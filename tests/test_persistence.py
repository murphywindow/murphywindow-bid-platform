import json
from pathlib import Path

import pytest

from app.persistence import ConflictError, JsonStore, PersistenceError
from app.schema import new_project


def test_atomic_write_and_revision_snapshots(tmp_path):
    store = JsonStore(tmp_path, backup_retention=3)
    doc = new_project("Atomic", "Alice", "Estimator")
    saved1 = store.save_project(doc, -1)
    assert saved1["project"]["revision"] == 1
    assert json.loads(store.project_path(doc["project"]["id"]).read_text(encoding="utf-8"))["project"]["name"] == "Atomic"
    saved1["project"]["name"] = "Atomic Two"
    saved2 = store.save_project(saved1, 1)
    assert saved2["project"]["revision"] == 2
    assert len(store.backup_names(doc["project"]["id"])) == 1
    assert not list(store.projects.glob("*.tmp"))


def test_concurrent_revision_rejected(tmp_path):
    store = JsonStore(tmp_path)
    doc = store.save_project(new_project("Conflict", "A", "Estimator"), -1)
    stale = json.loads(json.dumps(doc))
    doc["project"]["name"] = "First"
    store.save_project(doc, 1)
    stale["project"]["name"] = "Second"
    with pytest.raises(ConflictError):
        store.save_project(stale, 1)


def test_malformed_primary_recovers_latest_valid_backup(tmp_path):
    store = JsonStore(tmp_path)
    doc = store.save_project(new_project("Recovery", "A", "Estimator"), -1)
    doc["project"]["name"] = "Valid two"
    store.save_project(doc, 1)
    path = store.project_path(doc["project"]["id"])
    path.write_text('{"partial":', encoding="utf-8")
    with pytest.raises(PersistenceError):
        store.load_project(doc["project"]["id"])
    recovered, backup_name = store.load_project(doc["project"]["id"], recover=True)
    assert recovered["project"]["name"] == "Recovery"
    assert backup_name.endswith("autosave.json")
    restored = store.restore_backup(doc["project"]["id"], backup_name)
    assert restored["project"]["name"] == "Recovery"
    assert json.loads(path.read_text(encoding="utf-8"))["project"]["name"] == "Recovery"
    assert list((store.backups / doc["project"]["id"]).glob("*.json.corrupt"))


def test_interrupted_atomic_write_leaves_primary(monkeypatch, tmp_path):
    store = JsonStore(tmp_path)
    target = tmp_path / "primary.json"
    JsonStore.atomic_write(target, {"ok": 1})
    original = target.read_text()
    def broken_replace(source, destination):
        raise OSError("simulated interruption")
    monkeypatch.setattr("app.persistence.os.replace", broken_replace)
    with pytest.raises(PersistenceError):
        JsonStore.atomic_write(target, {"ok": 2})
    assert target.read_text() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_write_permission_failure_is_wrapped(monkeypatch, tmp_path):
    target = tmp_path / "x.json"
    def denied(*args, **kwargs):
        raise OSError("permission denied")
    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(PersistenceError, match="Atomic save failed"):
        JsonStore.atomic_write(target, {"x": 1})


def test_backup_retention(tmp_path):
    store = JsonStore(tmp_path, backup_retention=2)
    doc = store.save_project(new_project("Retention", "A", "Estimator"), -1)
    for i in range(5):
        doc["project"]["name"] = str(i)
        doc = store.save_project(doc, doc["project"]["revision"])
    assert len(store.backup_names(doc["project"]["id"])) == 2
