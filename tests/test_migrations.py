from copy import deepcopy
import json

import pytest

from app.migrations import MigrationError, migrate_project_document, project_migration_required
from app.persistence import JsonStore


def legacy_document():
    return {
        "schema_version": "1.0.0",
        "interchange_version": "1.0.0",
        "project": {
            "id": "prj_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "revision": 7,
            "project_type": "Legacy Renovation",
            "contract_type": "Negotiated lump sum",
            "prevailing_wage_required": False,
            "bid_due_date": "2026-09-01",
            "address": "100 Main Street, Rogers, MN 55374",
        },
        "contacts": [{"id": "con_legacy", "name": "Alex", "organization": "Steinier"}],
        "cost_codes": [{"id": "ccd_legacy", "code": "08 41 13"}],
        "quotes": [{
            "id": "quo_legacy", "code": "08 41 13", "group_id": "old-group",
            "price": "1000", "surcharge_percent": ".05", "used": True,
        }],
        "takeoff_sections": [{
            "id": "sec_legacy", "lines": [{"id": "frm_legacy", "mark": "F1", "quantity": 0}],
            "material_overrides": {"mat_sealant": {"rate": "14.25", "factor": ".08"}},
        }],
        "doors": [{"id": "dor_legacy", "mark": "D1", "leaf_quantity": 0}],
        "labor_estimates": [{
            "id": "lbr_legacy", "category": "field", "quantity": 100,
            "crew": 2, "productivity": 5, "rate": "68.53", "rate_id": "legacy-rate",
        }],
        "working_estimate": {"markup_overrides": {"LAF": ".12"}},
        "estimate_revisions": [{
            "id": "rev_frozen", "immutable": True,
            "source_snapshot": {"quotes": [{"surcharge_percent": ".07"}]},
        }],
        "submissions": [{"id": "sub_frozen", "immutable": True}],
        "proposal_artifacts": [{"id": "art_frozen", "immutable": True}],
        "award": {"id": "awd_frozen", "immutable": True, "awarded_bid_snapshot": {"schema_version": "1.0.0"}},
    }


def test_active_project_migration_is_lossless_idempotent_and_leaves_history_frozen():
    source = legacy_document()
    source_before = deepcopy(source)
    frozen = deepcopy({key: source[key] for key in (
        "estimate_revisions", "submissions", "proposal_artifacts", "award"
    )})

    migrated = migrate_project_document(source)

    assert source == source_before
    assert migrated["schema_version"] == "1.4.0"
    assert migrated["interchange_version"] == "1.4.0"
    assert migrated["project"]["project_type"] == "Legacy Renovation"
    assert migrated["project"]["project_type_status"] == "legacy_unsupported"
    assert migrated["project"]["contract_type_status"] == "legacy_unsupported"
    assert migrated["project"]["wage_type"] == "Non-PW"
    assert migrated["project"]["wage_type_status"] == "current"
    assert migrated["project"]["bid_due_date"] == "2026-09-01"
    assert migrated["project"]["bid_due_date_status"] == "legacy_date_only"
    assert migrated["project"]["address"] == source["project"]["address"]
    assert migrated["project"]["address_structure_status"] == "legacy_unparsed"
    assert migrated["project"]["address_street"] == ""
    assert {key: migrated[key] for key in frozen} == frozen
    assert migrate_project_document(migrated) == migrated
    assert project_migration_required(source) is True
    assert project_migration_required(migrated) is False


def test_migration_adds_compatible_commercial_metadata_without_removing_legacy_fields():
    migrated = migrate_project_document(legacy_document())
    quote = migrated["quotes"][0]
    assert quote["group_id"] == "old-group"
    assert quote["surcharge_percent"] == ".05"
    assert quote["surcharge_type"] == "percentage"
    assert quote["surcharge_value"] == ".05"
    assert quote["credit_type"] is None and quote["square_feet_source"] == "unassigned"
    assert migrated["working_estimate"]["quote_selection_by_code"]["08 41 13"] == {
        "mode": "legacy_manual",
        "selected_quote_ids": ["quo_legacy"],
        "source": "migrated_quotes_used_flags",
    }
    override = migrated["takeoff_sections"][0]["material_overrides"]["mat_sealant"]
    assert override["rate"] == "14.25" and override["rate_override"] == "14.25"
    assert override["factor"] == ".08" and override["factor_override"] == ".08"
    assert migrated["takeoff_sections"][0]["lines"][0]["missing_quantity_acknowledged"] is False
    assert migrated["doors"][0]["missing_quantity_acknowledged"] is False
    labor = migrated["labor_estimates"][0]
    assert labor["labor_type"] == "Field"
    assert labor["man_hours"] == "10"
    assert labor["man_hours_source"] == "legacy_productivity_calculation"
    assert labor["quantity"] == 100 and labor["productivity"] == 5
    assert labor["legacy_effective_rate"] == "68.53"
    assert migrated["working_estimate"]["markup_overrides"] == {"LAF": ".12"}
    assert migrated["working_estimate"]["labor_suggestion_exclusions"] == []
    assert migrated["working_estimate"]["pending_controlled_values"] == []


