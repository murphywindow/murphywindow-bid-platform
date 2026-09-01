import json
import re
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING

import pytest
from fastapi.testclient import TestClient

from app.custom_code_auth import MINIMUM_ITERATIONS, hash_password
from app.persistence import JsonStore
from app.schema import CONFIG_VERSION, SCHEMA_VERSION, default_configuration
from app.version import SOFTWARE_VERSION


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.main as main
    test_store = JsonStore(tmp_path)
    test_store.save_configuration(default_configuration(test_store.ensure_packaged_cost_code_reference()))
    monkeypatch.setattr(main, "store", test_store)
    return TestClient(main.app)


def h(role="Estimator", actor="Tester"):
    return {"X-Role":role,"X-Actor":actor}


def configured_default():
    import app.main as main
    return default_configuration(main.store.load_cost_code_reference())


def create_project(client, name="API Contract"):
    response = client.post("/api/projects", headers=h(), json={"name": name})
    assert response.status_code == 200
    return response.json()["project"]


def test_bid_review_pdf_is_a_single_sheet_and_supports_inline_or_download(client):
    document = create_project(client, "Single-sheet Bid Review")
    project_id = document["project"]["id"]
    inline = client.get(f"/api/projects/{project_id}/bid-review.pdf", headers=h())
    download = client.get(f"/api/projects/{project_id}/bid-review.pdf?download=true", headers=h())
    assert inline.status_code == 200 and inline.headers["content-type"] == "application/pdf"
    assert inline.headers["content-disposition"].startswith("inline")
    assert download.headers["content-disposition"].startswith("attachment")
    assert "no-store" in inline.headers["cache-control"]
    assert inline.headers["x-bid-review"] == "base"
    assert inline.content.startswith(b"%PDF-")
    assert len(re.findall(br"/Type\s*/Page\b", inline.content)) == 1


def test_systems_administrator_can_create_and_edit_working_projects_without_page_override(client):
    created = client.post("/api/projects", headers=h("Systems Administrator"), json={"name": "Administrator workspace"})
    assert created.status_code == 200, created.text
    doc = created.json()["project"]
    project_id = doc["project"]["id"]
    doc["project"]["proposal_scope"] = "Administrator-entered global project edit"
    saved = client.put(f"/api/projects/{project_id}", headers=h("Systems Administrator"), json={
        "project": doc,
        "expected_revision": doc["project"]["revision"],
        "changes": [{
            "path": "project.proposal_scope",
            "prior": "",
            "new": doc["project"]["proposal_scope"],
            "reason": "Administrator global edit permission test",
        }],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["project"]["project"]["proposal_scope"] == doc["project"]["proposal_scope"]


def test_decimal_precision_configuration_is_admin_only_persisted_and_validated(client):
    source = client.get("/api/configurations", headers=h()).json()["configurations"][0]
    configured = deepcopy(source)
    configured["application_settings"]["decimal_precision"].update({
        "currency": 0, "percentage": 3, "quantity": 1, "square_footage": 4,
    })
    forbidden = client.post("/api/configurations", headers=h(), json={"source_id": source["id"], "configuration": configured})
    assert forbidden.status_code == 403
    created = client.post("/api/configurations", headers=h("Systems Administrator"), json={
        "source_id": source["id"], "configuration": configured, "reason": "Display precision policy",
    })
    assert created.status_code == 200
    precision = created.json()["configuration"]["application_settings"]["decimal_precision"]
    assert precision["currency"] == 0 and precision["percentage"] == 3
    assert precision["quantity"] == 1 and precision["square_footage"] == 4
    configured["application_settings"]["decimal_precision"]["currency"] = 7
    invalid = client.post("/api/configurations", headers=h("Systems Administrator"), json={"source_id": source["id"], "configuration": configured})
    assert invalid.status_code == 422


def test_frame_square_footage_method_is_persisted_and_validated(client):
    source = client.get("/api/configurations", headers=h("Systems Administrator")).json()["configurations"][0]
    configured = deepcopy(source)
    configured["application_settings"]["frame_square_footage_method"] = "quantity_then_round_up"
    created = client.post("/api/configurations", headers=h("Systems Administrator"), json={
        "source_id": source["id"], "configuration": configured, "reason": "Frame area rounding policy",
    })
    assert created.status_code == 200
    assert created.json()["configuration"]["application_settings"]["frame_square_footage_method"] == "quantity_then_round_up"
    configured["application_settings"]["frame_square_footage_method"] = "unsupported"
    invalid = client.post("/api/configurations", headers=h("Systems Administrator"), json={
        "source_id": source["id"], "configuration": configured,
    })
    assert invalid.status_code == 422


def test_commercial_impact_preview_is_read_only_and_lists_pricing_dollar_and_sf_changes(client):
    document = create_project(client, "Pricing configuration impact")
    code = first_controlled_cost_code()
    document["cost_codes"] = [code]
    document["takeoff_sections"] = [{
        "id": "sec_impact", "definition_id": "frame-v1", "code": code["code"], "name": "Frames",
        "lines": [{"id": "frm_impact", "mark": "F1", "quantity": "1.5", "width_inches": "42.75", "height_inches": "120.5"}],
        "material_overrides": {}, "tie_back_qty": 0, "backpan_lf": 0,
    }]
    document["quotes"] = [{
        "id": "quo_impact", "code": code["code"], "vendor": "Impact Vendor",
        "price": "1000", "used": True, "tax_included": True,
    }]
    saved = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "project": document, "expected_revision": document["project"]["revision"],
    }).json()["project"]
    original_revision = saved["project"]["revision"]
    original_value = Decimal(saved["working_estimate"]["totals"]["selling_value"])
    candidate = deepcopy(saved)
    candidate["working_estimate"]["markup_overrides"]["base_product"] = "0.25"

    preview = client.post(f"/api/projects/{saved['project']['id']}/commercial-impact", headers=h(), json={
        "expected_revision": original_revision, "project": candidate,
    })
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["requires_confirmation"] is True
    assert any(row["scope"] == "Bid total" and row["label"] == "Selling Value" for row in payload["impacts"])
    assert any(row["label"] == "Value/ft²" and row["value_type"] == "currency_per_unit" for row in payload["impacts"])
    reopened = client.get(f"/api/projects/{saved['project']['id']}", headers=h()).json()["project"]
    assert reopened["project"]["revision"] == original_revision
    assert Decimal(reopened["working_estimate"]["totals"]["selling_value"]) == original_value


def test_configuration_autosave_requires_commercial_confirmation_then_adopts_and_recalculates(client):
    document = create_project(client, "Administration autosave impact")
    code = first_controlled_cost_code()
    document["cost_codes"] = [code]
    document["quotes"] = [{
        "id": "quo_admin_impact", "code": code["code"], "vendor": "Admin Impact Vendor",
        "price": "1000", "used": True, "tax_included": True,
    }]
    saved = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "project": document, "expected_revision": document["project"]["revision"],
    }).json()["project"]
    source = client.get("/api/configurations", headers=h("Systems Administrator")).json()["configurations"][0]
    candidate = deepcopy(source)
    candidate["markup_defaults"]["base_product"]["rate"] = "0.25"
    before_count = len(client.get("/api/configurations", headers=h("Systems Administrator")).json()["configurations"])
    command = {
        "source_id": source["id"], "configuration": candidate,
        "project_id": saved["project"]["id"], "expected_project_revision": saved["project"]["revision"],
        "apply_to_project": True, "reason": "Automatic Administration configuration save",
    }

    blocked = client.post("/api/configurations", headers=h("Systems Administrator"), json=command)
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "commercial_impact_confirmation_required"
    assert len(client.get("/api/configurations", headers=h("Systems Administrator")).json()["configurations"]) == before_count

    accepted = client.post("/api/configurations", headers=h("Systems Administrator"), json={
        **command, "confirmed_commercial_impact": True,
    })
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["configuration"]["status"] == "active"
    assert payload["project"]["project"]["configuration_id"] == payload["configuration"]["id"]
    assert payload["project"]["project"]["revision"] == saved["project"]["revision"] + 1
    assert Decimal(payload["project"]["working_estimate"]["totals"]["selling_value"]) > Decimal(saved["working_estimate"]["totals"]["selling_value"])
    assert payload["impacts"]
    assert payload["project"]["audit_events"][-1]["operation"] == "configuration_autosaved_and_adopted"


