"""Provider-neutral database boundary and local SQLite implementation."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol, Sequence


class DatabaseError(RuntimeError):
    pass


class DatabaseProvider(Protocol):
    """Small DB-API contract; hosted providers adapt placeholders and DDL here."""

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[Any]: ...
    def initialize(self) -> None: ...
    def is_integrity_error(self, error: BaseException) -> bool: ...


SCHEMA_MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, """
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS project_ids (
      id TEXT PRIMARY KEY, claimed_at TEXT NOT NULL, source TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS project_aliases (
      alias TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project_ids(id)
    );
    CREATE TABLE IF NOT EXISTS projects (
      id TEXT PRIMARY KEY REFERENCES project_ids(id), record_kind TEXT NOT NULL DEFAULT 'project',
      name TEXT NOT NULL, project_number TEXT, configuration_id TEXT, status TEXT,
      archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)), revision INTEGER NOT NULL CHECK (revision >= 0),
      schema_version TEXT, created_at TEXT, updated_at TEXT NOT NULL,
      document_json TEXT NOT NULL, document_sha256 TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_projects_kind_archived_name ON projects(record_kind, archived, name);
    CREATE INDEX IF NOT EXISTS ix_projects_configuration ON projects(configuration_id);
    CREATE TABLE IF NOT EXISTS project_records (
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      collection_name TEXT NOT NULL, record_id TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
      parent_record_id TEXT, cost_code TEXT, payload_json TEXT NOT NULL,
      PRIMARY KEY(project_id, collection_name, record_id), UNIQUE(project_id, collection_name, ordinal)
    );
    CREATE INDEX IF NOT EXISTS ix_project_records_collection_code ON project_records(collection_name, cost_code);
    CREATE INDEX IF NOT EXISTS ix_project_records_parent ON project_records(project_id, parent_record_id);
    CREATE TABLE IF NOT EXISTS project_components (
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      component_name TEXT NOT NULL, payload_json TEXT NOT NULL,
      PRIMARY KEY(project_id, component_name)
    );
    CREATE TABLE IF NOT EXISTS project_backups (
      id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      revision INTEGER NOT NULL, label TEXT NOT NULL, created_at TEXT NOT NULL,
      document_json TEXT NOT NULL, document_sha256 TEXT NOT NULL,
      UNIQUE(project_id, revision, label, created_at)
    );
    CREATE INDEX IF NOT EXISTS ix_project_backups_project_created ON project_backups(project_id, created_at DESC);
    CREATE TABLE IF NOT EXISTS configurations (
      id TEXT PRIMARY KEY, version INTEGER, effective_date TEXT, created_at TEXT NOT NULL,
      payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS configuration_records (
      configuration_id TEXT NOT NULL REFERENCES configurations(id) ON DELETE CASCADE,
      collection_name TEXT NOT NULL, record_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
      payload_json TEXT NOT NULL, PRIMARY KEY(configuration_id, collection_name, record_id)
    );
    CREATE INDEX IF NOT EXISTS ix_configuration_records_kind ON configuration_records(collection_name);
    CREATE TABLE IF NOT EXISTS master_documents (
      name TEXT PRIMARY KEY, revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
      payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS master_entities (
      document_name TEXT NOT NULL REFERENCES master_documents(name) ON DELETE CASCADE,
      entity_kind TEXT NOT NULL, entity_id TEXT NOT NULL, normalized_name TEXT, payload_json TEXT NOT NULL,
      PRIMARY KEY(document_name, entity_kind, entity_id)
    );
    CREATE INDEX IF NOT EXISTS ix_master_entities_search ON master_entities(entity_kind, normalized_name);
    CREATE TABLE IF NOT EXISTS master_backups (
      id TEXT PRIMARY KEY, document_name TEXT NOT NULL, revision INTEGER NOT NULL,
      created_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS historical_indexes (
      name TEXT PRIMARY KEY, revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
      payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS proposal_snapshots (
      id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      created_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
      UNIQUE(project_id, id)
    );
    CREATE INDEX IF NOT EXISTS ix_proposals_project_created ON proposal_snapshots(project_id, created_at);
    CREATE TABLE IF NOT EXISTS proposal_artifacts (
      id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      media_type TEXT NOT NULL, created_at TEXT NOT NULL, content BLOB NOT NULL, sha256 TEXT NOT NULL,
      UNIQUE(project_id, id)
    );
    CREATE TABLE IF NOT EXISTS data_migrations (
      source_key TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, target_table TEXT NOT NULL,
      target_key TEXT NOT NULL, imported_at TEXT NOT NULL, verified_at TEXT NOT NULL
    );
    """),
    (2, """
    CREATE TABLE IF NOT EXISTS persistent_documents (
      document_kind TEXT NOT NULL, name TEXT NOT NULL, updated_at TEXT NOT NULL,
      payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
      PRIMARY KEY(document_kind, name)
    );
    CREATE INDEX IF NOT EXISTS ix_persistent_documents_kind ON persistent_documents(document_kind);
    """),
    (3, """
    CREATE TABLE IF NOT EXISTS cost_code_references (
      name TEXT PRIMARY KEY, reference_id TEXT, source TEXT, source_sha256 TEXT,
      updated_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS cost_code_records (
      reference_name TEXT NOT NULL REFERENCES cost_code_references(name) ON DELETE CASCADE,
      record_id TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
      normalized_code TEXT NOT NULL, display_code TEXT, description TEXT,
      payload_json TEXT NOT NULL,
      PRIMARY KEY(reference_name, record_id), UNIQUE(reference_name, ordinal)
    );
    CREATE INDEX IF NOT EXISTS ix_cost_code_records_code ON cost_code_records(reference_name, normalized_code);
    CREATE TABLE IF NOT EXISTS application_credentials (
      name TEXT PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS legacy_migration_runs (
      migration_name TEXT PRIMARY KEY,
      status TEXT NOT NULL CHECK (status IN ('running','completed','failed')),
      source_root TEXT NOT NULL, source_manifest_sha256 TEXT,
      started_at TEXT NOT NULL, completed_at TEXT, summary_json TEXT NOT NULL
    );
    """),
)


class SQLiteProvider:
    """Windows-native, zero-network local provider using Python's SQLite driver."""

    def __init__(self, path: Path, *, timeout: float = 30.0):
        self.path = Path(path)
        self.timeout = timeout
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.transaction(write=True) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
            for version, ddl in SCHEMA_MIGRATIONS:
                if version in applied:
                    continue
                for statement in (part.strip() for part in ddl.split(";")):
                    if statement:
                        connection.execute(statement)
                connection.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (version,))

    def integrity_check(self) -> str:
        with self.transaction() as connection:
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0])

    def foreign_key_violations(self) -> Sequence[Any]:
        with self.transaction() as connection:
            return connection.execute("PRAGMA foreign_key_check").fetchall()

    @staticmethod
    def is_integrity_error(error: BaseException) -> bool:
        return isinstance(error, sqlite3.IntegrityError)
