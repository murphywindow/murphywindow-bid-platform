import json
import sqlite3

import pytest

from app.persistence import ConflictError, JsonStore, PersistenceError
from app.project_ids import PROJECT_ID_CAPACITY, is_project_id
from app.schema import new_project


def test_atomic_write_and_revision_snapshots(tmp_path):
    store = JsonStore(tmp_path, backup_retention=3)
    doc = new_project("Atomic", "Alice", "Estimator")
    saved1 = store.save_project(doc, -1)
    assert saved1["project"]["revision"] == 1
    assert store.load_project(doc["project"]["id"])[0]["project"]["name"] == "Atomic"
    saved1["project"]["name"] = "Atomic Two"
    saved2 = store.save_project(saved1, 1)
    assert saved2["project"]["revision"] == 2
    assert len(store.backup_names(doc["project"]["id"])) == 1
    assert store.provider.integrity_check() == "ok"
    assert store.provider.foreign_key_violations() == []


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
    with store.provider.transaction(write=True) as connection:
        connection.execute("UPDATE projects SET document_json=? WHERE id=?", ('{"partial":', doc["project"]["id"]))
    with pytest.raises(PersistenceError):
        store.load_project(doc["project"]["id"])
    recovered, backup_name = store.load_project(doc["project"]["id"], recover=True)
    assert recovered["project"]["name"] == "Recovery"
    assert "autosave" in backup_name
    restored = store.restore_backup(doc["project"]["id"], backup_name)
    assert restored["project"]["name"] == "Recovery"
    assert store.load_project(doc["project"]["id"])[0]["project"]["name"] == "Recovery"


def test_backup_retention(tmp_path):
    store = JsonStore(tmp_path, backup_retention=2)
    doc = store.save_project(new_project("Retention", "A", "Estimator"), -1)
    for i in range(5):
        doc["project"]["name"] = str(i)
        doc = store.save_project(doc, doc["project"]["revision"])
    assert len(store.backup_names(doc["project"]["id"])) == 2


def test_compact_project_id_capacity_and_collision_checked_allocation(tmp_path):
    store = JsonStore(tmp_path)
    first = store.allocate_project_id()
    assert is_project_id(first)
    assert PROJECT_ID_CAPACITY >= 100_000
    second = store.allocate_project_id()
    assert is_project_id(second)
    assert second != first
    with sqlite3.connect(store.project_id_database) as connection:
        used = {row[0] for row in connection.execute("SELECT id FROM project_ids")}
    assert {first, second} <= used
    assert store._claim_project_id(first, "collision-test") is False
    generated = {store.allocate_project_id(reserved={first, second}) for _ in range(100)}
    assert all(is_project_id(value) for value in generated)
    assert all(len(value) == 36 and value[14] == "4" and value[19] in "89ab" for value in generated)


def test_explicit_legacy_project_id_migration_updates_sql_references_and_aliases(tmp_path):
    old_id = "prj_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    new_id = "ada5bdb1-af68-495c-a86b-a9c4508558ff"
    doc = new_project("Legacy identity", "A", "Estimator", project_id=old_id)
    doc["working_branch"] = {"source_project_id": old_id}
    project_path=tmp_path / "projects" / f"{old_id}.json";project_path.parent.mkdir(parents=True);project_path.write_text(json.dumps(doc),encoding="utf-8")
    (tmp_path / "project-id-migration-v1.json").write_text(json.dumps({"status": "complete", "mapping": {old_id: new_id}}),encoding="utf-8")
    proposal_dir = tmp_path / "proposals" / old_id
    proposal_dir.mkdir(parents=True);(proposal_dir / "snapshot.json").write_text(json.dumps({"state": {"project": {"id": old_id}}}),encoding="utf-8")
    store = JsonStore(tmp_path)
    assert store.list_projects()==[]
    store.migrate_legacy_data_once(tmp_path)
    mapping = store.migrate_legacy_project_ids()
    assert mapping[old_id] == new_id
    assert is_project_id(new_id)
    migrated, _ = store.load_project(new_id)
    assert migrated["project"]["id"] == new_id
    assert migrated["working_branch"]["source_project_id"] == new_id
    assert store.load_proposal_snapshot(new_id, "snapshot")["state"]["project"]["id"] == new_id
    legacy_alias, _ = store.load_project(old_id)
    assert legacy_alias["project"]["id"] == new_id