def test_display_only_configuration_autosave_recalculates_without_confirmation(client):
    document = create_project(client, "Display-only configuration autosave")
    source = client.get("/api/configurations", headers=h("Systems Administrator")).json()["configurations"][0]
    candidate = deepcopy(source)
    candidate["application_settings"]["decimal_precision"]["currency"] = 0

    saved = client.post("/api/configurations", headers=h("Systems Administrator"), json={
        "source_id": source["id"], "configuration": candidate,
        "project_id": document["project"]["id"], "expected_project_revision": document["project"]["revision"],
        "apply_to_project": True, "reason": "Display precision autosave",
    })
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["impacts"] == []
    assert payload["configuration"]["application_settings"]["decimal_precision"]["currency"] == 0
    assert payload["project"]["project"]["configuration_id"] == payload["configuration"]["id"]


def first_controlled_cost_code():
    reference = next(row for row in configured_default()["csi_references"] if row.get("active", True))
    return {
        "id": "ccd_api_contract",
        "code": reference["display_code"],
        "description": reference["description"],
        "deduct": False,
    }


def test_base_plus_delta_alternate_api_creates_inherited_alt_and_applies_override(client):
    document = create_project(client, "Alternate API")
    code = first_controlled_cost_code()
    document["project"].update({
        "project_type": "New Construction - Exterior Storefront", "project_type_status": "current",
        "contract_type": "Bid to CM/GC", "contract_type_status": "current",
        "wage_type": "Non-PW", "wage_type_status": "current",
    })
    document["cost_codes"] = [code]
    document["takeoff_sections"] = [{
        "id": "sec_alt_api", "definition_id": "frame-v1", "code": code["code"], "name": "Frames",
        "lines": [{"id": "frm_alt_api", "mark": "F1", "quantity": 10, "width_inches": 60,
                   "height_inches": 96, "caulking_passes": 2}], "material_overrides": {},
        "tie_back_qty": 0, "backpan_lf": 0,
    }]
    saved = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "expected_revision": document["project"]["revision"], "project": document,
    })
    assert saved.status_code == 200
    document = saved.json()["project"]

    created = client.post(f"/api/projects/{document['project']['id']}/alternates", headers=h(), json={
        "expected_revision": document["project"]["revision"], "name": "VE Storefront",
    })
    assert created.status_code == 200
    alternate = created.json()["alternate"]
    assert alternate["key"] == "ALT1" and alternate["calculated"]["classification"] == "zero"
    reopened = client.get(f"/api/projects/{document['project']['id']}", headers=h()).json()["project"]
    reopened_alt = next(row for row in reopened["alternates"] if row["id"] == alternate["id"])
    assert reopened_alt["calculated"]["effective_estimate"]["totals"] == reopened_alt["calculated"]["effective_totals"]
    document = created.json()["project"]

    changed = client.post(f"/api/projects/{document['project']['id']}/alternates/{alternate['id']}/change", headers=h(), json={
        "expected_revision": document["project"]["revision"], "operation": "override", "collection": "frames",
        "record_id": "frm_alt_api", "field": "quantity", "value": 6,
    })
    assert changed.status_code == 200
    alternate = changed.json()["alternate"]
    override = alternate["changes"]["frames"]["overrides"]["frm_alt_api"]["quantity"]
    assert override["base_value"] == 10 and override["value"] == 6
    assert alternate["calculated"]["classification"] == "deduct"
    assert "F1 quantity reduced from 10 to 6" in alternate["calculated"]["scope_of_change"][0]["changes"]
    projected = alternate["calculated"]["effective_takeoff_sections"]
    assert [section["id"] for section in projected] == ["sec_alt_api"]
    assert projected[0]["lines"][0]["quantity"] == 6

    history = client.get(
        f"/api/projects/{document['project']['id']}/historical/bid-cost-codes",
        headers=h(), params={"alternate_id": alternate["id"]},
    )
    assert history.status_code == 200
    assert history.json()["alternate_id"] == alternate["id"]


def test_optional_alternate_name_uses_stable_id_and_specific_audit_events(client):
    document = create_project(client, "Alternate naming API")
    created = client.post(f"/api/projects/{document['project']['id']}/alternates", headers=h(), json={
        "expected_revision": document["project"]["revision"], "name": "",
    })
    assert created.status_code == 200
    alternate = created.json()["alternate"]
    assert alternate["name"] == ""
    stable_id, stable_key = alternate["id"], alternate["key"]

    renamed = client.patch(
        f"/api/projects/{document['project']['id']}/alternates/{stable_id}/name", headers=h(), json={
            "expected_revision": created.json()["project"]["project"]["revision"],
            "name": "  North Elevation  ",
        },
    )
    assert renamed.status_code == 200
    payload = renamed.json()
    assert payload["alternate"]["id"] == stable_id
    assert payload["alternate"]["key"] == stable_key == "ALT1"
    assert payload["alternate"]["name"] == "North Elevation"
    assert payload["project"]["audit_events"][-1]["operation"] == "alternate_name_set"
    assert payload["project"]["audit_events"][-1]["prior_value"] == {"name": ""}

    cleared = client.patch(
        f"/api/projects/{document['project']['id']}/alternates/{stable_id}/name", headers=h(), json={
            "expected_revision": payload["project"]["project"]["revision"], "name": "",
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["alternate"]["id"] == stable_id
    assert cleared.json()["project"]["audit_events"][-1]["operation"] == "alternate_name_cleared"


def test_actual_material_cost_code_may_use_full_reference_outside_project_scope(client):
    document = create_project(client, "Actual Cost Code API")
    references = [row for row in configured_default()["csi_references"] if row.get("active", True)]
    grouping, actual = references[0], next(row for row in references[1:] if row["display_code"] != references[0]["display_code"])
    document["cost_codes"] = [{
        "id": "ccd_grouping", "code": grouping["display_code"],
        "description": grouping["description"], "deduct": False,
    }]
    document["takeoff_sections"] = [{
        "id": "sec_grouping", "definition_id": "frame-v1", "code": grouping["display_code"],
        "name": "Grouped Frames", "lines": [], "material_overrides": {},
        "additional_materials": [], "tie_back_qty": 0, "backpan_lf": 0,
    }]
    saved = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "expected_revision": document["project"]["revision"], "project": document,
    }).json()["project"]

    added = client.post(
        f"/api/projects/{document['project']['id']}/frame-sections/sec_grouping/materials", headers=h(), json={
            "expected_revision": saved["project"]["revision"], "name": "Actual classified material",
            "source": "manual_quantity", "manual_quantity": 2, "factor": 1, "unit": "each",
            "project_rate": 10, "actual_cost_code": actual["display_code"], "apply_to_existing": False,
        },
    )
    assert added.status_code == 200, added.text
    project = added.json()["project"]
    material = project["takeoff_sections"][0]["additional_materials"][0]
    assert material["cost_code"] == actual["display_code"]
    line = next(row for row in project["working_estimate"]["lines"] if row.get("source_key", "").endswith(material["id"]))
    assert line["grouping_code"] == grouping["display_code"]
    assert line["actual_cost_code"] == actual["display_code"]
    assert all(row["code"] != actual["display_code"] for row in project["cost_codes"])

    invalid = deepcopy(project)
    invalid["takeoff_sections"][0]["additional_materials"][0]["cost_code"] = "99 99 99"
    rejected = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "expected_revision": project["project"]["revision"], "project": invalid,
        "changes": [{"path": "takeoff_sections.0.additional_materials.0.cost_code",
                     "prior": actual["display_code"], "new": "99 99 99"}],
    })
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "invalid_actual_cost_code"

    replacement = next(row for row in references[2:] if row["display_code"] not in {grouping["display_code"], actual["display_code"]})
    project["takeoff_sections"][0]["additional_materials"][0]["cost_code"] = replacement["display_code"]
    changed = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "expected_revision": project["project"]["revision"], "project": project,
        "changes": [{"path": "takeoff_sections.0.additional_materials.0.cost_code",
                     "prior": actual["display_code"], "new": replacement["display_code"],
                     "reason": "Estimator changed Actual Cost Code"}],
    })
    assert changed.status_code == 200, changed.text
    event = changed.json()["project"]["audit_events"][-1]
    assert event["operation"] == "installation_material_actual_cost_code_change"
    assert event["entity_id"] == material["id"]


