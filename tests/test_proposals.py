from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from app.persistence import JsonStore, PersistenceError
from app.proposals import canonical_proposal_state, compare_snapshots, proposal_fingerprint
from app.schema import default_configuration, test_project as make_test_project
from app.services import calculate_project


def headers(role="Estimator", actor="Proposal Tester"):
    return {"X-Role": role, "X-Actor": actor}


@pytest.fixture()
def proposal_client(tmp_path, monkeypatch):
    import app.main as main
    store = JsonStore(tmp_path)
    config = default_configuration()
    store.save_configuration(config)
    document = make_test_project()
    calculate_project(document, config)
    store.save_project(document, 0)
    monkeypatch.setattr(main, "store", store)
    return TestClient(main.app), store, document["project"]["id"]


def test_canonical_fingerprint_is_stable_and_excludes_operational_metadata():
    config = default_configuration()
    document = make_test_project()
    calculate_project(document, config)
    first = proposal_fingerprint(document, config)
    changed = deepcopy(document)
    changed["project"]["revision"] = 987
    changed["project"]["updated_at"] = "2099-01-01T00:00:00+00:00"
    changed["project"]["bid_version"]["patch"] = 44
    changed["audit_events"].append({"id": "ephemeral"})
    changed["bid_tabulations"].append({"id": "market-result", "bid_value": "999999"})
    changed["working_branch"] = {"source_proposal_id": "prp_metadata_only"}
    assert proposal_fingerprint(changed, config) == first
    changed["project"]["proposal_scope"] += " Commercially meaningful change."
    assert proposal_fingerprint(changed, config) != first
    assert canonical_proposal_state(document, config)["effective_configuration"]["id"] == config["id"]


def test_generate_duplicate_prevention_historical_isolation_branch_ancestry_void_and_compare(proposal_client):
    client, store, project_id = proposal_client
    current = client.get(f"/api/projects/{project_id}", headers=headers()).json()["project"]
    generated = client.post(f"/api/projects/{project_id}/proposals", headers=headers(), json={
        "expected_revision": current["project"]["revision"], "proposal_name": "Original Bid",
    })
    assert generated.status_code == 200
    body = generated.json()
    p1 = body["proposal"]
    assert p1["number"] == "P1" and p1["name"] == "Original Bid"
    assert p1["parent_proposal_id"] is None
    snapshot_path = store.proposal_path(project_id, p1["id"])
    original_snapshot_bytes = snapshot_path.read_bytes()

    duplicate = client.post(f"/api/projects/{project_id}/proposals", headers=headers(), json={
        "expected_revision": body["project"]["project"]["revision"], "proposal_name": "Same State, Other Name",
    })
    assert duplicate.status_code == 409, duplicate.json()
    assert duplicate.json()["error"]["code"] == "duplicate_proposal"
    assert len(store.list_proposal_snapshot_ids(project_id)) == 1

    historical = client.get(f"/api/projects/{project_id}/proposals/{p1['id']}", headers=headers()).json()
    assert historical["project"]["project"]["historical_proposal"]["number"] == "P1"
    historical["project"]["project"]["proposal_scope"] = "Client-side mutation must not persist"
    reopened = client.get(f"/api/projects/{project_id}/proposals/{p1['id']}", headers=headers()).json()
    assert reopened["project"]["project"]["proposal_scope"] != "Client-side mutation must not persist"

    branch = client.post(f"/api/projects/{project_id}/proposals/{p1['id']}/branch", headers=headers(), json={
        "expected_revision": body["project"]["project"]["revision"],
        "correlation_id": "cor_first_edit",
        "changes": [{"path": "project.proposal_scope", "prior": reopened["project"]["project"]["proposal_scope"], "new": "VE scope", "reason": "First edit"}],
    })
    assert branch.status_code == 200
    working = branch.json()["project"]
    assert working["project"]["proposal_scope"] == "VE scope"
    assert working["working_branch"]["source_proposal_id"] == p1["id"]
    assert snapshot_path.read_bytes() == original_snapshot_bytes

    generated_p2 = client.post(f"/api/projects/{project_id}/proposals", headers=headers(), json={
        "expected_revision": working["project"]["revision"], "proposal_name": "VE Revision",
    })
    assert generated_p2.status_code == 200
    p2 = generated_p2.json()["proposal"]
    assert p2["number"] == "P2" and p2["parent_proposal_id"] == p1["id"]
    assert p2["ancestor_ids"] == [p1["id"]]

    comparison = client.get(f"/api/projects/{project_id}/proposals/compare/{p1['id']}/{p2['id']}", headers=headers())
    assert comparison.status_code == 200
    comparison_body = comparison.json()["comparison"]
    assert comparison_body["identical"] is False
    assert comparison_body["proposal_language"]["proposal_scope"]["new"] == "VE scope"

    latest = generated_p2.json()["project"]
    voided = client.post(f"/api/projects/{project_id}/proposals/{p1['id']}/void", headers=headers(), json={
        "expected_revision": latest["project"]["revision"], "reason": "Withdrawn by estimator",
    })
    assert voided.status_code == 200 and voided.json()["proposal"]["status"] == "voided"
    assert snapshot_path.read_bytes() == original_snapshot_bytes
    still_viewable = client.get(f"/api/projects/{project_id}/proposals/{p1['id']}", headers=headers())
    assert still_viewable.status_code == 200 and still_viewable.json()["proposal"]["status"] == "voided"
    artifact = generated_p2.json()["artifact"]
    pdf = client.get(f"/api/projects/{project_id}/proposal/{artifact['id']}.pdf", headers=headers())
    assert pdf.status_code == 200 and pdf.headers["x-proposal-artifact"] == artifact["id"]
    assert pdf.content == store.proposal_artifact_path(project_id, artifact["id"]).read_bytes()
    assert client.get(f"/api/projects/{project_id}/proposal/{artifact['id']}.pdf", headers=headers()).content == pdf.content


