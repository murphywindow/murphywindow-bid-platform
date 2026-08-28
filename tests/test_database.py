import json
import sqlite3

import pytest

from app.database import SQLiteProvider
from app.persistence import ConflictError, SqlStore
from app.schema import default_configuration, new_project


def configured_store(root):
    store=SqlStore(root);reference=store.ensure_packaged_cost_code_reference();store.save_configuration(default_configuration(reference));return store


def test_database_initialization_constraints_and_integrity(tmp_path):
    store = SqlStore(tmp_path)
    with store.provider.transaction() as connection:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert versions == [1, 2, 3]
    assert {"projects", "project_records", "configurations", "proposal_snapshots", "proposal_artifacts", "cost_code_references", "cost_code_records", "application_credentials", "legacy_migration_runs"} <= tables
    assert store.provider.integrity_check() == "ok"
    assert store.provider.foreign_key_violations() == []
    with pytest.raises(sqlite3.IntegrityError):
        with store.provider.transaction(write=True) as connection:
            connection.execute("INSERT INTO project_records(project_id,collection_name,record_id,ordinal,payload_json) VALUES(?,?,?,?,?)", ("missing", "quotes", "q", 0, "{}"))


def test_project_crud_is_transactional_and_relationally_projected(tmp_path):
    store = configured_store(tmp_path)
    document = new_project("Relational Bid", "Estimator", "Estimator")
    document["quotes"] = [{"id": "quo_one", "code": "08 41 13", "vendor": "Vendor", "price": "1000"}]
    saved = store.save_project(document, -1)
    with store.provider.transaction() as connection:
        project = connection.execute("SELECT name,revision,document_sha256 FROM projects WHERE id=?", (saved["project"]["id"],)).fetchone()
        quote = connection.execute("SELECT cost_code,payload_json FROM project_records WHERE project_id=? AND collection_name='quotes'", (saved["project"]["id"],)).fetchone()
    assert (project[0], project[1]) == ("Relational Bid", 1)
    assert quote[0] == "08 41 13" and json.loads(quote[1])["vendor"] == "Vendor"
    stale = json.loads(json.dumps(saved));saved["project"]["name"] = "Updated"
    store.save_project(saved, 1)
    with pytest.raises(ConflictError):
        store.save_project(stale, 1)
    assert store.backup_names(saved["project"]["id"])


def test_sqlite_transaction_rolls_back_as_a_unit(tmp_path):
    provider = SQLiteProvider(tmp_path / "rollback.db")
    with pytest.raises(RuntimeError):
        with provider.transaction(write=True) as connection:
            connection.execute("INSERT INTO project_ids(id,claimed_at,source) VALUES(?,?,?)", ("rolled-back", "now", "test"))
            raise RuntimeError("stop")
    with provider.transaction() as connection:
        assert connection.execute("SELECT 1 FROM project_ids WHERE id='rolled-back'").fetchone() is None


def test_legacy_import_is_idempotent_and_hash_verified(tmp_path):
    source = new_project("Imported", "Estimator", "Estimator")
    source_path = tmp_path / "projects" / f"{source['project']['id']}.json"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(json.dumps(source),encoding="utf-8")
    first = SqlStore(tmp_path)
    assert first.list_projects() == []
    report = first.migrate_legacy_data_once(tmp_path)
    assert report["ok"] is True and report["verified_files"] == 1
    source["project"]["name"]="Must not overwrite SQL"
    source_path.write_text(json.dumps(source),encoding="utf-8")
    second = SqlStore(tmp_path)
    assert len(second.list_projects()) == 1
    assert second.list_projects()[0]["name"] == "Imported"
    assert second.migrate_legacy_data_once(tmp_path)["already_completed"] is True
    with second.provider.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM data_migrations").fetchone()[0] == 1
        assert connection.execute("SELECT status FROM legacy_migration_runs").fetchone()[0] == "completed"


def test_runtime_crud_ignores_legacy_json_and_uses_only_sql(tmp_path):
    store=configured_store(tmp_path)
    saved=store.save_project(new_project("SQL truth","Estimator","Estimator"),-1)
    legacy=tmp_path/"projects"/f"{saved['project']['id']}.json";legacy.parent.mkdir();legacy.write_text(json.dumps({**saved,"project":{**saved["project"],"name":"Legacy overwrite"}}),encoding="utf-8")
    reopened=SqlStore(tmp_path)
    assert reopened.load_project(saved["project"]["id"])[0]["project"]["name"]=="SQL truth"
    assert reopened.legacy_migration_report(tmp_path)["changed_after_import"] == []
