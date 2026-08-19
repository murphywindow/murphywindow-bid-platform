import json

import pytest

from app.custom_code_auth import (
    PASSWORD_HASH_ENV, SECRET_FILE_ENV, USERNAME_ENV,
    hash_password, verify_custom_code_credentials, verify_password,
)
from app.master_data import (
    MasterDataRepository, new_master_directory, search_master_data, seed_master_data,
    upsert_organization, upsert_person_organization_contact, upsert_text_entity,
)
from app.persistence import ConflictError, JsonStore


def history_project(project_id="prj_history_one"):
    return {
        "schema_version": "1.0.0",
        "project": {
            "id": project_id, "archived": True, "estimator": "Micah Johnson",
            "plan_source": "Architectural Bid Set", "owner_name": "North Star Properties",
            "owner_address": "100 Main Street", "architect": "Steinier Architects",
            "engineer": "Element Engineering", "general_contractor": "Northland Builders",
            "construction_manager": "Northland Builders",
        },
        "quotes": [{"id": "quo_one", "vendor": "Metro Glass Supply"}],
        "contacts": [{
            "id": "con_one", "name": "Alex Smith", "organization": "Northland Builders",
            "role": "GC", "position": "Estimator", "email": "alex@example.invalid",
            "phone": "555-0100",
        }, {
            "id": "con_two", "name": "Jamie Doe", "organization": "North Star Properties",
            "role": "Facilities Lead", "position": "Director",
        }],
    }


def test_seeded_history_survives_source_removal_and_preserves_person_at_organization():
    source = history_project()
    directory = seed_master_data([source])
    assert source == history_project()
    assert len(directory["organizations"]) == 5
    assert len(directory["person_organization_contacts"]) == 2
    assert any(row["kind"] == "contact_role" and row["display_name"] == "Facilities Lead"
               for row in directory["text_entities"])

    # Search uses the independent directory; no source project is required after seeding.
    vendor = search_master_data(directory, "metro glass", entity_kinds=["organization"])
    assert vendor["results"][0]["display_name"] == "Metro Glass Supply"
    assert vendor["results"][0]["match_type"] in {"prefix", "exact"}

    second_org = upsert_organization(directory, {
        "display_name": "Another Employer", "classifications": ["GC"]
    })
    second_contact = upsert_person_organization_contact(directory, {
        "name": "Alex Smith", "organization_id": second_org["id"], "roles": ["GC"]
    })
    first_contact = next(row for row in directory["person_organization_contacts"]
                         if row["name"] == "Alex Smith" and row["id"] != second_contact["id"])
    assert first_contact["id"] != second_contact["id"]
    assert first_contact["organization_id"] != second_contact["organization_id"]


def test_search_normalizes_case_aliases_prefix_substring_fuzzy_and_ambiguity():
    directory = new_master_directory()
    canonical = upsert_organization(directory, {
        "display_name": "Steinier Architects", "aliases": ["SAI"],
        "classifications": ["Architect"],
    })
    # Exact differently cased history resolves to the stored canonical record.
    same = upsert_organization(directory, {"display_name": "STEINIER ARCHITECTS"})
    assert same["id"] == canonical["id"]
    assert same["display_name"] == "Steinier Architects"

    assert search_master_data(directory, "steinier architects")["resolved_id"] == canonical["id"]
    assert search_master_data(directory, "sai")["resolved_id"] == canonical["id"]
    assert search_master_data(directory, "Stein")["results"][0]["match_type"] == "prefix"
    assert search_master_data(directory, "Architect")["results"][0]["match_type"] == "substring"
    fuzzy = search_master_data(directory, "Steiner Archtects")
    assert fuzzy["results"][0]["id"] == canonical["id"]
    assert "fuzzy" in fuzzy["results"][0]["match_type"]

    upsert_organization(directory, {"display_name": "Acme Glass"})
    upsert_organization(directory, {"display_name": "Acme Glazing"})
    ambiguous = search_master_data(directory, "Acme Gla")
    assert ambiguous["ambiguous"] is True
    assert len(ambiguous["results"]) >= 2
    assert ambiguous["resolved_id"] is None


