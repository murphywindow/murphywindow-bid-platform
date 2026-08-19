from app.schema import new_project, test_project as make_test_project
from app.services import bump_bid_version


def test_bid_semantic_version_rules_and_monotonic_sequence():
    doc = new_project("Version", "A", "Estimator")
    assert doc["project"]["bid_version"]["display"] == "B0.0.0"
    bump_bid_version(doc, "edit")
    bump_bid_version(doc, "coalesced_datapoints", amount=4)
    assert doc["project"]["bid_version"]["display"] == "B0.0.5"
    assert doc["project"]["bid_version"]["sequence"] == 5
    bump_bid_version(doc, "submission", "minor")
    assert doc["project"]["bid_version"]["display"] == "B0.1.0"
    bump_bid_version(doc, "edit")
    assert doc["project"]["bid_version"]["display"] == "B0.1.1"
    bump_bid_version(doc, "activation", "major")
    assert doc["project"]["bid_version"]["display"] == "B1.0.0"
    assert doc["project"]["bid_version"]["sequence"] == 8


def test_seeded_test_project_is_rich_editable_draft():
    doc = make_test_project()
    assert doc["project"]["id"] == "prj_00000000000000000000000000004320"
    assert doc["project"]["project_number"] == "TEST-4320"
    assert doc["project"]["bid_version"]["display"] == "B0.0.0"
    assert len(doc["quotes"]) >= 3
    assert doc["takeoff_sections"][0]["lines"]
    assert {row["category"] for row in doc["labor_estimates"]} == {"field", "shop"}
    assert doc["estimate_revisions"] == [] and doc["award"] is None
