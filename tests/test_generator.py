import pytest
from fastapi.testclient import TestClient

from app.generator import GENERATOR_VERSION, generate_test_project
from app.persistence import JsonStore
from app.schema import default_configuration
from app.services import calculate_project


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.main as main
    test_store = JsonStore(tmp_path)
    test_store.save_configuration(default_configuration())
    monkeypatch.setattr(main, "store", test_store)
    return TestClient(main.app)


def _generated(seed=4320):
    config = default_configuration()
    doc = generate_test_project(config, "Test Estimator", "Estimator", seed)
    calculate_project(doc, config)
    return doc


def test_generator_populates_every_estimating_bucket_with_coherent_data():
    doc = _generated()
    assert len(doc["contacts"]) >= 6
    assert len(doc["cost_codes"]) >= 9
    assert len(doc["quotes"]) >= 12
    assert len(doc["takeoff_sections"]) >= 5
    assert sum(len(section["lines"]) for section in doc["takeoff_sections"]) >= 40
    assert len(doc["doors"]) >= 18
    assert len(doc["hardware_assignments"]) == len(doc["doors"])
    assert len(doc["equipment"]) >= 5
    assert len(doc["borrowed_lites"]) >= 8
    assert len(doc["labor_estimates"]) >= 14
    assert len(doc["travel_estimates"]) >= 3
    assert len(doc["bid_tabulations"]) >= 4

    door_ids = {row["id"] for row in doc["doors"]}
    assert all(row["door_id"] in door_ids for row in doc["hardware_assignments"])
    groups = {row["group_id"] for row in doc["quotes"]}
    assert all(sum(bool(row["used"]) for row in doc["quotes"] if row["group_id"] == group) == 1 for group in groups)
    assert not [warning for warning in doc["working_estimate"]["validation"] if warning["code"] in {"invalid_cost_code", "multiple_used_quotes", "missing_used_quote"}]
    assert float(doc["working_estimate"]["totals"]["selling_value"]) > 100_000


def test_generator_is_seed_reproducible_but_creates_distinct_projects():
    first, second = _generated("training-scenario"), _generated("training-scenario")
    assert first["project"]["id"] != second["project"]["id"]
    assert first["project"]["name"] == second["project"]["name"]
    assert first["project"]["address"] == second["project"]["address"]
    assert [row["price"] for row in first["quotes"]] == [row["price"] for row in second["quotes"]]
    assert [(row["width_inches"], row["height_inches"], row["quantity"]) for section in first["takeoff_sections"] for row in section["lines"]] == [
        (row["width_inches"], row["height_inches"], row["quantity"]) for section in second["takeoff_sections"] for row in section["lines"]
    ]
    assert first["working_estimate"]["totals"]["selling_value"] == second["working_estimate"]["totals"]["selling_value"]


def test_generator_starts_as_a_saved_editable_synthetic_draft():
    doc = _generated()
    assert doc["project"]["lifecycle_state"] == "estimate_created"
    assert doc["project"]["bid_version"]["display"] == "B0.0.0"
    assert doc["project"]["test_generation"]["generator_version"] == GENERATOR_VERSION
    assert doc["project"]["test_generation"]["purpose"] == "training_test_only"
    assert "TEST DATA ONLY" in doc["project"]["notes"]
    assert doc["estimate_revisions"] == [] and doc["award"] is None
    assert all(not row["enabled"] for row in doc["travel_estimates"])
    assert any(event["operation"] == "generate_test_project" for event in doc["audit_events"])


def test_generate_test_project_api_and_home_control(client):
    response = client.post("/api/projects/generate-test", headers={"X-Role": "Estimator", "X-Actor": "Generator Tester"}, json={"seed": "api-case"})
    assert response.status_code == 200
    body = response.json()
    assert body["project"]["project"]["bid_version"]["display"] == "B0.0.0"
    assert body["generation"]["counts"]["frame_rows"] == 40
    project_id = body["project"]["project"]["id"]
    assert client.get(f"/api/projects/{project_id}", headers={"X-Role": "Estimator"}).status_code == 200

    forbidden = client.post("/api/projects/generate-test", headers={"X-Role": "Project Manager"}, json={"seed": 123})
    assert forbidden.status_code == 403

    home = client.get("/").text
    javascript = client.get("/assets/app.js").text
    assert "Generate realistic test project" in home
    assert '"generate-test":generateTestProject' in javascript