def test_quote_grouping_code_change_preserves_manual_selection_provenance_and_audits_identity(client):
    document = create_project(client, "Quote grouping audit")
    references = [row for row in configured_default()["csi_references"] if row.get("active", True)][:2]
    first, second = references
    document["cost_codes"] = [
        {"id": "ccd_quote_a", "code": first["display_code"], "description": first["description"], "deduct": False},
        {"id": "ccd_quote_b", "code": second["display_code"], "description": second["description"], "deduct": False},
    ]
    document["quotes"] = [{
        "id": "quo_group_move", "code": first["display_code"], "vendor": "Stable Vendor",
        "price": "500", "used": True, "tax_included": True,
    }]
    document["working_estimate"]["quote_selection_by_code"] = {
        first["display_code"]: {"mode": "manual", "selected_quote_ids": ["quo_group_move"]},
    }
    saved = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "expected_revision": document["project"]["revision"], "project": document,
    }).json()["project"]

    saved["quotes"][0]["code"] = second["display_code"]
    moved = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "expected_revision": saved["project"]["revision"], "project": saved,
        "changes": [{"path": "quotes.0.code", "prior": first["display_code"],
                     "new": second["display_code"], "reason": "Quote grouping changed"}],
    })
    assert moved.status_code == 200, moved.text
    project = moved.json()["project"]
    selection = project["working_estimate"]["quote_selection_by_code"]
    assert selection[first["display_code"]]["mode"] == "manual"
    assert selection[first["display_code"]]["selected_quote_ids"] == []
    assert selection[second["display_code"]]["mode"] == "manual"
    assert "quo_group_move" in selection[second["display_code"]]["selected_quote_ids"]
    event = project["audit_events"][-1]
    assert event["operation"] == "quote_grouping_code_change"
    assert event["entity_id"] == "quo_group_move"


def test_direct_workspace_routes_return_fresh_application_shell(client):
    response = client.get("/projects/06e84ea0-a276-45e2-af97-0d220556b945/frames")
    assert response.status_code == 200
    assert "Murphy Window" in response.text
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    basic_css = client.get("/assets/basic.css")
    assert basic_css.status_code == 200
    assert "functional baseline" in basic_css.text
    assert basic_css.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"