def test_migration_normalizes_legacy_quote_selection_alias_without_deleting_it():
    source = legacy_document()
    source["working_estimate"]["quote_selection_modes"] = {"08 41 13": "manual"}

    migrated = migrate_project_document(source)

    assert migrated["working_estimate"]["quote_selection_modes"] == {"08 41 13": "manual"}
    assert migrated["working_estimate"]["quote_selection_by_code"]["08 41 13"] == {
        "mode": "manual",
        "selected_quote_ids": ["quo_legacy"],
        "source": "migrated_quote_selection_modes",
    }


def test_1_3_migration_normalizes_optional_alternate_names_and_markup_authority():
    source = migrate_project_document(legacy_document(), target_version="1.2.0")
    source["alternates"] = [{
        "id": "alt_1", "sequence": 1, "key": "ALT1", "name": "Alternate 1",
        "changes": {}, "calculated": {},
    }]
    source["working_estimate"]["component_markup_overrides"] = {
        "quote:quo_legacy": {"rate": ".25", "reason": "Legacy rate authority"},
    }

    migrated = migrate_project_document(source)

    assert migrated["alternates"][0]["name"] == ""
    override = migrated["working_estimate"]["component_markup_overrides"]["quote:quo_legacy"]
    assert override["mode"] == "percentage"
    assert override["value"] == ".25"
    assert override["rate"] == ".25"


def test_1_4_migration_normalizes_optional_zero_quantities_and_alt_snapshots():
    source = migrate_project_document(legacy_document(), target_version="1.3.0")
    section = source["takeoff_sections"][0]
    section.update({"tie_back_qty": 0, "backpan_lf": "0.00"})
    section["lines"][0]["quantity"] = 0
    source["doors"][0]["leaf_quantity"] = 0
    source["alternates"] = [{"id": "alt_1", "sequence": 1, "key": "ALT1", "changes": {
        "takeoff_sections": {"added": [], "removed": [], "overrides": {section["id"]: {
            "tie_back_qty": {"base_value": 0, "value": 24}
        }}}
    }}]

    migrated = migrate_project_document(source)

    section = migrated["takeoff_sections"][0]
    assert section["tie_back_qty"] is None and section["backpan_lf"] is None
    assert section["lines"][0]["quantity"] is None
    assert migrated["doors"][0]["leaf_quantity"] is None
    change = migrated["alternates"][0]["changes"]["takeoff_sections"]["overrides"][section["id"]]["tie_back_qty"]
    assert change["base_value"] is None and change["value"] == 24
    assert migrated["schema_migrations"][-1]["id"] == "project-1.3.0-to-1.4.0"


def test_unknown_schema_fails_closed():
    with pytest.raises(MigrationError, match="No supported project migration path"):
        migrate_project_document({"schema_version": "9.0.0", "project": {}})


def test_json_store_migrates_on_load_without_rewriting_the_source(tmp_path):
    store = JsonStore(tmp_path)
    source = legacy_document()
    path = store.project_path(source["project"]["id"])
    JsonStore.atomic_write(path, source)
    raw_before = path.read_bytes()

    loaded, recovered_from = store.load_project(source["project"]["id"])

    assert recovered_from is None
    assert loaded["schema_version"] == "1.4.0"
    assert loaded["project"]["revision"] == 7
    assert path.read_bytes() == raw_before
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "1.0.0"


def test_legacy_prefixed_alternate_sources_migrate_to_explicit_alt_additions():
    source = migrate_project_document(legacy_document(), target_version="1.1.0")
    source["quotes"].append({"id": "quo_alt", "code": "ALT1-08 41 13", "vendor": "Alternate Glass",
                             "price": "750", "used": True})
    source["takeoff_sections"][0]["code"] = "08 41 13"
    source["takeoff_sections"].append({"id": "sec_alt", "code": "ALT1-08 41 13", "name": "ALT frames",
                                       "definition_id": "frame-v1", "lines": [{"id": "frm_alt", "mark": "F8", "quantity": 3}],
                                       "material_overrides": {}, "tie_back_qty": 0, "backpan_lf": 0})
    source["working_estimate"]["alternate_inclusion"] = {"ALT1": True}
    source["working_estimate"]["quote_selection_by_code"]["ALT1-08 41 13"] = {
        "mode": "legacy_manual", "selected_quote_ids": ["quo_alt"],
    }
    source["working_estimate"]["labor_suggestion_exclusions"] = ["08 41 13", "ALT1-08 41 13"]
    frozen = deepcopy(source["estimate_revisions"])

    migrated = migrate_project_document(source)

    assert [row["id"] for row in migrated["quotes"]] == ["quo_legacy"]
    alternate = migrated["alternates"][0]
    assert alternate["key"] == "ALT1" and alternate["selected_for_proposal"] is True
    assert alternate["changes"]["quotes"]["added"][0]["code"] == "08 41 13"
    assert alternate["changes"]["frames"]["added"][0]["section_id"] == "sec_legacy"
    assert alternate["changes"]["frames"]["added"][0]["mark"] == "F8"
    assert [row["id"] for row in migrated["takeoff_sections"]] == ["sec_legacy"]
    assert "alternate_inclusion" not in migrated["working_estimate"]
    assert "ALT1-08 41 13" not in migrated["working_estimate"]["quote_selection_by_code"]
    assert migrated["working_estimate"]["labor_suggestion_exclusions"] == ["08 41 13"]
    assert migrated["estimate_revisions"] == frozen
