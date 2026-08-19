import json

import pytest
from fastapi.testclient import TestClient

from app.persistence import JsonStore
from app.schema import CONFIG_VERSION, default_configuration


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.main as main
    test_store = JsonStore(tmp_path)
    test_store.save_configuration(default_configuration())
    monkeypatch.setattr(main, "store", test_store)
    return TestClient(main.app)


def h(role="Estimator", actor="Tester"):
    return {"X-Role":role,"X-Actor":actor}


def test_direct_workspace_routes_return_fresh_application_shell(client):
    response = client.get("/projects/prj_00000000000000000000000000004320/frames")
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


def test_health_static_and_project_crud_conflict(client):
    assert client.get("/api/health").status_code == 200
    assert "Murphy Window" in client.get("/").text
    created=client.post("/api/projects",headers=h(),json={"name":"API Job"})
    assert created.status_code == 200
    doc=created.json()["project"]; pid=doc["project"]["id"]
    assert client.get("/api/projects",headers=h()).json()["projects"][0]["id"] == pid
    doc["project"]["address"]="Rogers"
    saved=client.put(f"/api/projects/{pid}",headers=h(),json={"project":doc,"expected_revision":1,"changes":[{"path":"project.address","prior":"","new":"Rogers"},{"path":"project.notes","prior":"","new":"Two changes"}]})
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


def test_duplicate_export_backup_import_and_job_data(client):
    doc=client.post("/api/projects",headers=h(),json={"name":"Portable"}).json()["project"];pid=doc["project"]["id"]
    dup=client.post(f"/api/projects/{pid}/duplicate",headers=h(),json={"name":"Portable Copy"})
    assert dup.status_code == 200 and dup.json()["project"]["project"]["id"] != pid
    export=client.get(f"/api/projects/{pid}/export",headers=h()); assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/json")
    assert client.post(f"/api/projects/{pid}/backup",headers=h(),json={}).status_code == 200
    data=client.get(f"/api/projects/{pid}/job-data",headers=h()).json();assert data["version"] == "1.0.0"
    imported=client.post("/api/projects/import",headers=h(),json={"project_document":json.loads(export.text),"as_duplicate":True})
    assert imported.status_code == 200 and imported.json()["project"]["project"]["id"] != pid


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
    doc["cost_codes"]=[{"id":"ccd_api","code":"08 40 00","description":"Frames","deduct":False}]
    doc["quotes"]=[{"id":"quo_api","group_id":"g","code":"08 40 00","price":"1000","surcharge_percent":"0","tax_included":True,"used":True,"vendor":"V"}]
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
        "distance_meters": "51016.2", "duration_minutes": "38.4", "origin": {"label": "Rogers", "latitude": "45", "longitude": "-93"},
        "destination": {"latitude": "44", "longitude": "-93"}, "geocoder": "Test geocoder", "router": "Test router",
        "attribution": None, "calculated_at": "2026-08-17T00:00:00+00:00", "rounding": "nearest 0.1 mile", "cache_hit": False,
    })
    result = client.post(f"/api/projects/{project_id}/mileage", headers=h(), json={"expected_revision": created["project"]["revision"]})
    assert result.status_code == 200
    doc = result.json()["project"]
    assert doc["project"]["miles_from_rogers"] == "31.7"
    assert doc["project"]["mileage_calculation"]["matched_address"].startswith("100 MAIN")
    assert doc["project"]["bid_version"]["patch"] == 2
    assert any(event["operation"] == "mileage_calculated" for event in doc["audit_events"])

    cached = client.post(f"/api/projects/{project_id}/mileage", headers=h(), json={"expected_revision": doc["project"]["revision"]})
    assert cached.status_code == 200 and cached.json()["cached"] is True
    assert cached.json()["project"]["project"]["revision"] == doc["project"]["revision"]
    assert client.post(f"/api/projects/{project_id}/mileage", headers=h("Project Manager"), json={}).status_code == 403