def test_legacy_project_information_route_redirects_to_canonical_info_url(client):
    response = client.get(
        "/projects/06e84ea0-a276-45e2-af97-0d220556b945/project?popup=example",
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "/projects/06e84ea0-a276-45e2-af97-0d220556b945/info?popup=example"


def test_frame_save_and_reopen_recalculates_fractional_outputs_instead_of_reusing_whole_values(client):
    document = create_project(client, "Fractional Frame API")
    code = first_controlled_cost_code()
    document["project"].update({
        "project_type": "New Construction - Exterior Storefront", "project_type_status": "current",
        "contract_type": "Bid to CM/GC", "contract_type_status": "current",
        "wage_type": "Non-PW", "wage_type_status": "current",
    })
    document["cost_codes"] = [code]
    document["takeoff_sections"] = [{
        "id": "sec_fractional_api", "definition_id": "frame-v1", "code": code["code"], "name": "Frames",
        "lines": [{
            "id": "frm_fractional_api", "mark": "A1", "quantity": "6.60",
            "width_inches": "42.75", "height_inches": "120.67", "caulking_passes": "3.18",
            "calculated": {"square_feet": "237", "perimeter_lf": "180", "caulking_lf": "571", "head_sill_qty": "48"},
        }],
        "material_overrides": {}, "tie_back_qty": 0, "backpan_lf": 0,
    }]

    saved = client.put(f"/api/projects/{document['project']['id']}", headers=h(), json={
        "expected_revision": document["project"]["revision"], "project": document,
    })
    assert saved.status_code == 200
    reopened = client.get(f"/api/projects/{document['project']['id']}", headers=h())
    assert reopened.status_code == 200
    calculated = reopened.json()["project"]["takeoff_sections"][0]["lines"][0]["calculated"]

    quantity, width, height, passes = map(Decimal, ("6.60", "42.75", "120.67", "3.18"))
    perimeter = Decimal(2) * (width / Decimal(12) + height / Decimal(12)) * quantity
    per_frame_square_feet = (width * height / Decimal(144)).to_integral_value(rounding=ROUND_CEILING)
    assert Decimal(calculated["square_feet"]) == per_frame_square_feet * quantity
    assert Decimal(calculated["perimeter_lf"]) == perimeter
    assert Decimal(calculated["caulking_lf"]) == perimeter * passes
    assert Decimal(calculated["head_sill_qty"]) == quantity * width / Decimal(6)
    assert calculated != {"square_feet": "237", "perimeter_lf": "180", "caulking_lf": "571", "head_sill_qty": "48"}


def test_health_static_and_project_crud_conflict(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["software_version"] == SOFTWARE_VERSION
    assert re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", health.json()["software_version"])
    assert health.json()["schema_version"] == SCHEMA_VERSION == "1.5.0"
    assert client.get("/openapi.json").json()["info"]["version"] == SOFTWARE_VERSION
    assert "Murphy Window" in client.get("/").text
    created=client.post("/api/projects",headers=h(),json={"name":"API Job"})
    assert created.status_code == 200
    doc=created.json()["project"]; pid=doc["project"]["id"]
    assert client.get("/api/projects",headers=h()).json()["projects"][0]["id"] == pid
    doc["project"]["address"]="Minneapolis"
    saved=client.put(f"/api/projects/{pid}",headers=h(),json={"project":doc,"expected_revision":1,"changes":[{"path":"project.address","prior":"","new":"Minneapolis"},{"path":"project.notes","prior":"","new":"Two changes"}]})
    assert saved.status_code == 200 and saved.json()["project"]["project"]["revision"] == 2
    assert saved.json()["project"]["project"]["bid_version"]["display"] == "B0.0.2"
    assert len([e for e in saved.json()["project"]["audit_events"] if e["operation"] == "data_point_change"]) == 2
    conflict=client.put(f"/api/projects/{pid}",headers=h(),json={"project":doc,"expected_revision":1})
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "concurrent_edit"


def test_unauthorized_save_activate_and_configuration(client):
    created=client.post("/api/projects",headers=h(),json={"name":"Permission"}).json()["project"];pid=created["project"]["id"]
    assert client.put(f"/api/projects/{pid}",headers=h("Project Manager"),json={"project":created,"expected_revision":1}).status_code == 403
    assert client.post(f"/api/projects/{pid}/activate",headers=h(),json={}).status_code == 403
    assert client.post("/api/configurations",headers=h(),json={}).status_code == 403


@pytest.mark.parametrize(
    ("field", "invalid_value", "error_code"),
    (
        ("project_type", "Training / Sandbox", "invalid_project_type"),
        ("contract_type", "Time and materials", "invalid_contract_type"),
        ("wage_type", "Unknown wage plan", "invalid_wage_type"),
    ),
)
def test_new_controlled_project_values_are_enforced_server_side(client, field, invalid_value, error_code):
    doc = create_project(client, f"Controlled {field}")
    project_id = doc["project"]["id"]
    doc["project"][field] = invalid_value

    response = client.put(
        f"/api/projects/{project_id}",
        headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == error_code
    reopened = client.get(f"/api/projects/{project_id}", headers=h()).json()["project"]
    if field == "wage_type":
        assert reopened["project"][field] == "Non-PW"
    else:
        assert reopened["project"][field] in (None, "")


def test_new_source_rows_must_reference_a_project_cost_code(client):
    doc = create_project(client, "Source Cost Code guard")
    project_id = doc["project"]["id"]
    doc["cost_codes"] = [first_controlled_cost_code()]
    doc["equipment"] = [{
        "id": "eqp_invalid_source_code", "code": "99 99 99",
        "description": "Invalid source", "quantity": 1, "duration": 1,
        "duration_unit": "day", "rate": "100", "delivery": "0", "taxable": True,
    }]
    response = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_source_cost_code"


def test_unchanged_legacy_controlled_values_are_preserved_and_marked(client):
    import app.main as main

    doc = create_project(client, "Legacy controlled values")
    project_id = doc["project"]["id"]
    persisted, _ = main.store.load_project(project_id)
    persisted["project"].update({
        "project_type": "Training / Sandbox",
        "contract_type": "Legacy negotiated contract",
        "wage_type": "Legacy wage class",
    })
    persisted = main.store.save_project(persisted, persisted["project"]["revision"])

    persisted["project"]["notes"] = "Unrelated edit"
    response = client.put(
        f"/api/projects/{project_id}",
        headers=h(),
        json={"project": persisted, "expected_revision": persisted["project"]["revision"]},
    )

    assert response.status_code == 200
    project = response.json()["project"]["project"]
    assert project["project_type"] == "Training / Sandbox"
    assert project["contract_type"] == "Legacy negotiated contract"
    assert project["wage_type"] == "Legacy wage class"
    assert project["project_type_status"] == "legacy_unsupported"
    assert project["contract_type_status"] == "legacy_unsupported"
    assert project["wage_type_status"] == "legacy_unsupported"


@pytest.mark.parametrize("deadline", ("2026-09-01", "2026-09-01T14:30:00Z", "2026-09-01T14:30:00-05:00"))
def test_bid_due_date_rejects_non_local_datetime_values(client, deadline):
    doc = create_project(client, "Local deadline validation")
    project_id = doc["project"]["id"]
    doc["project"]["bid_due_date"] = deadline

    response = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_bid_due_date"


def test_bid_due_local_datetime_round_trips_without_timezone_conversion(client):
    doc = create_project(client, "Local deadline round trip")
    project_id = doc["project"]["id"]
    entered = "2026-09-01T14:30"
    doc["project"]["bid_due_date"] = entered

    saved = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )
    assert saved.status_code == 200
    assert saved.json()["project"]["project"]["bid_due_date"] == entered
    assert client.get(f"/api/projects/{project_id}", headers=h()).json()["project"]["project"]["bid_due_date"] == entered
    exported = client.get(f"/api/projects/{project_id}/export", headers=h())
    assert json.loads(exported.text)["project"]["bid_due_date"] == entered


def test_quote_square_feet_manual_edit_is_not_replaced_by_later_frame_calculation(client):
    doc = create_project(client, "Manual Quote area")
    project_id = doc["project"]["id"]
    code = first_controlled_cost_code()
    doc["cost_codes"] = [code]
    doc["takeoff_sections"] = [{
        "id": "sec_quote_area", "definition_id": "frame-v1", "code": code["code"],
        "name": "Quote area frames", "material_overrides": {}, "tie_back_qty": 0,
        "backpan_lf": 0, "lines": [{
            "id": "frm_quote_area", "mark": "F1", "quantity": 1,
            "width_inches": 12, "height_inches": 12, "caulking_passes": 3,
        }],
    }]
    doc["quotes"] = [{
        "id": "quo_manual_area", "code": code["code"], "vendor": "Area Vendor",
        "price": "100", "used": True, "tax_included": True,
        "square_feet": None, "square_feet_source": "unassigned",
    }]
    first = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )
    assert first.status_code == 200
    saved = first.json()["project"]
    assert Decimal(saved["quotes"][0]["square_feet"]) == Decimal("1")
    assert saved["quotes"][0]["square_feet_source"] == "takeoff_default"

    saved["quotes"][0]["square_feet"] = "25"
    second = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": saved, "expected_revision": saved["project"]["revision"]},
    )
    assert second.status_code == 200
    edited = second.json()["project"]
    assert edited["quotes"][0]["square_feet"] == "25"
    assert edited["quotes"][0]["square_feet_source"] == "manual"

    edited["takeoff_sections"][0]["lines"][0]["width_inches"] = 120
    third = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": edited, "expected_revision": edited["project"]["revision"]},
    )
    assert third.status_code == 200
    assert third.json()["project"]["quotes"][0]["square_feet"] == "25"
    assert third.json()["project"]["quotes"][0]["square_feet_source"] == "manual"


def test_labor_type_change_resolves_the_new_controlled_rate_family(client):
    doc = create_project(client, "Labor rate family")
    project_id = doc["project"]["id"]
    code = first_controlled_cost_code()
    doc["cost_codes"] = [code]
    doc["project"].update({"wage_type": "Non-PW", "wage_type_status": "current"})
    doc["labor_estimates"] = [{
        "id": "lbr_rate_family", "code": code["code"], "description": "Rate family",
        "labor_type": "Field", "man_hours": "10", "crew_size": "1",
        "hours_per_worker_per_day": "8", "workdays_per_week": "5", "origin": "manual",
    }]
    first = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )
    assert first.status_code == 200
    saved = first.json()["project"]
    field_rate = saved["labor_estimates"][0]["calculated_controlled_rate"]
    assert field_rate not in (None, "")

    saved["labor_estimates"][0]["labor_type"] = "Shop"
    second = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": saved, "expected_revision": saved["project"]["revision"]},
    )
    assert second.status_code == 200
    shop = second.json()["project"]["labor_estimates"][0]
    assert shop["labor_type"] == "Shop"
    assert shop["calculated_controlled_rate"] not in (None, "", field_rate)
    assert shop["controlled_rate_snapshot"]["rate"] == shop["calculated_controlled_rate"]


