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
        self.backup_retention = backup_retention
        self._locks: dict[str, threading.Lock] = {}
        for path in (self.projects, self.backups, self.exports, self.configurations):
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
                doc = self._read(path)
                output.append(doc["project"])
            except (PersistenceError, KeyError):
                output.append({"id": path.stem, "name": path.stem, "malformed": True, "archived": False})
        return output

    def load_project(self, project_id: str, recover: bool = False) -> tuple[dict[str, Any], str | None]:
        path = self.project_path(project_id)
        try:
            return self._read(path), None
        except PersistenceError as primary_error:
            if not recover:
                raise
            candidates = sorted((self.backups / project_id).glob("*.json"), reverse=True)
            for candidate in candidates:
                try:
                    return self._read(candidate), candidate.name
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
        recovered = self._read(candidate)
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

    def save_configuration(self, config: dict[str, Any]) -> None:
        self.atomic_write(self.configurations / f"{config['id']}.json", config)

    def load_configuration(self, config_id: str) -> dict[str, Any]:
        return self._read(self.configurations / f"{config_id}.json")

    def list_configurations(self) -> list[dict[str, Any]]:
        return [self._read(p) for p in sorted(self.configurations.glob("*.json"))]