def test_same_value_with_different_underlying_state_is_allowed(proposal_client):
    client, _, project_id = proposal_client
    current = client.get(f"/api/projects/{project_id}", headers=headers()).json()["project"]
    p1 = client.post(f"/api/projects/{project_id}/proposals", headers=headers(), json={
        "expected_revision": current["project"]["revision"], "proposal_name": "First",
    }).json()
    document = p1["project"]
    old_value = document["working_estimate"]["totals"]["selling_value"]
    document["project"]["notes"] = "Changed explanatory commercial note"
    saved = client.put(f"/api/projects/{project_id}", headers=headers(), json={
        "project": document, "expected_revision": document["project"]["revision"],
        "changes": [{"path": "project.notes", "prior": "", "new": document["project"]["notes"]}],
    }).json()["project"]
    assert saved["working_estimate"]["totals"]["selling_value"] == old_value
    p2 = client.post(f"/api/projects/{project_id}/proposals", headers=headers(), json={
        "expected_revision": saved["project"]["revision"], "proposal_name": "Same Price, Different Basis",
    })
    assert p2.status_code == 200 and p2.json()["proposal"]["number"] == "P2"


def test_failed_project_index_commit_rolls_back_new_snapshot(proposal_client, monkeypatch):
    client, store, project_id = proposal_client
    current = client.get(f"/api/projects/{project_id}", headers=headers()).json()["project"]
    monkeypatch.setattr(store, "save_project", lambda *args, **kwargs: (_ for _ in ()).throw(PersistenceError("simulated index failure")))
    response = client.post(f"/api/projects/{project_id}/proposals", headers=headers(), json={
        "expected_revision": current["project"]["revision"], "proposal_name": "Must Roll Back",
    })
    assert response.status_code == 500
    assert store.list_proposal_snapshot_ids(project_id) == []
    assert list(store.proposal_artifacts.rglob("*.pdf")) == []
    persisted = store.load_project(project_id)[0]
    assert persisted.get("proposal_history", []) == []


def test_working_preview_is_ephemeral_and_includes_customer_language(proposal_client):
    client, store, project_id = proposal_client
    before = store.load_project(project_id)[0]
    response = client.get(f"/api/projects/{project_id}/proposal-preview.pdf", headers=headers())
    assert response.status_code == 200
    assert response.headers["x-proposal-preview"] == "current-working"
    assert "no-store" in response.headers["cache-control"]
    assert response.content.startswith(b"%PDF")
    after = store.load_project(project_id)[0]
    assert after.get("proposal_history", []) == before.get("proposal_history", []) == []
    assert store.list_proposal_snapshot_ids(project_id) == []


def test_branch_from_history_updates_all_customer_facing_fields_without_mutating_snapshot(proposal_client):
    client, store, project_id = proposal_client
    current = client.get(f"/api/projects/{project_id}", headers=headers()).json()["project"]
    generated = client.post(f"/api/projects/{project_id}/proposals", headers=headers(), json={
        "expected_revision": current["project"]["revision"], "proposal_name": "Frozen Original",
    }).json()
    proposal = generated["proposal"]
    frozen_bytes = store.proposal_path(project_id, proposal["id"]).read_bytes()
    changes = [
        {"path": "project.proposal_scope", "new": "Branched scope"},
        {"path": "project.proposal_inclusions", "new": "Branched inclusions"},
        {"path": "project.proposal_exclusions", "new": "Branched exclusions"},
        {"path": "project.additional_information", "new": "Branched qualifications"},
    ]
    response = client.post(f"/api/projects/{project_id}/proposals/{proposal['id']}/branch", headers=headers(), json={
        "expected_revision": generated["project"]["project"]["revision"], "correlation_id": "customer-language-edit",
        "changes": changes,
    })
    assert response.status_code == 200
    project = response.json()["project"]
    assert [project["project"][field] for field in ("proposal_scope", "proposal_inclusions", "proposal_exclusions", "additional_information")] == [
        "Branched scope", "Branched inclusions", "Branched exclusions", "Branched qualifications",
    ]
    assert project["working_branch"]["source_proposal_id"] == proposal["id"]
    assert project["working_branch"]["has_unpublished_changes"] is True
    assert store.proposal_path(project_id, proposal["id"]).read_bytes() == frozen_bytes