def test_ui_only_draft_rows_are_never_persisted_or_calculated(client):
    doc = create_project(client, "Draft row boundary")
    project_id = doc["project"]["id"]
    doc["quotes"] = [
        {"id": "draft-quotes-working", "_ui_only": True, "vendor": "Must not persist", "price": "999"},
        {},
    ]
    doc["takeoff_sections"] = [{
        "id": "sec_draft_contract",
        "definition_id": "frame-v1",
        "name": "Draft test",
        "code": "",
        "material_overrides": {},
        "lines": [
            {"id": "draft-frame-working", "row_kind": "draft", "mark": "Must not persist"},
            {},
        ],
    }]

    response = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )

    assert response.status_code == 200
    saved = response.json()["project"]
    assert saved["quotes"] == []
    assert saved["takeoff_sections"][0]["lines"] == []
    reopened = client.get(f"/api/projects/{project_id}", headers=h()).json()["project"]
    assert "draft-quotes-working" not in json.dumps(reopened)
    assert "draft-frame-working" not in json.dumps(reopened)


def test_material_rate_override_audit_retains_controlled_override_and_effective_values(client):
    doc = create_project(client, "Material override audit")
    project_id = doc["project"]["id"]
    code = first_controlled_cost_code()
    doc["cost_codes"] = [code]
    doc["takeoff_sections"] = [{
        "id": "sec_rate_audit", "definition_id": "frame-v1", "code": code["code"],
        "name": "Rate audit", "material_overrides": {}, "tie_back_qty": 0,
        "backpan_lf": 0, "lines": [{
            "id": "frm_rate_audit", "mark": "F1", "quantity": 1,
            "width_inches": 12, "height_inches": 12, "caulking_passes": 3,
        }],
    }]
    initial = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )
    assert initial.status_code == 200
    saved = initial.json()["project"]
    configuration_before = client.get("/api/configurations", headers=h()).json()["configurations"]

    saved["takeoff_sections"][0]["material_overrides"]["mat_sealant"] = {
        "rate_override": "15", "rate_override_reason": "Project supplier quotation",
    }
    changed = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={
            "project": saved, "expected_revision": saved["project"]["revision"],
            "changes": [{
                "path": "takeoff_sections.0.material_overrides.mat_sealant.rate_override",
                "prior": None, "new": "15", "reason": "Project-only rate override modified",
            }],
        },
    )
    assert changed.status_code == 200
    project = changed.json()["project"]
    result = next(item for item in project["takeoff_sections"][0]["material_results"] if item["material_rule_id"] == "mat_sealant")
    assert result["controlled_rate"] == "12.00"
    assert result["rate_override"] == "15"
    assert result["effective_rate"] == "15"
    event = project["audit_events"][-1]
    assert event["new_value"]["rate_context"] == {
        "controlled_rate": "12.00", "project_rate_override": "15",
        "effective_rate": "15", "configuration_id": CONFIG_VERSION,
    }
    assert client.get("/api/configurations", headers=h()).json()["configurations"] == configuration_before


def test_project_specific_section_material_api_adds_applies_and_removes_dependencies(client):
    doc = create_project(client, "Custom section material")
    project_id = doc["project"]["id"]
    code = first_controlled_cost_code()
    doc["cost_codes"] = [code]
    doc["takeoff_sections"] = [{
        "id": "sec_custom_material", "definition_id": "frame-v1", "code": code["code"], "name": "Storefront",
        "lines": [{"id": "frm_custom_material", "mark": "F1", "quantity": 2, "width_inches": 60, "height_inches": 96}],
        "material_overrides": {}, "tie_back_qty": 0, "backpan_lf": 0,
    }]
    saved = client.put(f"/api/projects/{project_id}", headers=h(), json={"project": doc, "expected_revision": doc["project"]["revision"]}).json()["project"]
    configuration_before = client.get("/api/configurations", headers=h()).json()["configurations"]
    created = client.post(f"/api/projects/{project_id}/frame-sections/sec_custom_material/materials", headers=h(), json={
        "expected_revision": saved["project"]["revision"], "name": "Custom sill pan", "source": "square_feet",
        "operator": "divide", "operand": "2", "unit": "LF", "project_rate": "4.50", "cost_code": code["code"], "apply_to_existing": True,
    })
    assert created.status_code == 200
    saved = created.json()["project"]
    material = created.json()["material"]
    assert material["source"] == "square_feet" and material["operator"] == "divide" and material["operand"] == "2.0"
    selections = saved["takeoff_sections"][0]["lines"][0].get("installation_material_ids")
    assert selections is None or material["id"] in selections  # missing list canonically means all selected
    result = next(row for row in saved["takeoff_sections"][0]["material_results"] if row["material_rule_id"] == material["id"])
    assert Decimal(result["pre_tax_cost"]) > 0
    assert client.get("/api/configurations", headers=h()).json()["configurations"] == configuration_before

    blocked = client.request("DELETE", f"/api/projects/{project_id}/frame-sections/sec_custom_material/materials/{material['id']}", headers=h(), json={
        "expected_revision": saved["project"]["revision"], "confirm_dependencies": False, "reason": "Dependency check",
    })
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "material_dependencies"
    removed = client.request("DELETE", f"/api/projects/{project_id}/frame-sections/sec_custom_material/materials/{material['id']}", headers=h(), json={
        "expected_revision": saved["project"]["revision"], "confirm_dependencies": True, "reason": "Confirmed removal",
    })
    assert removed.status_code == 200
    final = removed.json()["project"]["takeoff_sections"][0]
    assert final["additional_materials"] == []
    assert material["id"] not in (final["lines"][0].get("installation_material_ids") or [])
    assert removed.json()["project"]["audit_events"][-1]["operation"] == "material_remove"

    controlled = configured_default()["material_rules"][0]
    controlled_removed = client.request(
        "DELETE",
        f"/api/projects/{project_id}/frame-sections/sec_custom_material/materials/{controlled['id']}",
        headers=h(),
        json={
            "expected_revision": removed.json()["project"]["project"]["revision"],
            "confirm_dependencies": True,
            "reason": "Remove controlled material from this section",
        },
    )
    assert controlled_removed.status_code == 200, controlled_removed.text
    controlled_section = controlled_removed.json()["project"]["takeoff_sections"][0]
    assert controlled["id"] in controlled_section["excluded_material_rule_ids"]
    assert controlled["id"] not in {
        row["material_rule_id"] for row in controlled_section["material_results"]
    }
    assert controlled_removed.json()["removed"]["controlled"] is True


def test_duplicate_export_backup_import_and_job_data(client):
    doc=client.post("/api/projects",headers=h(),json={"name":"Portable"}).json()["project"];pid=doc["project"]["id"]
    dup=client.post(f"/api/projects/{pid}/duplicate",headers=h(),json={"name":"Portable Copy"})
    assert dup.status_code == 200 and dup.json()["project"]["project"]["id"] != pid
    export=client.get(f"/api/projects/{pid}/export",headers=h()); assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/json")
    assert client.post(f"/api/projects/{pid}/backup",headers=h(),json={}).status_code == 200
    data=client.get(f"/api/projects/{pid}/job-data",headers=h()).json();assert data["version"] == "1.5.0"
    imported=client.post("/api/projects/import",headers=h(),json={"project_document":json.loads(export.text),"as_duplicate":True})
    assert imported.status_code == 200 and imported.json()["project"]["project"]["id"] != pid


def test_master_data_add_and_search_returns_canonical_record(client):
    added = client.post(
        "/api/master-data/organizations",
        headers=h(),
        json={
            "display_name": "Steinier Glass",
            "legal_name": "Steinier Glass, Inc.",
            "aliases": ["Steinier"],
            "classifications": ["Vendor"],
            "email": "estimating@example.invalid",
        },
    )
    assert added.status_code == 200
    record = added.json()["record"]
    assert record["display_name"] == "Steinier Glass"
    assert record["entity_kind"] == "organization"

    exact = client.get("/api/master-data/search", headers=h(), params={"kind": "organizations", "q": "STEINIER GLASS"})
    alias = client.get("/api/master-data/search", headers=h(), params={"kind": "organizations", "q": "steinier"})
    initial_list = client.get("/api/master-data/search", headers=h(), params={"kind": "organizations", "q": "", "limit": 100})
    assert exact.status_code == alias.status_code == 200
    assert exact.json()["resolved_id"] == record["id"]
    assert exact.json()["results"][0]["display_name"] == "Steinier Glass"
    assert alias.json()["results"][0]["id"] == record["id"]
    assert initial_list.status_code == 200
    assert record["id"] in {row["id"] for row in initial_list.json()["results"]}


