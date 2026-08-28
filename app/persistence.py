"""SQL repositories plus read-only legacy JSON migration support."""
from __future__ import annotations

import json
import threading
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .project_ids import is_project_id, random_project_id
from .database import DatabaseProvider, SQLiteProvider


class PersistenceError(RuntimeError):
    pass


class ConflictError(PersistenceError):
    pass


class SqlStore:
    """Authoritative SQL repository.

    Business services continue to consume aggregate dictionaries.  Each write
    stores the aggregate and refreshes normalized relational projections in the
    same transaction, keeping persistence concerns outside calculations/UI.
    Legacy files are never inspected by construction or ordinary CRUD methods.
    """

    def __init__(self, root: Path, backup_retention: int = 20, provider: DatabaseProvider | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "murphywindow.db"
        self.project_id_database = self.database_path
        self.provider = provider or SQLiteProvider(self.database_path)
        self.backup_retention = backup_retention
        self._locks: dict[str, threading.Lock] = {}
        self._project_id_aliases: dict[str, str] = {}
        self._adopt_sql_compatibility_documents()

    def _lock(self, key: str) -> threading.Lock:
        self._locks.setdefault(key, threading.Lock())
        return self._locks[key]

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        """Read an explicit legacy migration source; never used by runtime CRUD."""
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Cannot read valid JSON from {path.name}: {exc}") from exc
        if not isinstance(value, dict):
            raise PersistenceError(f"Cannot read valid JSON from {path.name}: root must be an object")
        return value

    @staticmethod
    def _migrate_project(document: dict[str, Any]) -> dict[str, Any]:
        from .migrations import migrate_project_document
        try:
            return migrate_project_document(document)
        except ValueError as exc:
            raise PersistenceError(f"Cannot migrate project document: {exc}") from exc

    @staticmethod
    def _safe_document_name(name: str) -> str:
        value = str(name)
        safe = "".join(character for character in value if character.isalnum() or character in "_-")
        if not safe or safe != value:
            raise PersistenceError("Invalid document name")
        return safe

    @classmethod
    def _replace_project_id_references(cls, value: Any, mapping: dict[str, str]) -> Any:
        if isinstance(value,dict):
            replaced: dict[str,Any]={}
            for key,item in value.items():
                next_key=mapping.get(key,key) if isinstance(key,str) else key
                next_item=cls._replace_project_id_references(item,mapping)
                if next_key in replaced and replaced[next_key]!=next_item:
                    raise PersistenceError(f"Project ID migration produced conflicting key {next_key!r}.")
                replaced[next_key]=next_item
            return replaced
        if isinstance(value,list):return [cls._replace_project_id_references(item,mapping) for item in value]
        return mapping.get(value,value) if isinstance(value,str) else value

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def _encoded(cls, value: Any) -> tuple[str, str]:
        payload = cls._json(value)
        return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _decoded(value: str) -> dict[str, Any]:
        try:result = json.loads(value)
        except (TypeError, ValueError) as exc:raise PersistenceError(f"Stored document is not valid JSON: {exc}") from exc
        if not isinstance(result, dict):
            raise PersistenceError("Stored document root is not an object.")
        return result

    def _load_alias_manifest_for_explicit_migration(self, source_root: Path) -> dict[str, str]:
        path = source_root / "project-id-migration-v1.json"
        try:
            return dict(self._read(path).get("mapping") or {}) if path.exists() else {}
        except PersistenceError:
            return {}

    def _canonical_id(self, project_id: str) -> str:
        candidate = str(project_id)
        with self.provider.transaction() as connection:
            row = connection.execute("SELECT project_id FROM project_aliases WHERE alias = ?", (candidate,)).fetchone()
        return str(row[0]) if row else candidate

    def project_exists(self, project_id: str) -> bool:
        with self.provider.transaction() as connection:
            return connection.execute("SELECT 1 FROM projects WHERE id = ?", (self._canonical_id(project_id),)).fetchone() is not None

    def _claim_project_id(self, project_id: str, source: str) -> bool:
        if not is_project_id(project_id):
            return False
        try:
            with self.provider.transaction(write=True) as connection:
                connection.execute("INSERT INTO project_ids(id, claimed_at, source) VALUES (?, ?, ?)", (project_id, datetime.now(UTC).isoformat(), source))
            return True
        except Exception as exc:
            if self.provider.is_integrity_error(exc):return False
            raise

    def _record_project_id(self, project_id: str, source: str, connection: Any | None = None) -> None:
        if not str(project_id).strip():
            return
        if connection is not None:
            connection.execute("INSERT INTO project_ids(id, claimed_at, source) VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING", (project_id, datetime.now(UTC).isoformat(), source));return
        with self.provider.transaction(write=True) as active:
            self._record_project_id(project_id, source, active)

    def allocate_project_id(self, reserved: set[str] | None = None) -> str:
        blocked = {str(value).lower() for value in (reserved or set())}
        while True:
            candidate = random_project_id(blocked)
            if self._claim_project_id(candidate, "allocated"):
                return candidate
            blocked.add(candidate)

    def migrate_legacy_project_ids(self) -> dict[str, str]:
        """Return already-migrated SQL aliases; no filesystem migration occurs."""
        with self.provider.transaction() as connection:
            rows = connection.execute("SELECT alias,project_id FROM project_aliases ORDER BY alias").fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def _project_projection(self, connection: Any, document: dict[str, Any]) -> None:
        project_id = str(document["project"]["id"])
        connection.execute("DELETE FROM project_records WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM project_components WHERE project_id = ?", (project_id,))
        counters: dict[str, int] = {}

        def walk(value: Any, collection: str, parent_id: str | None = None) -> None:
            if not isinstance(value, list):
                return
            for local_ordinal, item in enumerate(value):
                if not isinstance(item, dict):
                    continue
                ordinal = counters.get(collection, 0);counters[collection] = ordinal + 1
                natural = item.get("id") or item.get("code") or item.get("key")
                identity = str(natural) if natural not in (None, "") else hashlib.sha256(self._json(item).encode()).hexdigest()[:24]
                record_id = identity if parent_id is None else f"{parent_id}:{identity}"
                payload = self._json(item)
                connection.execute("INSERT INTO project_records(project_id, collection_name, record_id, ordinal, parent_record_id, cost_code, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)", (project_id, collection, record_id, ordinal, parent_id, item.get("code") or item.get("cost_code"), payload))
                for key, child in item.items():
                    if isinstance(child, list):
                        walk(child, f"{collection}.{key}", record_id)

        for key, value in document.items():
            if key == "project":
                continue
            if isinstance(value, list):
                walk(value, key)
            else:
                connection.execute("INSERT INTO project_components(project_id, component_name, payload_json) VALUES (?, ?, ?)", (project_id, key, self._json(value)))

    def _upsert_project(self, connection: Any, document: dict[str, Any], record_kind: str, *, preserve_revision: bool = True) -> dict[str, Any]:
        saved = json.loads(json.dumps(document))
        project = saved["project"];project_id = str(project["id"])
        self._record_project_id(project_id, "import" if record_kind != "project" else "saved", connection)
        payload, digest = self._encoded(saved)
        connection.execute("""INSERT INTO projects(id, record_kind, name, project_number, configuration_id, status, archived, revision, schema_version, created_at, updated_at, document_json, document_sha256)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(id) DO UPDATE SET record_kind=excluded.record_kind,name=excluded.name,project_number=excluded.project_number,configuration_id=excluded.configuration_id,status=excluded.status,archived=excluded.archived,revision=excluded.revision,schema_version=excluded.schema_version,created_at=excluded.created_at,updated_at=excluded.updated_at,document_json=excluded.document_json,document_sha256=excluded.document_sha256""",
          (project_id, record_kind, project.get("name") or project_id, project.get("project_number"), project.get("configuration_id"), project.get("status"), int(bool(project.get("archived"))), int(project.get("revision", 0)), saved.get("schema_version"), project.get("created_at"), project.get("updated_at") or datetime.now(UTC).isoformat(), payload, digest))
        self._project_projection(connection, saved)
        return saved

    def list_projects(self) -> list[dict[str, Any]]:
        with self.provider.transaction() as connection:
            rows = connection.execute("SELECT document_json FROM projects WHERE record_kind='project' ORDER BY lower(name), id").fetchall()
        return [self._migrate_project(self._decoded(row[0]))["project"] for row in rows]

    def iter_project_documents(self, *, include_historical_reference: bool = False) -> list[tuple[str, dict[str, Any]]]:
        kinds = ("project", "historical_reference") if include_historical_reference else ("project",)
        placeholders = ",".join("?" for _ in kinds)
        with self.provider.transaction() as connection:
            rows = connection.execute(f"SELECT record_kind, document_json FROM projects WHERE record_kind IN ({placeholders}) ORDER BY id", kinds).fetchall()
        return [(str(row[0]), self._migrate_project(self._decoded(row[1]))) for row in rows]

    def save_historical_reference(self, document: dict[str, Any]) -> dict[str, Any]:
        prepared = self._migrate_project(json.loads(json.dumps(document)))
        with self.provider.transaction(write=True) as connection:
            return self._upsert_project(connection, prepared, "historical_reference")

    def load_project(self, project_id: str, recover: bool = False) -> tuple[dict[str, Any], str | None]:
        canonical = self._canonical_id(project_id)
        with self.provider.transaction() as connection:
            row = connection.execute("SELECT document_json, document_sha256 FROM projects WHERE id = ?", (canonical,)).fetchone()
            if row is None:
                raise PersistenceError(f"Project not found: {project_id}")
            if hashlib.sha256(str(row[0]).encode()).hexdigest() != row[1]:
                if not recover:
                    raise PersistenceError("Stored project failed its integrity hash.")
                backup = connection.execute("SELECT id, document_json FROM project_backups WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (canonical,)).fetchone()
                if not backup:
                    raise PersistenceError("Stored project is invalid and no valid backup exists.")
                return self._migrate_project(self._decoded(backup[1])), str(backup[0])
        return self._migrate_project(self._decoded(row[0])), None

    def _insert_backup(self, connection: Any, project_id: str, document: dict[str, Any], revision: int, label: str) -> str:
        created = datetime.now(UTC).isoformat();backup_id = f"{created.replace(':','').replace('-','').replace('+','_')}-r{revision}-{label}-{uuid.uuid4().hex[:8]}"
        payload, digest = self._encoded(document)
        connection.execute("INSERT INTO project_backups(id, project_id, revision, label, created_at, document_json, document_sha256) VALUES (?, ?, ?, ?, ?, ?, ?)", (backup_id, project_id, revision, label, created, payload, digest))
        expired=connection.execute("SELECT id FROM project_backups WHERE project_id=? ORDER BY created_at DESC",(project_id,)).fetchall()[self.backup_retention:]
        for row in expired:connection.execute("DELETE FROM project_backups WHERE id=?",(row[0],))
        return backup_id

    def save_project(self, doc: dict[str, Any], expected_revision: int | None, *, force_snapshot: bool = False) -> dict[str, Any]:
        incoming = json.loads(json.dumps(doc));project_id = str(incoming["project"]["id"])
        with self._lock(project_id), self.provider.transaction(write=True) as connection:
            row = connection.execute("SELECT revision, document_json FROM projects WHERE id=?", (project_id,)).fetchone()
            if row:
                actual = int(row[0])
                if expected_revision is not None and int(expected_revision) != actual:
                    raise ConflictError(f"Concurrent edit detected: expected revision {expected_revision}, current revision {actual}.")
                current = self._decoded(row[1]);self._insert_backup(connection, project_id, current, actual, "autosave")
                revision = actual + 1
            else:
                if expected_revision not in (None, -1, 0):
                    raise ConflictError("Project does not yet exist at the expected revision.")
                revision = 1
            incoming["project"]["revision"] = revision
            incoming["project"]["updated_at"] = datetime.now(UTC).isoformat()
            saved = self._upsert_project(connection, incoming, "project")
            if force_snapshot:
                self._insert_backup(connection, project_id, saved, revision, "manual")
            return saved

    def manual_backup(self, project_id: str) -> str:
        document, _ = self.load_project(project_id);canonical = document["project"]["id"]
        with self.provider.transaction(write=True) as connection:
            return self._insert_backup(connection, canonical, document, int(document["project"].get("revision", 0)), "manual")

    def backup_names(self, project_id: str) -> list[str]:
        with self.provider.transaction() as connection:
            return [str(row[0]) for row in connection.execute("SELECT id FROM project_backups WHERE project_id=? ORDER BY created_at DESC", (self._canonical_id(project_id),))]

    def restore_backup(self, project_id: str, backup_name: str) -> dict[str, Any]:
        canonical = self._canonical_id(project_id)
        with self.provider.transaction(write=True) as connection:
            current = connection.execute("SELECT revision, document_json FROM projects WHERE id=?", (canonical,)).fetchone()
            backup = connection.execute("SELECT document_json FROM project_backups WHERE project_id=? AND id=?", (canonical, Path(backup_name).name)).fetchone()
            if not backup:
                raise PersistenceError("Backup not found.")
            recovered = self._decoded(backup[0]);revision = int(current[0]) + 1
            try:current_document=self._decoded(current[1])
            except PersistenceError:current_document=None
            if current_document is not None:self._insert_backup(connection, canonical, current_document, int(current[0]), "pre-restore")
            recovered["project"]["revision"] = revision;recovered["project"]["updated_at"] = datetime.now(UTC).isoformat()
            return self._upsert_project(connection, recovered, "project")

    def save_configuration(self, config: dict[str, Any]) -> None:
        payload, digest = self._encoded(config);created = datetime.now(UTC).isoformat()
        with self.provider.transaction(write=True) as connection:
            connection.execute("INSERT INTO configurations(id,version,effective_date,created_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,effective_date=excluded.effective_date,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256", (config["id"], config.get("version"), config.get("effective_date"), created, payload, digest))
            connection.execute("DELETE FROM configuration_records WHERE configuration_id=?", (config["id"],))
            for key, values in config.items():
                if not isinstance(values, list):continue
                for ordinal, item in enumerate(values):
                    if not isinstance(item, dict):continue
                    record_id = str(item.get("id") or item.get("code") or item.get("name") or ordinal)
                    connection.execute("INSERT INTO configuration_records(configuration_id,collection_name,record_id,ordinal,payload_json) VALUES(?,?,?,?,?)", (config["id"], key, record_id, ordinal, self._json(item)))

    def load_configuration(self, config_id: str) -> dict[str, Any]:
        with self.provider.transaction() as connection:
            row = connection.execute("SELECT payload_json,payload_sha256 FROM configurations WHERE id=?", (config_id,)).fetchone()
        if not row:raise PersistenceError(f"Configuration not found: {config_id}")
        if hashlib.sha256(str(row[0]).encode()).hexdigest()!=row[1]:raise PersistenceError("Configuration failed its integrity hash.")
        return self._decoded(row[0])

    def configuration_exists(self, config_id: str) -> bool:
        with self.provider.transaction() as connection:
            return connection.execute("SELECT 1 FROM configurations WHERE id=?", (config_id,)).fetchone() is not None

    def list_configurations(self) -> list[dict[str, Any]]:
        with self.provider.transaction() as connection:
            return [self._decoded(row[0]) for row in connection.execute("SELECT payload_json FROM configurations ORDER BY effective_date,id")]

    def master_data_exists(self, name: str = "directory") -> bool:
        with self.provider.transaction() as connection:return connection.execute("SELECT 1 FROM master_documents WHERE name=?", (self._safe_document_name(name),)).fetchone() is not None

    def load_master_data(self, name: str = "directory") -> dict[str, Any]:
        with self.provider.transaction() as connection:row=connection.execute("SELECT payload_json FROM master_documents WHERE name=?", (self._safe_document_name(name),)).fetchone()
        if not row:raise PersistenceError("Master-data document not found.")
        return self._decoded(row[0])

    def save_master_data(self, document: dict[str, Any], expected_revision: int | None, *, name: str = "directory") -> dict[str, Any]:
        name=self._safe_document_name(name)
        with self.provider.transaction(write=True) as connection:
            row=connection.execute("SELECT revision,payload_json FROM master_documents WHERE name=?",(name,)).fetchone()
            actual=int(row[0]) if row else 0
            if row and expected_revision is not None and int(expected_revision)!=actual:raise ConflictError(f"Concurrent master-data edit detected: expected revision {expected_revision}, current revision {actual}.")
            if not row and expected_revision not in (None,-1,0):raise ConflictError("Master-data document does not yet exist at the expected revision.")
            if row:self._insert_master_backup(connection,name,self._decoded(row[1]),actual)
            saved=json.loads(json.dumps(document));saved["revision"]=actual+1;saved["updated_at"]=datetime.now(UTC).isoformat();payload,digest=self._encoded(saved)
            connection.execute("INSERT INTO master_documents(name,revision,updated_at,payload_json,payload_sha256) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET revision=excluded.revision,updated_at=excluded.updated_at,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256",(name,actual+1,saved["updated_at"],payload,digest))
            connection.execute("DELETE FROM master_entities WHERE document_name=?",(name,))
            for kind,values in saved.items():
                if not isinstance(values,list):continue
                for ordinal,item in enumerate(values):
                    if not isinstance(item,dict):continue
                    entity_id=str(item.get("id") or ordinal);normalized=item.get("normalized_name") or item.get("display_name") or item.get("name")
                    connection.execute("INSERT INTO master_entities(document_name,entity_kind,entity_id,normalized_name,payload_json) VALUES(?,?,?,?,?)",(name,kind,entity_id,str(normalized or "").casefold(),self._json(item)))
            return saved

    def _insert_master_backup(self,connection:Any,name:str,document:dict[str,Any],revision:int)->str:
        created=datetime.now(UTC).isoformat();backup_id=f"{created.replace(':','')}-r{revision}-{uuid.uuid4().hex[:8]}";payload,digest=self._encoded(document)
        connection.execute("INSERT INTO master_backups(id,document_name,revision,created_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?)",(backup_id,name,revision,created,payload,digest))
        expired=connection.execute("SELECT id FROM master_backups WHERE document_name=? ORDER BY created_at DESC",(name,)).fetchall()[self.backup_retention:]
        for row in expired:connection.execute("DELETE FROM master_backups WHERE id=?",(row[0],))
        return backup_id

    def master_data_backup_names(self,name:str="directory")->list[str]:
        with self.provider.transaction() as connection:return [str(row[0]) for row in connection.execute("SELECT id FROM master_backups WHERE document_name=? ORDER BY created_at DESC",(self._safe_document_name(name),))]

    def restore_master_data(self,backup_name:str,*,name:str="directory")->dict[str,Any]:
        name=self._safe_document_name(name)
        with self.provider.transaction() as connection:row=connection.execute("SELECT payload_json FROM master_backups WHERE document_name=? AND id=?",(name,Path(backup_name).name)).fetchone()
        if not row:raise PersistenceError("Master-data backup not found.")
        current=self.load_master_data(name);return self.save_master_data(self._decoded(row[0]),int(current.get("revision",0)),name=name)

    def historical_index_exists(self,name:str)->bool:
        with self.provider.transaction() as connection:return connection.execute("SELECT 1 FROM historical_indexes WHERE name=?",(self._safe_document_name(name),)).fetchone() is not None
    def load_historical_index(self,name:str)->dict[str,Any]:
        with self.provider.transaction() as connection:row=connection.execute("SELECT payload_json FROM historical_indexes WHERE name=?",(self._safe_document_name(name),)).fetchone()
        if not row:raise PersistenceError("Historical index not found.")
        return self._decoded(row[0])
    def save_historical_index(self,document:dict[str,Any],name:str,expected_revision:int|None=None)->dict[str,Any]:
        name=self._safe_document_name(name)
        with self.provider.transaction(write=True) as connection:
            row=connection.execute("SELECT revision FROM historical_indexes WHERE name=?",(name,)).fetchone();actual=int(row[0]) if row else 0
            if expected_revision is not None and int(expected_revision)!=actual:raise ConflictError(f"Concurrent historical-index refresh detected: expected revision {expected_revision}, current revision {actual}.")
            saved=json.loads(json.dumps(document));saved["revision"]=actual+1;saved["updated_at"]=datetime.now(UTC).isoformat();payload,digest=self._encoded(saved)
            connection.execute("INSERT INTO historical_indexes(name,revision,updated_at,payload_json,payload_sha256) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET revision=excluded.revision,updated_at=excluded.updated_at,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256",(name,actual+1,saved["updated_at"],payload,digest));return saved

    def save_proposal_snapshot(self,project_id:str,snapshot:dict[str,Any])->str:
        proposal_id=str(snapshot.get("metadata",{}).get("id") or "");payload,digest=self._encoded(snapshot)
        try:
            with self.provider.transaction(write=True) as connection:connection.execute("INSERT INTO proposal_snapshots(id,project_id,created_at,payload_json,payload_sha256) VALUES(?,?,?,?,?)",(proposal_id,self._canonical_id(project_id),datetime.now(UTC).isoformat(),payload,digest))
        except Exception as exc:
            if self.provider.is_integrity_error(exc):raise ConflictError("Immutable proposal snapshot already exists.") from exc
            raise
        return proposal_id
    def load_proposal_snapshot(self,project_id:str,proposal_id:str)->dict[str,Any]:
        with self.provider.transaction() as connection:row=connection.execute("SELECT payload_json FROM proposal_snapshots WHERE project_id=? AND id=?",(self._canonical_id(project_id),proposal_id)).fetchone()
        if not row:raise PersistenceError("Proposal snapshot not found.")
        return self._decoded(row[0])
    def discard_unindexed_proposal(self,project_id:str,proposal_id:str)->None:
        with self.provider.transaction(write=True) as connection:connection.execute("DELETE FROM proposal_snapshots WHERE project_id=? AND id=?",(self._canonical_id(project_id),proposal_id))
    def list_proposal_snapshot_ids(self,project_id:str)->list[str]:
        with self.provider.transaction() as connection:return [str(row[0]) for row in connection.execute("SELECT id FROM proposal_snapshots WHERE project_id=? ORDER BY created_at",(self._canonical_id(project_id),))]
    def save_proposal_artifact(self,project_id:str,artifact_id:str,content:bytes)->str:
        try:
            with self.provider.transaction(write=True) as connection:connection.execute("INSERT INTO proposal_artifacts(id,project_id,media_type,created_at,content,sha256) VALUES(?,?,?,?,?,?)",(artifact_id,self._canonical_id(project_id),"application/pdf",datetime.now(UTC).isoformat(),content,hashlib.sha256(content).hexdigest()))
        except Exception as exc:
            if self.provider.is_integrity_error(exc):raise ConflictError("Immutable proposal artifact already exists.") from exc
            raise
        return artifact_id
    def load_proposal_artifact(self,project_id:str,artifact_id:str)->bytes:
        with self.provider.transaction() as connection:row=connection.execute("SELECT content,sha256 FROM proposal_artifacts WHERE project_id=? AND id=?",(self._canonical_id(project_id),artifact_id)).fetchone()
        if not row:raise PersistenceError("Proposal artifact not found.")
        content=bytes(row[0]);
        if hashlib.sha256(content).hexdigest()!=row[1]:raise PersistenceError("Stored proposal artifact failed its immutable SHA-256 verification.")
        return content
    def discard_unindexed_artifact(self,project_id:str,artifact_id:str)->None:
        with self.provider.transaction(write=True) as connection:connection.execute("DELETE FROM proposal_artifacts WHERE project_id=? AND id=?",(self._canonical_id(project_id),artifact_id))
    def proposal_artifact_exists(self,project_id:str,artifact_id:str)->bool:
        with self.provider.transaction() as connection:return connection.execute("SELECT 1 FROM proposal_artifacts WHERE project_id=? AND id=?",(self._canonical_id(project_id),artifact_id)).fetchone() is not None

    def save_cost_code_reference(self, document: dict[str, Any], name: str = "codes") -> None:
        """Persist the reference aggregate and its searchable relational rows atomically."""
        safe_name = self._safe_document_name(name)
        records = document.get("records") or []
        if not isinstance(records, list):
            raise PersistenceError("Cost-code reference records must be a list.")
        payload,digest=self._encoded(document)
        with self.provider.transaction(write=True) as connection:
            source=document.get("source");source_text=self._json(source) if isinstance(source,(dict,list)) else source
            connection.execute("INSERT INTO cost_code_references(name,reference_id,source,source_sha256,updated_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET reference_id=excluded.reference_id,source=excluded.source,source_sha256=excluded.source_sha256,updated_at=excluded.updated_at,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256",(safe_name,document.get("reference_id"),source_text,document.get("source_sha256") or (source.get("sha256") if isinstance(source,dict) else None),datetime.now(UTC).isoformat(),payload,digest))
            connection.execute("DELETE FROM cost_code_records WHERE reference_name=?",(safe_name,))
            seen: set[str] = set()
            for ordinal,item in enumerate(records):
                if not isinstance(item,dict):
                    raise PersistenceError(f"Cost-code reference record {ordinal} is not an object.")
                record_id=str(item.get("id") or item.get("reference_id") or ordinal)
                if record_id in seen:
                    raise PersistenceError(f"Duplicate cost-code reference record id: {record_id}")
                seen.add(record_id)
                normalized=str(item.get("normalized_code") or item.get("code") or "").strip()
                connection.execute("INSERT INTO cost_code_records(reference_name,record_id,ordinal,normalized_code,display_code,description,payload_json) VALUES(?,?,?,?,?,?,?)",(safe_name,record_id,ordinal,normalized,item.get("display_code") or item.get("code"),item.get("description"),self._json(item)))
            stored=int(connection.execute("SELECT COUNT(*) FROM cost_code_records WHERE reference_name=?",(safe_name,)).fetchone()[0])
            if stored != len(records):
                raise PersistenceError(f"Cost-code reference verification failed: expected {len(records)}, stored {stored}.")

    def load_cost_code_reference(self, name: str = "codes") -> dict[str, Any] | None:
        safe_name=self._safe_document_name(name)
        with self.provider.transaction() as connection:
            row=connection.execute("SELECT payload_json,payload_sha256 FROM cost_code_references WHERE name=?",(safe_name,)).fetchone()
        if not row:return None
        if hashlib.sha256(str(row[0]).encode()).hexdigest()!=row[1]:raise PersistenceError("Cost-code reference failed its integrity hash.")
        return self._decoded(row[0])

    def ensure_packaged_cost_code_reference(self) -> dict[str, Any]:
        """Seed a new SQL database from the immutable packaged bootstrap resource."""
        current=self.load_cost_code_reference()
        if current is not None:return current
        bootstrap=Path(__file__).resolve().parent/"static-data"/"codes.json"
        document=self._read(bootstrap)
        self.save_cost_code_reference(document)
        return document

    def save_application_credential(self, name: str, credential: dict[str, Any]) -> None:
        safe_name=self._safe_document_name(name);username=credential.get("username");password_hash=credential.get("password_hash")
        if not isinstance(username,str) or not username or not isinstance(password_hash,str) or not password_hash:
            raise PersistenceError("Credential requires a username and password_hash.")
        with self.provider.transaction(write=True) as connection:
            connection.execute("INSERT INTO application_credentials(name,username,password_hash,updated_at) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET username=excluded.username,password_hash=excluded.password_hash,updated_at=excluded.updated_at",(safe_name,username,password_hash,datetime.now(UTC).isoformat()))

    def load_application_credential(self, name: str) -> dict[str, str] | None:
        with self.provider.transaction() as connection:row=connection.execute("SELECT username,password_hash FROM application_credentials WHERE name=?",(self._safe_document_name(name),)).fetchone()
        return {"username":str(row[0]),"password_hash":str(row[1])} if row else None

    def _adopt_sql_compatibility_documents(self) -> None:
        """One-way SQL-to-SQL upgrade from migration-v2 compatibility rows."""
        with self.provider.transaction() as connection:
            reference=connection.execute("SELECT payload_json FROM persistent_documents WHERE document_kind='reference' AND name='codes'").fetchone()
            credential=connection.execute("SELECT payload_json FROM persistent_documents WHERE document_kind='secret' AND name='custom-code'").fetchone()
            has_reference=connection.execute("SELECT 1 FROM cost_code_references WHERE name='codes'").fetchone()
            has_credential=connection.execute("SELECT 1 FROM application_credentials WHERE name='custom-code'").fetchone()
        if reference and not has_reference:self.save_cost_code_reference(self._decoded(reference[0]))
        if credential and not has_credential:self.save_application_credential("custom-code",self._decoded(credential[0]))
        with self.provider.transaction(write=True) as connection:
            connection.execute("DELETE FROM persistent_documents WHERE document_kind IN ('reference','secret')")

    def load_persistent_document(self, kind: str, name: str) -> dict[str, Any] | None:
        with self.provider.transaction() as connection:
            row = connection.execute("SELECT payload_json,payload_sha256 FROM persistent_documents WHERE document_kind=? AND name=?", (kind, name)).fetchone()
        if not row:return None
        if hashlib.sha256(str(row[0]).encode()).hexdigest()!=row[1]:raise PersistenceError(f"{kind} document failed its integrity hash.")
        return self._decoded(row[0])

    def _store_persistent_document(self, connection: Any, kind: str, name: str, document: dict[str, Any]) -> None:
        payload,digest=self._encoded(document)
        connection.execute("INSERT INTO persistent_documents(document_kind,name,updated_at,payload_json,payload_sha256) VALUES(?,?,?,?,?) ON CONFLICT(document_kind,name) DO UPDATE SET updated_at=excluded.updated_at,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256",(kind,name,datetime.now(UTC).isoformat(),payload,digest))

    def _repair_relational_projections(self) -> None:
        """Idempotently rebuild projections from authoritative SQL aggregates."""
        with self.provider.transaction(write=True) as connection:
            for row in connection.execute("SELECT id,payload_json FROM configurations").fetchall():
                config_id,config=str(row[0]),self._decoded(row[1]);connection.execute("DELETE FROM configuration_records WHERE configuration_id=?",(config_id,))
                for key,values in config.items():
                    if not isinstance(values,list):continue
                    for ordinal,item in enumerate(values):
                        if not isinstance(item,dict):continue
                        record_id=str(item.get("id") or item.get("code") or item.get("name") or ordinal)
                        connection.execute("INSERT INTO configuration_records(configuration_id,collection_name,record_id,ordinal,payload_json) VALUES(?,?,?,?,?)",(config_id,key,record_id,ordinal,self._json(item)))
            for row in connection.execute("SELECT name,payload_json FROM master_documents").fetchall():
                name,document=str(row[0]),self._decoded(row[1]);connection.execute("DELETE FROM master_entities WHERE document_name=?",(name,))
                for kind,values in document.items():
                    if not isinstance(values,list):continue
                    for ordinal,item in enumerate(values):
                        if not isinstance(item,dict):continue
                        entity_id=str(item.get("id") or ordinal);normalized=item.get("normalized_name") or item.get("display_name") or item.get("name")
                        connection.execute("INSERT INTO master_entities(document_name,entity_kind,entity_id,normalized_name,payload_json) VALUES(?,?,?,?,?)",(name,kind,entity_id,str(normalized or "").casefold(),self._json(item)))

    def legacy_migration_report(self, source_root: Path | None = None) -> dict[str, Any]:
        """Audit an explicitly supplied legacy source tree; never called at startup."""
        source_root=Path(source_root or self.root)
        patterns = (
            "projects/*.json", "historical-reference/*.json", "configurations/*.json",
            "master-data/*.json", "backups/*/*.json", "master-data-backups/*/*.json",
            "historical-index/*.json", "proposals/*/*.json", "proposal-artifacts/*/*.pdf",
            "reference/*.json", "secrets/*.json", "project-id-migration-v1.json",
        )
        sources = sorted({path for pattern in patterns for path in source_root.glob(pattern) if path.is_file()})
        with self.provider.transaction() as connection:
            migrated = {str(row[0]): str(row[1]) for row in connection.execute("SELECT source_key,source_sha256 FROM data_migrations")}
            target_counts = {table:int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in ("projects","project_aliases","project_records","project_backups","configurations","configuration_records","master_documents","master_entities","master_backups","historical_indexes","proposal_snapshots","proposal_artifacts","cost_code_references","cost_code_records","application_credentials")}
        missing=[];changed=[]
        for path in sources:
            key=str(path.relative_to(source_root));digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if key not in migrated:missing.append(key)
            elif migrated[key]!=digest:changed.append(key)
        return {"database":str(self.database_path),"source_files":len(sources),"verified_files":len(sources)-len(missing)-len(changed),"missing":missing,"changed_after_import":changed,"target_counts":target_counts,"integrity_check":self.provider.integrity_check(),"foreign_key_violations":len(self.provider.foreign_key_violations()),"ok":not missing and not changed and self.provider.integrity_check()=="ok" and not self.provider.foreign_key_violations()}

    def _migration_recorded(self,connection:Any,key:str,digest:str)->bool:
        row=connection.execute("SELECT source_sha256 FROM data_migrations WHERE source_key=?",(key,)).fetchone();return bool(row and row[0]==digest)
    def _mark_migrated(self,connection:Any,key:str,digest:str,table:str,target:str)->None:
        now=datetime.now(UTC).isoformat();connection.execute("INSERT INTO data_migrations(source_key,source_sha256,target_table,target_key,imported_at,verified_at) VALUES(?,?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET source_sha256=excluded.source_sha256,target_table=excluded.target_table,target_key=excluded.target_key,imported_at=excluded.imported_at,verified_at=excluded.verified_at",(key,digest,table,target,now,now))
    def migrate_legacy_data_once(self, source_root: Path | None = None) -> dict[str, Any]:
        """Run the controlled legacy import once and record a durable completion marker."""
        source_root=Path(source_root or self.root).resolve()
        migration_name="legacy-json-v1"
        with self.provider.transaction() as connection:
            prior=connection.execute("SELECT status,summary_json FROM legacy_migration_runs WHERE migration_name=?",(migration_name,)).fetchone()
        if prior and prior[0]=="completed":
            summary=json.loads(prior[1]);summary["already_completed"]=True;return summary
        patterns=("projects/*.json","historical-reference/*.json","configurations/*.json","master-data/*.json","backups/*/*.json","master-data-backups/*/*.json","historical-index/*.json","proposals/*/*.json","proposal-artifacts/*/*.pdf","reference/*.json","secrets/*.json","project-id-migration-v1.json")
        sources=sorted({path for pattern in patterns for path in source_root.glob(pattern) if path.is_file()})
        manifest_payload="\n".join(f"{path.relative_to(source_root)}:{hashlib.sha256(path.read_bytes()).hexdigest()}" for path in sources)
        manifest_digest=hashlib.sha256(manifest_payload.encode()).hexdigest()
        started=datetime.now(UTC).isoformat()
        with self.provider.transaction(write=True) as connection:
            connection.execute("INSERT INTO legacy_migration_runs(migration_name,status,source_root,source_manifest_sha256,started_at,completed_at,summary_json) VALUES(?,?,?,?,?,?,?) ON CONFLICT(migration_name) DO UPDATE SET status=excluded.status,source_root=excluded.source_root,source_manifest_sha256=excluded.source_manifest_sha256,started_at=excluded.started_at,completed_at=NULL,summary_json=excluded.summary_json",(migration_name,"running",str(source_root),manifest_digest,started,None,"{}"))
        try:
            self._import_legacy_data(source_root)
            report=self.legacy_migration_report(source_root)
            if not report["ok"]:raise PersistenceError(f"Legacy migration verification failed: {report}")
            report.update({"migration_name":migration_name,"source_manifest_sha256":manifest_digest,"completed_at":datetime.now(UTC).isoformat(),"already_completed":False})
            with self.provider.transaction(write=True) as connection:
                connection.execute("UPDATE legacy_migration_runs SET status='completed',completed_at=?,summary_json=? WHERE migration_name=?",(report["completed_at"],self._json(report),migration_name))
            return report
        except Exception as exc:
            with self.provider.transaction(write=True) as connection:
                connection.execute("UPDATE legacy_migration_runs SET status='failed',summary_json=? WHERE migration_name=?",(self._json({"error":str(exc)}),migration_name))
            raise

    def _import_legacy_data(self, source_root: Path)->None:
        """Implementation for explicit one-time migration only."""
        aliases=self._load_alias_manifest_for_explicit_migration(source_root)
        projects=source_root/"projects";historical_reference=source_root/"historical-reference";configurations=source_root/"configurations";master_data=source_root/"master-data";proposals=source_root/"proposals";proposal_artifacts=source_root/"proposal-artifacts";backups=source_root/"backups";master_data_backups=source_root/"master-data-backups";historical_indexes=source_root/"historical-index"
        with self.provider.transaction(write=True) as connection:
            for alias,target in aliases.items():self._record_project_id(target,"legacy-alias",connection);connection.execute("INSERT INTO project_aliases(alias,project_id) VALUES(?,?) ON CONFLICT(alias) DO NOTHING",(alias,target))
            alias_manifest=source_root/"project-id-migration-v1.json"
            if alias_manifest.exists():
                alias_digest=hashlib.sha256(alias_manifest.read_bytes()).hexdigest();self._mark_migrated(connection,str(alias_manifest.relative_to(source_root)),alias_digest,"project_aliases",str(len(aliases)))
            for folder,kind in ((projects,"project"),(historical_reference,"historical_reference")):
                for path in sorted(folder.glob("*.json")) if folder.exists() else []:
                    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();key=str(path.relative_to(source_root))
                    if self._migration_recorded(connection,key,digest):continue
                    source_document=self._read(path);source_document=self._replace_project_id_references(source_document,aliases);document=self._migrate_project(source_document);self._upsert_project(connection,document,kind);stored=connection.execute("SELECT document_json FROM projects WHERE id=?",(document["project"]["id"],)).fetchone()
                    if self._decoded(stored[0])!=document:raise PersistenceError(f"SQL migration verification failed for {path.name}")
                    self._mark_migrated(connection,key,digest,"projects",document["project"]["id"])
            for path in sorted(configurations.glob("*.json")) if configurations.exists() else []:
                raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();key=str(path.relative_to(source_root))
                if self._migration_recorded(connection,key,digest):continue
                config=self._read(path);payload,payload_digest=self._encoded(config);connection.execute("INSERT INTO configurations(id,version,effective_date,created_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,effective_date=excluded.effective_date,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256",(config["id"],config.get("version"),config.get("effective_date"),datetime.now(UTC).isoformat(),payload,payload_digest));self._mark_migrated(connection,key,digest,"configurations",config["id"])
            for path in sorted(master_data.glob("*.json")) if master_data.exists() else []:
                raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();key=str(path.relative_to(source_root));doc=self._read(path)
                if self._migration_recorded(connection,key,digest):continue
                payload,payload_digest=self._encoded(doc);connection.execute("INSERT INTO master_documents(name,revision,updated_at,payload_json,payload_sha256) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET revision=excluded.revision,updated_at=excluded.updated_at,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256",(path.stem,int(doc.get("revision",0)),doc.get("updated_at") or datetime.now(UTC).isoformat(),payload,payload_digest));self._mark_migrated(connection,key,digest,"master_documents",path.stem)
            for folder in sorted(proposals.glob("*")) if proposals.exists() else []:
                if not folder.is_dir():continue
                project_id=aliases.get(folder.name,folder.name)
                if not connection.execute("SELECT 1 FROM projects WHERE id=?",(project_id,)).fetchone():continue
                for path in sorted(folder.glob("*.json")):
                    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();key=str(path.relative_to(source_root))
                    if self._migration_recorded(connection,key,digest):continue
                    snapshot=self._replace_project_id_references(self._read(path),aliases);payload,payload_digest=self._encoded(snapshot);connection.execute("INSERT INTO proposal_snapshots(id,project_id,created_at,payload_json,payload_sha256) VALUES(?,?,?,?,?) ON CONFLICT(id) DO NOTHING",(path.stem,project_id,datetime.now(UTC).isoformat(),payload,payload_digest));self._mark_migrated(connection,key,digest,"proposal_snapshots",path.stem)
            for folder in sorted(proposal_artifacts.glob("*")) if proposal_artifacts.exists() else []:
                if not folder.is_dir():continue
                project_id=aliases.get(folder.name,folder.name)
                if not connection.execute("SELECT 1 FROM projects WHERE id=?",(project_id,)).fetchone():continue
                for path in sorted(folder.glob("*.pdf")):
                    content=path.read_bytes();digest=hashlib.sha256(content).hexdigest();key=str(path.relative_to(source_root))
                    if self._migration_recorded(connection,key,digest):continue
                    connection.execute("INSERT INTO proposal_artifacts(id,project_id,media_type,created_at,content,sha256) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",(path.stem,project_id,"application/pdf",datetime.now(UTC).isoformat(),content,digest));self._mark_migrated(connection,key,digest,"proposal_artifacts",path.stem)
            for folder in sorted(backups.glob("*")) if backups.exists() else []:
                if not folder.is_dir():continue
                project_id=aliases.get(folder.name,folder.name)
                if not connection.execute("SELECT 1 FROM projects WHERE id=?",(project_id,)).fetchone():continue
                for path in sorted(folder.glob("*.json")):
                    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();key=str(path.relative_to(source_root))
                    if self._migration_recorded(connection,key,digest):continue
                    document=self._migrate_project(self._read(path));revision=int(document.get("project",{}).get("revision",0));label="manual" if "manual" in path.stem else "legacy";payload,payload_digest=self._encoded(document)
                    connection.execute("INSERT INTO project_backups(id,project_id,revision,label,created_at,document_json,document_sha256) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",(f"legacy-{hashlib.sha256(key.encode()).hexdigest()[:24]}",project_id,revision,label,datetime.fromtimestamp(path.stat().st_mtime,UTC).isoformat(),payload,payload_digest));self._mark_migrated(connection,key,digest,"project_backups",project_id)
            for folder in sorted(master_data_backups.glob("*")) if master_data_backups.exists() else []:
                if not folder.is_dir():continue
                for path in sorted(folder.glob("*.json")):
                    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();key=str(path.relative_to(source_root))
                    if self._migration_recorded(connection,key,digest):continue
                    document=self._read(path);payload,payload_digest=self._encoded(document);backup_id=f"legacy-{hashlib.sha256(key.encode()).hexdigest()[:24]}"
                    connection.execute("INSERT INTO master_backups(id,document_name,revision,created_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",(backup_id,folder.name,int(document.get("revision",0)),datetime.fromtimestamp(path.stat().st_mtime,UTC).isoformat(),payload,payload_digest));self._mark_migrated(connection,key,digest,"master_backups",folder.name)
            for path in sorted(historical_indexes.glob("*.json")) if historical_indexes.exists() else []:
                raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();key=str(path.relative_to(source_root))
                if self._migration_recorded(connection,key,digest):continue
                document=self._read(path);payload,payload_digest=self._encoded(document);connection.execute("INSERT INTO historical_indexes(name,revision,updated_at,payload_json,payload_sha256) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET revision=excluded.revision,updated_at=excluded.updated_at,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256",(path.stem,int(document.get("revision",0)),document.get("updated_at") or datetime.now(UTC).isoformat(),payload,payload_digest));self._mark_migrated(connection,key,digest,"historical_indexes",path.stem)
            for kind,folder in (("reference",source_root/"reference"),("secret",source_root/"secrets")):
                for path in sorted(folder.glob("*.json")) if folder.exists() else []:
                    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();key=str(path.relative_to(source_root))
                    if self._migration_recorded(connection,key,digest):continue
                    document=self._read(path)
                    if kind=="reference":
                        payload,payload_digest=self._encoded(document);source=document.get("source");source_text=self._json(source) if isinstance(source,(dict,list)) else source;connection.execute("INSERT INTO cost_code_references(name,reference_id,source,source_sha256,updated_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET reference_id=excluded.reference_id,source=excluded.source,source_sha256=excluded.source_sha256,updated_at=excluded.updated_at,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256",(path.stem,document.get("reference_id"),source_text,document.get("source_sha256") or (source.get("sha256") if isinstance(source,dict) else None),datetime.now(UTC).isoformat(),payload,payload_digest));connection.execute("DELETE FROM cost_code_records WHERE reference_name=?",(path.stem,));[connection.execute("INSERT INTO cost_code_records(reference_name,record_id,ordinal,normalized_code,display_code,description,payload_json) VALUES(?,?,?,?,?,?,?)",(path.stem,str(item.get("id") or item.get("reference_id") or ordinal),ordinal,str(item.get("normalized_code") or item.get("code") or ""),item.get("display_code") or item.get("code"),item.get("description"),self._json(item))) for ordinal,item in enumerate(document.get("records") or [])]
                        target_table="cost_code_references"
                    else:
                        username=document.get("username");password_hash=document.get("password_hash")
                        if not isinstance(username,str) or not isinstance(password_hash,str):raise PersistenceError(f"Invalid credential migration source: {path.name}")
                        connection.execute("INSERT INTO application_credentials(name,username,password_hash,updated_at) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET username=excluded.username,password_hash=excluded.password_hash,updated_at=excluded.updated_at",(path.stem,username,password_hash,datetime.now(UTC).isoformat()));target_table="application_credentials"
                    self._mark_migrated(connection,key,digest,target_table,path.stem)


# Compatibility import name; new code should type against SqlStore/repository methods.
JsonStore = SqlStore