def test_comparison_is_changed_only_business_aware_and_reconciles():
    left = {
        "metadata": {"number": "P1", "name": "Original", "fingerprint": "a", "summary": {
            "bid_value": "1000", "direct_cost": "800", "margin_dollars": "200", "margin_percentage": ".2",
            "total_square_feet": "100", "value_per_square_foot": "10", "tax": "0", "contingency": "0", "bond": "0",
        }},
        "state": {"project": {"proposal_scope": "Windows.", "proposal_inclusions": "One mobilization.", "proposal_exclusions": "", "additional_information": ""},
                  "working_estimate": {"alternate_inclusion": {"ALT1": False}, "lines": [{"id": "line-1", "code": "08 41 13", "description": "Installation Materials", "direct_cost": "800", "selling_value": "1000", "area": "100"}], "cost_code_summaries": [{"code": "08 41 13", "description": "Aluminum-Framed Entrances and Storefronts", "direct_cost": "800", "selling_value": "1000", "margin_dollars": "200", "margin_percentage": ".2", "total_square_feet": "100", "dollars_per_square_foot": "10"}]},
                  "takeoff_sections": [{"id": "sec", "code": "08 41 13", "name": "Storefront", "material_overrides": {"matp_a": {"rate_override": "8"}}, "additional_materials": [{"id": "matp_a", "name": "Custom flashing", "source": "perimeter_lf", "factor": "1", "unit": "LF", "cost_code": "08 41 13"}], "lines": [{"id": "frame-12", "mark": "F12", "quantity": 3, "width_inches": 60, "height_inches": 96, "material_overrides": {"nested": {"factor": 1}}}]}],
                  "quotes": [], "equipment": [], "borrowed_lites": [], "labor_estimates": [], "doors": []},
    }
    right = deepcopy(left)
    right["metadata"] = deepcopy(left["metadata"])
    right["metadata"].update({"number": "P2", "name": "Revision", "fingerprint": "b"})
    right["metadata"]["summary"].update({"bid_value": "1092.47", "direct_cost": "882.56", "margin_dollars": "209.91", "total_square_feet": "121", "value_per_square_foot": "9.02867768595"})
    right["state"]["working_estimate"]["cost_code_summaries"][0].update({"direct_cost": "882.56", "selling_value": "1092.47", "margin_dollars": "209.91", "total_square_feet": "121", "dollars_per_square_foot": "9.02867768595"})
    right["state"]["working_estimate"]["lines"][0].update({"direct_cost": "882.56", "selling_value": "1092.47", "area": "121"})
    right["state"]["takeoff_sections"][0]["lines"][0]["width_inches"] = 66
    right["state"]["takeoff_sections"][0]["additional_materials"][0]["factor"] = "1.25"
    right["state"]["project"]["proposal_exclusions"] = "Temporary heat by others."
    result = compare_snapshots(left, right)
    assert "margin_percentage" not in result["summary"]
    assert "tax" not in result["summary"] and "bond" not in result["summary"]
    assert len(result["cost_codes"]) == 1
    assert "margin_percentage" not in result["cost_codes"][0]["fields"]
    frame = next(group for group in result["cost_codes"][0]["source_changes"] if group["category"] == "Frame Takeoff")
    assert frame["entries"][0]["changes"] == [{"field": "width_inches", "label": "Width Inches", "old": 60, "new": 66, "format": "number"}]
    material = next(group for group in result["cost_codes"][0]["source_changes"] if group["category"] == "Installation Materials")
    assert material["entries"][0]["changes"] == [{"field": "factor", "label": "Factor", "old": "1", "new": "1.25", "format": "text"}]
    assert result["proposal_language"]["proposal_exclusions"]["added"] == ["Temporary heat by others."]
    assert result["reconciliation"]["reconciled"] is True
    assert result["reconciliation"]["top_level_pricing_delta"] == "0.00"
    assert "[object Object]" not in json.dumps(result)