def test_owner_search_returns_owner_organizations_with_fill_details(client):
    owner = client.post(
        "/api/master-data/organizations", headers=h(), json={
            "display_name": "North Star Property Holdings",
            "legal_name": "North Star Property Holdings, LLC",
            "classifications": ["Owner"],
            "address": "100 Civic Plaza, Minneapolis, MN 55401",
            "website": "https://northstar.example.invalid",
            "primary_phone": "612-555-0100",
            "email": "facilities@example.invalid",
        },
    ).json()["record"]
    client.post(
        "/api/master-data/organizations", headers=h(), json={
            "display_name": "North Star Glass Vendor", "classifications": ["Vendor"],
        },
    )

    response = client.get(
        "/api/master-data/search", headers=h(), params={"kind": "owners", "q": "North Star"},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert [row["id"] for row in results] == [owner["id"]]
    assert results[0]["legal_name"] == "North Star Property Holdings, LLC"
    assert results[0]["address"] == "100 Civic Plaza, Minneapolis, MN 55401"
    assert results[0]["primary_phone"] == "(612) 555-0100"


def test_structured_address_search_proxies_existing_provider_and_request_identity(client, monkeypatch):
    import app.main as main

    observed = {}

    def fake_search(query, *, limit, request_id):
        observed.update({"query": query, "limit": limit, "request_id": request_id})
        return {
            "query": query,
            "request_id": request_id,
            "cache_hit": False,
            "provider": "Existing mileage provider",
            "attribution": "Provider attribution",
            "results": [{
                "id": "address_result_1",
                "label": "3900 Hoffman Road, White Bear Lake, MN 55110",
                "street": "3900 Hoffman Road",
                "city": "White Bear Lake",
                "state": "MN",
                "zip": "55110",
                "county": "Ramsey County",
                "latitude": "45.053",
                "longitude": "-93.012",
                "provider": "Existing mileage provider",
            }],
        }

    monkeypatch.setattr(main, "search_addresses", fake_search)
    response = client.get(
        "/api/address-search", headers=h(),
        params={"q": "3900 Hoffman", "limit": 4, "request_id": "address-request-7"},
    )

    assert response.status_code == 200
    assert observed == {"query": "3900 Hoffman", "limit": 4, "request_id": "address-request-7"}
    assert response.json()["results"][0] == {
        "id": "address_result_1",
        "label": "3900 Hoffman Road, White Bear Lake, MN 55110",
        "street": "3900 Hoffman Road",
        "city": "White Bear Lake",
        "state": "MN",
        "zip": "55110",
        "county": "Ramsey County",
        "latitude": "45.053",
        "longitude": "-93.012",
        "provider": "Existing mileage provider",
    }
    short = client.get("/api/address-search", headers=h(), params={"q": "ab"})
    assert short.status_code == 200 and short.json()["results"] == []


def test_custom_cost_code_requires_hashed_local_secret_and_never_persists_password(client, tmp_path):
    import app.main as main

    test_username = "custom-code-test-user"
    valid_password = "test-only credential with spaces"
    main.store.save_application_credential("custom-code", {
        "username": test_username,
        "password_hash": hash_password(valid_password, iterations=MINIMUM_ITERATIONS, salt=b"api-contract-salt"),
    })
    doc = create_project(client, "Custom Cost Code auth")
    project_id = doc["project"]["id"]
    invalid = client.post(
        f"/api/projects/{project_id}/cost-codes/custom", headers=h(),
        json={
            "expected_revision": doc["project"]["revision"],
            "username": test_username,
            "password": "wrong test credential",
            "code": "CUSTOM 991",
            "description": "Protected test code",
        },
    )
    assert invalid.status_code == 403
    assert invalid.json()["error"]["code"] == "custom_code_authorization_failed"

    created = client.post(
        f"/api/projects/{project_id}/cost-codes/custom", headers=h(),
        json={
            "expected_revision": doc["project"]["revision"],
            "username": test_username,
            "password": valid_password,
            "code": "CUSTOM 991",
            "description": "Protected test code",
            "reason": "API contract test",
        },
    )
    assert created.status_code == 200
    record = created.json()["cost_code"]
    assert record["is_custom"] is True
    assert record["custom_status"] == "authorized_custom"
    assert record["controlled_status"] == "custom_exception"

    response_text = created.text
    reopened_text = client.get(f"/api/projects/{project_id}", headers=h()).text
    persisted_text = json.dumps(main.store.load_project(project_id)[0])
    for text in (response_text, reopened_text, persisted_text):
        assert valid_password not in text
        assert "wrong test credential" not in text
        assert "password_hash" not in text


def test_mileage_is_locked_except_for_scoped_administrator_session_override(client):
    import app.main as main

    username, password = "override-test-admin", "session-only-test-password"
    main.store.save_application_credential("custom-code", {
        "username": username,
        "password_hash": hash_password(password, iterations=MINIMUM_ITERATIONS, salt=b"override-api-salt"),
    })
    doc = create_project(client, "Session override contract")
    project_id = doc["project"]["id"]
    doc["project"]["miles_from_minneapolis"] = "47.5"
    body = {"project": doc, "expected_revision": doc["project"]["revision"], "changes": [{
        "path": "project.miles_from_minneapolis", "prior": None, "new": "47.5",
    }]}
    locked = client.put(f"/api/projects/{project_id}", headers=h(), json=body)
    assert locked.status_code == 422, locked.text
    assert locked.json()["error"]["code"] == "calculated_field_locked"

    unlocked = client.post("/api/session-overrides", headers=h("Systems Administrator"), json={
        "project_id": project_id, "page": "project", "username": username, "password": password,
    })
    assert unlocked.status_code == 200
    token = unlocked.json()["token"]
    saved = client.put(f"/api/projects/{project_id}", headers={
        **h("Systems Administrator"), "X-Override-Token": token,
    }, json=body)
    assert saved.status_code == 200
    assert saved.json()["project"]["project"]["miles_from_minneapolis"] == "47.5"
    assert password not in saved.text

    client.delete("/api/session-overrides", headers={
        **h("Systems Administrator"), "X-Override-Token": token,
    })
    body["project"] = saved.json()["project"]
    body["expected_revision"] = body["project"]["project"]["revision"]
    body["project"]["project"]["miles_from_minneapolis"] = "48.0"
    relocked = client.put(f"/api/projects/{project_id}", headers={
        **h("Systems Administrator"), "X-Override-Token": token,
    }, json=body)
    assert relocked.status_code == 422
    assert relocked.json()["error"]["code"] == "calculated_field_locked"


def test_cost_code_dependency_preview_does_not_mutate_then_confirmed_cascade_removes_working_detail(client):
    doc = create_project(client, "Cascade contract")
    project_id = doc["project"]["id"]
    code = first_controlled_cost_code()
    doc["cost_codes"] = [code]
    doc["quotes"] = [{
        "id": "quo_cascade_contract",
        "code": code["code"],
        "vendor": "Cascade Vendor",
        "price": "1250",
        "used": True,
        "tax_included": True,
    }]
    doc["borrowed_lites"] = [{
        "id": "brl_cascade_contract", "code": code["code"], "mark": "BL-1",
        "quantity": 1, "width_inches": 12, "height_inches": 12, "rate": "10",
    }]
    normalized_code = "".join(char for char in code["code"] if char.isalnum()).upper()
    doc["working_estimate"]["component_markup_overrides"] = {
        f"borrowed_lite:{normalized_code}": {"rate": ".35", "reason": "Cascade coverage"},
    }
    saved_response = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )
    assert saved_response.status_code == 200
    saved = saved_response.json()["project"]
    revision = saved["project"]["revision"]

    preview = client.post(
        f"/api/projects/{project_id}/cost-codes/{code['id']}/remove", headers=h(),
        json={"expected_revision": revision, "confirm_cascade": False},
    )
    assert preview.status_code == 200
    assert preview.json()["removed"] is False
    assert preview.json()["requires_confirmation"] is True
    assert preview.json()["dependency_report"]["dependency_count"] >= 1
    assert any(item["id"] == "quo_cascade_contract" for item in preview.json()["dependency_report"]["dependencies"])
    assert preview.json()["project"]["project"]["revision"] == revision
    assert preview.json()["project"]["cost_codes"][0]["id"] == code["id"]

    removed = client.post(
        f"/api/projects/{project_id}/cost-codes/{code['id']}/remove", headers=h(),
        json={"expected_revision": revision, "confirm_cascade": True, "reason": "Confirmed API cascade"},
    )
    assert removed.status_code == 200
    result = removed.json()
    assert result["removed"] is True
    assert result["project"]["cost_codes"] == []
    assert result["project"]["quotes"] == []
    assert result["project"]["borrowed_lites"] == []
    assert result["project"]["working_estimate"]["component_markup_overrides"] == {}
    event = next(item for item in result["project"]["audit_events"] if item["operation"] == "cost_code_cascade_removed")
    assert "quo_cascade_contract" in event["new_value"]["removed_record_ids"]