def test_text_entities_are_kind_specific_and_alias_searchable():
    directory = new_master_directory()
    estimator = upsert_text_entity(directory, {
        "kind": "estimator", "display_name": "Micah Johnson", "aliases": ["MJ"]
    })
    plan_source = upsert_text_entity(directory, {
        "kind": "plan_source", "display_name": "Micah Johnson"
    })
    assert estimator["id"] != plan_source["id"]
    result = search_master_data(directory, "mj", entity_kinds=["text"])
    assert result["resolved_id"] == estimator["id"]


def test_master_directory_persistence_is_atomic_revisioned_backed_up_and_no_churn(tmp_path):
    store = JsonStore(tmp_path, backup_retention=2)
    repository = MasterDataRepository(store)
    first = repository.seed_projects([history_project()])
    assert first["revision"] == 1
    assert store.master_data_path().exists()

    unchanged = repository.seed_projects([history_project()])
    assert unchanged["revision"] == 1
    assert store.master_data_backup_names() == []

    updated = repository.load_or_create()
    upsert_organization(updated, {"display_name": "New Vendor", "classifications": ["Vendor"]})
    saved = repository.save(updated, expected_revision=1)
    assert saved["revision"] == 2
    assert len(store.master_data_backup_names()) == 1
    with pytest.raises(ConflictError, match="Concurrent master-data edit"):
        repository.save(updated, expected_revision=1)
    assert json.loads(store.master_data_path().read_text(encoding="utf-8"))["revision"] == 2

    valid_backup = store.master_data_backup_names()[0]
    store.master_data_path().write_text("{ malformed master data", encoding="utf-8")
    restored = store.restore_master_data(valid_backup)
    assert restored["schema_version"] == "1.0.0"
    assert json.loads(store.master_data_path().read_text(encoding="utf-8"))["revision"] == restored["revision"]
    corrupt = list((store.master_data_backups / "directory").glob("*.corrupt"))
    assert len(corrupt) == 1 and corrupt[0].read_text(encoding="utf-8") == "{ malformed master data"


def test_existing_project_reindexes_only_when_reusable_history_changes(tmp_path):
    repository = MasterDataRepository(JsonStore(tmp_path))
    source = history_project()
    first = repository.seed_projects([source])
    assert first["revision"] == 1

    changed = history_project()
    changed["quotes"].append({"id": "quo_two", "vendor": "New Historical Vendor"})
    second = repository.seed_projects([changed])
    assert second["revision"] == 2
    result = repository.search("new historical", entity_kinds=["organization"])
    assert result["results"][0]["display_name"] == "New Historical Vendor"

    unchanged = repository.seed_projects([changed])
    assert unchanged["revision"] == 2


def test_custom_code_credentials_use_only_hashes_and_fail_closed(tmp_path):
    password = "unit-test-secret-not-in-source"
    encoded = hash_password(password, iterations=210_000, salt=b"0123456789abcdef")
    assert password not in encoded
    assert verify_password(password, encoded) is True
    assert verify_password("wrong", encoded) is False

    environment = {USERNAME_ENV: "custom-user", PASSWORD_HASH_ENV: encoded}
    assert verify_custom_code_credentials("custom-user", password, environment=environment) is True
    assert verify_custom_code_credentials("wrong-user", password, environment=environment) is False
    assert verify_custom_code_credentials("custom-user", "wrong", environment=environment) is False
    assert verify_custom_code_credentials("custom-user", password, environment={}) is False
    assert verify_custom_code_credentials("custom-user", password, environment={USERNAME_ENV: "custom-user"}) is False

    secret_path = tmp_path / "custom-code-secret.json"
    secret_path.write_text(json.dumps({"username": "local-user", "password_hash": encoded}), encoding="utf-8")
    file_environment = {SECRET_FILE_ENV: str(secret_path)}
    result = verify_custom_code_credentials("local-user", password, environment=file_environment)
    assert result is True and isinstance(result, bool)
