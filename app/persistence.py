"""Human-readable JSON persistence with atomic replacement and recovery."""
from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PersistenceError(RuntimeError):
    pass


class ConflictError(PersistenceError):
    pass


class JsonStore:
    def __init__(self, root: Path, backup_retention: int = 20):
        self.root = root
        self.projects = root / "projects"
        self.backups = root / "backups"
        self.exports = root / "exports"
        self.configurations = root / "configurations"
        self.master_data = root / "master-data"
        self.master_data_backups = root / "master-data-backups"
        self.historical_indexes = root / "historical-index"
        self.historical_reference = root / "historical-reference"
        self.proposals = root / "proposals"
        self.proposal_artifacts = root / "proposal-artifacts"
        self.backup_retention = backup_retention
        self._locks: dict[str, threading.Lock] = {}
        for path in (
            self.projects, self.backups, self.exports, self.configurations,
            self.master_data, self.master_data_backups, self.historical_indexes, self.historical_reference,
            self.proposals, self.proposal_artifacts,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _lock(self, key: str) -> threading.Lock:
        self._locks.setdefault(key, threading.Lock())
        return self._locks[key]

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            if not isinstance(value, dict):
                raise ValueError("root must be an object")
            return value
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Cannot read valid JSON from {path.name}: {exc}") from exc

    @staticmethod
    def _migrate_project(document: dict[str, Any]) -> dict[str, Any]:
        """Migrate a project in memory without rewriting its source file."""
        from .migrations import migrate_project_document
        try:
            return migrate_project_document(document)
        except ValueError as exc:
            raise PersistenceError(f"Cannot migrate project document: {exc}") from exc

    @staticmethod
    def atomic_write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except OSError as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise PersistenceError(f"Atomic save failed for {path.name}: {exc}") from exc

    def project_path(self, project_id: str) -> Path:
        safe = "".join(c for c in project_id if c.isalnum() or c in "_-")
        if safe != project_id or not safe:
            raise PersistenceError("Invalid project identifier")
        return self.projects / f"{safe}.json"

    def list_projects(self) -> list[dict[str, Any]]:
        output = []
        for path in sorted(self.projects.glob("*.json")):
            try:
                doc = self._migrate_project(self._read(path))
                output.append(doc["project"])
            except (PersistenceError, KeyError):
                output.append({"id": path.stem, "name": path.stem, "malformed": True, "archived": False})
        return output

    def load_project(self, project_id: str, recover: bool = False) -> tuple[dict[str, Any], str | None]:
        path = self.project_path(project_id)
        try:
            return self._migrate_project(self._read(path)), None
        except PersistenceError as primary_error:
            if not recover:
                raise
            candidates = sorted((self.backups / project_id).glob("*.json"), reverse=True)
            for candidate in candidates:
                try:
                    return self._migrate_project(self._read(candidate)), candidate.name
                except PersistenceError:
                    continue
            raise PersistenceError(f"Primary is invalid and no valid backup exists: {primary_error}") from primary_error

    def save_project(self, doc: dict[str, Any], expected_revision: int | None, *, force_snapshot: bool = False) -> dict[str, Any]:
        project = doc["project"]
        project_id = project["id"]
        path = self.project_path(project_id)
        with self._lock(project_id):
            current = None
            if path.exists():
                current = self._read(path)
                actual = int(current["project"].get("revision", 0))
                if expected_revision is not None and expected_revision != actual:
                    raise ConflictError(f"Concurrent edit detected: expected revision {expected_revision}, current revision {actual}.")
                self._backup(project_id, path, actual)
            elif expected_revision not in (None, -1, 0):
                raise ConflictError("Project does not yet exist at the expected revision.")
            saved = json.loads(json.dumps(doc))
            saved["project"]["revision"] = (int(current["project"].get("revision", 0)) + 1) if current else 1
            saved["project"]["updated_at"] = datetime.now(UTC).isoformat()
            self.atomic_write(path, saved)
            if force_snapshot:
                self._backup(project_id, path, saved["project"]["revision"], label="manual")
            return saved

    def _backup(self, project_id: str, path: Path, revision: int, label: str = "autosave") -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        folder = self.backups / project_id
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{stamp}-r{revision}-{label}.json"
        shutil.copy2(path, target)
        backups = sorted(folder.glob("*.json"), reverse=True)
        for old in backups[self.backup_retention:]:
            old.unlink(missing_ok=True)
        return target

    def manual_backup(self, project_id: str) -> Path:
        path = self.project_path(project_id)
        doc = self._read(path)
        return self._backup(project_id, path, int(doc["project"].get("revision", 0)), "manual")

    def restore_backup(self, project_id: str, backup_name: str) -> dict[str, Any]:
        candidate = self.backups / project_id / Path(backup_name).name
        recovered = self._migrate_project(self._read(candidate))
        current_revision = int(recovered["project"].get("revision", 0))
        path = self.project_path(project_id)
        try:
            current, _ = self.load_project(project_id)
            current_revision = int(current["project"].get("revision", 0))
        except PersistenceError:
            # Preserve the unreadable primary for forensic recovery, then replace it
            # atomically with the selected known-valid backup.
            if path.exists():
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                folder = self.backups / project_id
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, folder / f"{stamp}-corrupt-primary.json.corrupt")
        with self._lock(project_id):
            recovered["project"]["revision"] = current_revision + 1
            recovered["project"]["updated_at"] = datetime.now(UTC).isoformat()
            self.atomic_write(path, recovered)
        return recovered

    def backup_names(self, project_id: str) -> list[str]:
        return [p.name for p in sorted((self.backups / project_id).glob("*.json"), reverse=True)]

    def proposal_path(self, project_id: str, proposal_id: str) -> Path:
        """Return a validated path in the append-only proposal snapshot store."""
        safe_project = self._safe_document_name(project_id)
        safe_proposal = self._safe_document_name(proposal_id)
        return self.proposals / safe_project / f"{safe_proposal}.json"

    def save_proposal_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> Path:
        """Commit a new immutable snapshot; an existing identity is never replaced."""
        proposal_id = str(snapshot.get("metadata", {}).get("id") or "")
        path = self.proposal_path(project_id, proposal_id)
        with self._lock(f"proposal:{project_id}:{proposal_id}"):
            if path.exists():
                raise ConflictError("Immutable proposal snapshot already exists.")
            self.atomic_write(path, json.loads(json.dumps(snapshot)))
        return path

    def load_proposal_snapshot(self, project_id: str, proposal_id: str) -> dict[str, Any]:
        """Load a detached copy so callers cannot mutate persisted history by reference."""
        return json.loads(json.dumps(self._read(self.proposal_path(project_id, proposal_id))))

    def discard_unindexed_proposal(self, project_id: str, proposal_id: str) -> None:
        """Rollback only a newly-created snapshot after its project-index commit failed."""
        path = self.proposal_path(project_id, proposal_id)
        with self._lock(f"proposal:{project_id}:{proposal_id}"):
            path.unlink(missing_ok=True)

    def list_proposal_snapshot_ids(self, project_id: str) -> list[str]:
        folder = self.proposals / self._safe_document_name(project_id)
        return [path.stem for path in sorted(folder.glob("*.json"))]

    def proposal_artifact_path(self, project_id: str, artifact_id: str) -> Path:
        return self.proposal_artifacts / self._safe_document_name(project_id) / f"{self._safe_document_name(artifact_id)}.pdf"

    def save_proposal_artifact(self, project_id: str, artifact_id: str, content: bytes) -> Path:
        path = self.proposal_artifact_path(project_id, artifact_id)
        with self._lock(f"proposal-artifact:{project_id}:{artifact_id}"):
            if path.exists():
                raise ConflictError("Immutable proposal artifact already exists.")
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            try:
                with temp.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, path)
            except OSError as exc:
                temp.unlink(missing_ok=True)
                raise PersistenceError(f"Atomic artifact save failed for {path.name}: {exc}") from exc
        return path

    def discard_unindexed_artifact(self, project_id: str, artifact_id: str) -> None:
        path = self.proposal_artifact_path(project_id, artifact_id)
        with self._lock(f"proposal-artifact:{project_id}:{artifact_id}"):
            path.unlink(missing_ok=True)

    def save_configuration(self, config: dict[str, Any]) -> None:
        self.atomic_write(self.configurations / f"{config['id']}.json", config)

    def load_configuration(self, config_id: str) -> dict[str, Any]:
        return self._read(self.configurations / f"{config_id}.json")

    def list_configurations(self) -> list[dict[str, Any]]:
        return [self._read(p) for p in sorted(self.configurations.glob("*.json"))]

    @staticmethod
    def _safe_document_name(name: str) -> str:
        safe = "".join(c for c in str(name) if c.isalnum() or c in "_-")
        if safe != name or not safe:
            raise PersistenceError("Invalid document identifier")
        return safe

    def master_data_path(self, name: str = "directory") -> Path:
        """Return the path for a named reusable master-data document."""
        return self.master_data / f"{self._safe_document_name(name)}.json"

    def load_master_data(self, name: str = "directory") -> dict[str, Any]:
        return self._read(self.master_data_path(name))

    def save_master_data(
        self,
        document: dict[str, Any],
        expected_revision: int | None,
        *,
        name: str = "directory",
    ) -> dict[str, Any]:
        """Atomically save a revisioned reusable master-data document.

        Master data has an independent revision stream and backup collection so a
        directory update can never advance or overwrite a project revision.
        """
        safe_name = self._safe_document_name(name)
        path = self.master_data_path(safe_name)
        with self._lock(f"master-data:{safe_name}"):
            current = None
            if path.exists():
                current = self._read(path)
                actual = int(current.get("revision", 0))
                if expected_revision is not None and expected_revision != actual:
                    raise ConflictError(
                        f"Concurrent master-data edit detected: expected revision "
                        f"{expected_revision}, current revision {actual}."
                    )
                self._backup_master_data(safe_name, path, actual)
            elif expected_revision not in (None, -1, 0):
                raise ConflictError("Master-data document does not yet exist at the expected revision.")
            saved = json.loads(json.dumps(document))
            saved["revision"] = int(current.get("revision", 0)) + 1 if current else 1
            saved["updated_at"] = datetime.now(UTC).isoformat()
            self.atomic_write(path, saved)
            return saved

    def _backup_master_data(self, name: str, path: Path, revision: int) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        folder = self.master_data_backups / name
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{stamp}-r{revision}.json"
        shutil.copy2(path, target)
        backups = sorted(folder.glob("*.json"), reverse=True)
        for old in backups[self.backup_retention:]:
            old.unlink(missing_ok=True)
        return target

    def master_data_backup_names(self, name: str = "directory") -> list[str]:
        safe_name = self._safe_document_name(name)
        return [
            path.name
            for path in sorted((self.master_data_backups / safe_name).glob("*.json"), reverse=True)
        ]

    def restore_master_data(self, backup_name: str, *, name: str = "directory") -> dict[str, Any]:
        """Restore a known-valid master-data backup as a new revision."""
        safe_name = self._safe_document_name(name)
        candidate = self.master_data_backups / safe_name / Path(backup_name).name
        recovered = self._read(candidate)
        path = self.master_data_path(safe_name)
        with self._lock(f"master-data:{safe_name}"):
            current = None
            if path.exists():
                try:
                    current = self._read(path)
                except PersistenceError:
                    # Retain malformed directory bytes as forensic evidence,
                    # then atomically install the selected known-valid backup.
                    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                    folder = self.master_data_backups / safe_name
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, folder / f"{stamp}-corrupt-primary.json.corrupt")
                else:
                    self._backup_master_data(safe_name, path, int(current.get("revision", 0)))
            saved = json.loads(json.dumps(recovered))
            basis_revision = int((current or recovered).get("revision", 0))
            saved["revision"] = basis_revision + 1
            saved["updated_at"] = datetime.now(UTC).isoformat()
            self.atomic_write(path, saved)
            return saved

    def historical_index_path(self, name: str) -> Path:
        return self.historical_indexes / f"{self._safe_document_name(name)}.json"

    def load_historical_index(self, name: str) -> dict[str, Any]:
        """Load a derived historical index without touching project evidence."""
        return self._read(self.historical_index_path(name))

    def save_historical_index(
        self,
        document: dict[str, Any],
        name: str,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Atomically replace a rebuildable historical index.

        Unlike project and master-data writes, this derived cache has no backup
        stream.  A malformed or missing index is safely rebuilt from immutable
        project snapshots.
        """
        safe_name = self._safe_document_name(name)
        path = self.historical_index_path(safe_name)
        with self._lock(f"historical-index:{safe_name}"):
            current_revision = 0
            if path.exists():
                try:
                    current_revision = int(self._read(path).get("revision", 0))
                except (PersistenceError, TypeError, ValueError):
                    current_revision = 0
            if expected_revision is not None and int(expected_revision) != current_revision:
                raise ConflictError(
                    f"Concurrent historical-index refresh detected: expected revision "
                    f"{expected_revision}, current revision {current_revision}."
                )
            saved = json.loads(json.dumps(document))
            saved["revision"] = current_revision + 1
            saved["updated_at"] = datetime.now(UTC).isoformat()
            self.atomic_write(path, saved)
            return saved