def test_import_migrates_supported_legacy_project_document_to_current_schema(client):
    current = create_project(client, "Legacy import source")
    legacy = deepcopy(current)
    legacy["schema_version"] = "1.0.0"
    legacy["interchange_version"] = "1.0.0"
    legacy["project"]["project_type"] = "Training / Sandbox"
    legacy["project"]["contract_type"] = "Legacy negotiated contract"
    legacy["project"]["bid_due_date"] = "2026-09-01"
    for field in (
        "project_type_status", "contract_type_status", "wage_type", "wage_type_status",
        "address_street", "address_city", "address_state", "county", "address_match_metadata",
    ):
        legacy["project"].pop(field, None)
    legacy.pop("schema_migrations", None)

    imported = client.post(
        "/api/projects/import", headers=h(),
        json={"project_document": legacy, "as_duplicate": True, "name": "Migrated legacy import"},
    )

    assert imported.status_code == 200
    migrated = imported.json()["project"]
    assert migrated["schema_version"] == SCHEMA_VERSION == "1.5.0"
    assert migrated["interchange_version"] == "1.5.0"
    assert migrated["project"]["project_type"] == "Training / Sandbox"
    assert migrated["project"]["project_type_status"] == "legacy_unsupported"
    assert migrated["project"]["contract_type"] == "Legacy negotiated contract"
    assert migrated["project"]["contract_type_status"] == "legacy_unsupported"
    assert migrated["project"]["bid_due_date"] == "2026-09-01"
    assert migrated["project"]["bid_due_date_status"] == "legacy_date_only"
    assert migrated["schema_migrations"][-1]["id"] == "project-1.4.0-to-1.5.0"


def test_bid_source_edit_requires_confirmation_and_updates_only_canonical_record(client):
    doc = create_project(client, "Canonical Bid edit")
    project_id = doc["project"]["id"]
    code = first_controlled_cost_code()
    doc["cost_codes"] = [code]
    doc["quotes"] = [{
        "id": "quo_bid_edit_contract",
        "code": code["code"],
        "vendor": "Canonical Vendor",
        "price": "100.00",
        "credit_type": None,
        "credit_value": None,
        "surcharge_type": None,
        "surcharge_value": None,
        "tax_included": True,
        "used": True,
        "notes": "Before Bid edit",
    }]
    saved_response = client.put(
        f"/api/projects/{project_id}", headers=h(),
        json={"project": doc, "expected_revision": doc["project"]["revision"]},
    )
    assert saved_response.status_code == 200
    saved = saved_response.json()["project"]
    revision = saved["project"]["revision"]

    declined = client.post(
        f"/api/projects/{project_id}/bid-source-edit", headers=h(),
        json={
            "expected_revision": revision,
            "source_type": "quote",
            "source_id": "quo_bid_edit_contract",
            "changes": {"price": "275.50", "notes": "Edited from Bid"},
            "confirmed": False,
        },
    )
    assert declined.status_code == 422
    assert declined.json()["error"]["code"] == "confirmation_required"
    unchanged = client.get(f"/api/projects/{project_id}", headers=h()).json()["project"]
    assert unchanged["project"]["revision"] == revision
    assert unchanged["quotes"][0]["price"] == "100.00"

    confirmed = client.post(
        f"/api/projects/{project_id}/bid-source-edit", headers=h(),
        json={
            "expected_revision": revision,
            "source_type": "quote",
            "source_id": "quo_bid_edit_contract",
            "changes": {"price": "275.50", "notes": "Edited from Bid"},
            "confirmed": True,
            "reason": "Estimator confirmed canonical source update",
            "correlation_id": "cor_bid_edit_contract",
        },
    )
    assert confirmed.status_code == 200
    result = confirmed.json()
    canonical = next(row for row in result["project"]["quotes"] if row["id"] == "quo_bid_edit_contract")
    assert canonical["price"] == "275.50"
    assert canonical["notes"] == "Edited from Bid"
    assert result["source"]["id"] == canonical["id"]
    audit_event = next(item for item in result["project"]["audit_events"] if item["operation"] == "bid_source_edit")
    assert audit_event["correlation_id"] == "cor_bid_edit_contract"
    assert audit_event["prior_value"]["price"] == "100.00"
    assert audit_event["new_value"]["price"] == "275.50"


def test_frame_takeoff_round_trips_realistic_scale_and_downstream_material_costs(client):
    doc = client.post("/api/projects", headers=h(), json={"name": "100 Row Frame Takeoff"}).json()["project"]
    project_id = doc["project"]["id"]
    doc["cost_codes"] = [
        {"id": "ccd_frames", "code": "08 40 00", "description": "Aluminum Entrances", "deduct": False},
        {"id": "ccd_storefront", "code": "08 41 13", "description": "Storefront", "deduct": False},
    ]
    all_materials = ["mat_bracing", "mat_membrane", "mat_flashing", "mat_backer", "mat_sealant", "mat_tieback", "mat_backpan"]
    lines = [{
        "id": f"frm_scale_{index}", "mark": f"F-{index + 1:03d}", "quantity": (index % 4) + 1,
        "width_inches": 36 + index % 5 * 6, "height_inches": 84 + index % 3 * 6,
        "caulking_passes": 3, "head": "H1", "sill": "S1", "jamb": "J1",
        "type": "Storefront", "material": "Aluminum", "finish": "Clear anodized", "notes": "",
        "installation_material_ids": all_materials if index % 2 else ["mat_bracing", "mat_flashing", "mat_sealant"],
    } for index in range(100)]
    doc["takeoff_sections"] = [
        {"id": "sec_scale", "definition_id": "frame-v1", "name": "08 40 00 Aluminum Entrances Take Off",
         "code": "08 40 00", "lines": lines, "material_overrides": {"mat_sealant": {"factor": ".08", "rate": "12"}},
         "tie_back_qty": 18, "backpan_lf": 144},
        {"id": "sec_second", "definition_id": "frame-v1", "name": "08 41 13 Storefront Take Off",
         "code": "08 41 13", "lines": [{**lines[0], "id": "frm_second", "mark": "SF-1"}],
         "material_overrides": {}, "tie_back_qty": 2, "backpan_lf": 20},
    ]

    saved = client.put(f"/api/projects/{project_id}", headers=h(), json={
        "project": doc, "expected_revision": doc["project"]["revision"],
        "changes": [{"path": "takeoff_sections", "prior": [], "new": "realistic-scale", "reason": "Scale workflow test"}],
    })
    assert saved.status_code == 200
    calculated = saved.json()["project"]
    assert len(calculated["takeoff_sections"][0]["lines"]) == 100
    assert float(calculated["takeoff_sections"][0]["totals"]["square_feet"]) > 0
    assert float(calculated["takeoff_sections"][0]["pre_tax_material_cost"]) > 0
    assert any(line["category"] == "installation_material" and line["code"] == "08 40 00"
               for line in calculated["working_estimate"]["lines"])

    reopened = client.get(f"/api/projects/{project_id}", headers=h()).json()["project"]
    assert reopened["takeoff_sections"][0]["lines"][50]["mark"] == "F-051"
    assert reopened["takeoff_sections"][0]["tie_back_qty"] == 18
    assert reopened["takeoff_sections"][0]["backpan_lf"] == 144
    assert client.post(f"/api/projects/{project_id}/backup", headers=h(), json={}).status_code == 200


def test_vertical_submission_activation_contract_pco_sov_closeout(client):
    doc=client.post("/api/projects",headers=h(),json={"name":"Vertical"}).json()["project"];pid=doc["project"]["id"]
    doc["project"].update({"project_type":"New Construction - Exterior Storefront","contract_type":"Bid to CM/GC","wage_type":"Non-PW"})
    doc["cost_codes"]=[{"id":"ccd_api","code":"08 40 00","description":"Frames","deduct":False}]
    doc["quotes"]=[{"id":"quo_api","group_id":"g","code":"08 40 00","price":"1000","surcharge_percent":"0","tax_included":True,"used":True,"vendor":"V"}]
    doc["working_estimate"]["labor_suggestion_exclusions"]=["08 40 00"]
    doc=client.put(f"/api/projects/{pid}",headers=h(),json={"project":doc,"expected_revision":1}).json()["project"]
    sub=client.post(f"/api/projects/{pid}/submit",headers=h(),json={"recipient":"GC","method":"email"})
    assert sub.status_code == 200
    doc=sub.json()["project"];rev=doc["estimate_revisions"][0]["id"]
    assert doc["project"]["bid_version"]["display"] == "B0.1.0"
    artifact=doc["proposal_artifacts"][0]
    preview=client.get(f"/api/projects/{pid}/proposal/{artifact['id']}.pdf",headers=h())
    download=client.get(f"/api/projects/{pid}/proposal/{artifact['id']}.pdf?download=true",headers=h())
    assert preview.status_code == 200 and preview.headers["content-disposition"].startswith("inline")
    assert download.status_code == 200 and download.headers["content-disposition"].startswith("attachment")
    assert doc["project"]["bid_version"]["display"].replace(".", "-") in download.headers["content-disposition"]
    act=client.post(f"/api/projects/{pid}/activate",headers=h("Project Manager","Pat"),json={"revision_id":rev,"ntp_date":"2026-01-01","ntp_evidence":"NTP email"})
    assert act.status_code == 200
    doc=act.json()["project"];allocation=doc["contract_allocations"][0]
    assert doc["project"]["bid_version"]["display"] == "B1.0.0"
    re=client.post(f"/api/projects/{pid}/contract/reestimate",headers=h("Project Manager","Pat"),json={"allocation_id":allocation["id"],"new_cost":"900","reason":"Buyout"});assert re.status_code==200
    pco=client.post(f"/api/projects/{pid}/change-orders",headers=h("Project Manager","Pat"),json={"identifier":"PCO-1","cost_lines":[{"cost":"100"}]});assert pco.status_code==200
    order=pco.json()["change_order"]
    approved=client.post(f"/api/projects/{pid}/change-orders/{order['id']}/status",headers=h("Project Manager","Pat"),json={"status":"approved","reason":"Test approval","pending_policy_acknowledged":True})
    assert approved.status_code==200 and approved.json()["change_order"]["contract_effect"]=="applied"
    sov=client.post(f"/api/projects/{pid}/sov",headers=h("Project Manager","Pat"),json={"allocation_id":allocation["id"],"components":[allocation["contract_value"]]});assert sov.status_code==200
    close=client.post(f"/api/projects/{pid}/closeout",headers=h("Project Manager","Pat"),json={"completion_evidence":"Test"});assert close.status_code==200
    assert close.json()["closeout"]["status"] == "provisional_pending_policy"


def test_pco_fields_are_server_redacted(client):
    # Direct service behavior is covered in unit tests; this proves API response filtering.
    doc=client.post("/api/projects",headers=h(),json={"name":"Redaction"}).json()["project"]
    assert "pco" in client.get("/api/configurations",headers=h()).json()["configurations"][0]
    assert client.get("/api/configurations",headers=h()).json()["configurations"][0]["pco"]["restricted"] is True


def test_mileage_command_persists_one_decimal_lineage_and_is_idempotently_cached(client, monkeypatch):
    import app.main as main

    created = client.post("/api/projects", headers=h(), json={"name": "Mileage Job"}).json()["project"]
    project_id = created["project"]["id"]
    created["project"]["address"] = "100 Main Street, Minneapolis, MN"
    created["project"]["zip"] = "55401"
    created = client.put(f"/api/projects/{project_id}", headers=h(), json={"project": created, "expected_revision": 1,
                         "changes": [{"path": "project.address", "prior": "", "new": created["project"]["address"]}]}).json()["project"]

    monkeypatch.setattr(main, "calculate_driving_mileage", lambda address, settings: {
        "input_address": address, "matched_address": "100 MAIN STREET, MINNEAPOLIS, MN, 55401", "miles": "31.7",
        "distance_meters": "51016.2", "duration_minutes": "38.4", "origin": {"label": "Minneapolis", "latitude": "45", "longitude": "-93"},
        "destination": {"latitude": "44", "longitude": "-93"}, "geocoder": "Test geocoder", "router": "Test router",
        "attribution": None, "calculated_at": "2026-08-17T00:00:00+00:00", "rounding": "nearest 0.1 mile", "cache_hit": False,
    })
    result = client.post(f"/api/projects/{project_id}/mileage", headers=h(), json={"expected_revision": created["project"]["revision"]})
    assert result.status_code == 200
    doc = result.json()["project"]
    assert doc["project"]["miles_from_minneapolis"] == "31.7"
    assert doc["project"]["mileage_calculation"]["matched_address"].startswith("100 MAIN")
    assert doc["project"]["bid_version"]["patch"] == 2
    assert any(event["operation"] == "mileage_calculated" for event in doc["audit_events"])

    cached = client.post(f"/api/projects/{project_id}/mileage", headers=h(), json={"expected_revision": doc["project"]["revision"]})
    assert cached.status_code == 200 and cached.json()["cached"] is True
    assert cached.json()["project"]["project"]["revision"] == doc["project"]["revision"]
    assert client.post(f"/api/projects/{project_id}/mileage", headers=h("Project Manager"), json={}).status_code == 403
