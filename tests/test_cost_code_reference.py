import json
from pathlib import Path

from app.schema import default_configuration


def test_owner_cost_code_reference_is_complete_normalized_and_versioned():
    payload = json.loads(Path("data/reference/codes.json").read_text(encoding="utf-8"))
    assert payload["source"]["file_name"] == "codes.xlsx"
    assert payload["source"]["sha256"] == "5f2bb30463165990d7ad5a6a4cc341d9acd4509de6a331298ba63ebb31f7a026"
    assert payload["source_row_count"] == 9332
    assert payload["unique_code_count"] == 9330
    assert len(payload["records"]) == 9330
    assert len({row["normalized_code"] for row in payload["records"]}) == 9330
    assert all(row["display_code"] and row["description"] for row in payload["records"])
    assert {row["display_code"] for row in payload["records"]}.issuperset({"GEN1", "GEN5", "00 00 00", "48 71 26"})


def test_duplicate_source_variants_are_preserved_as_aliases():
    payload = json.loads(Path("data/reference/codes.json").read_text(encoding="utf-8"))
    assert {row["normalized_code"] for row in payload["duplicate_normalized_codes"]} == {"060573", "211300"}
    by_code = {row["normalized_code"]: row for row in payload["records"]}
    assert by_code["060573"]["description_aliases"] == ["Wood Treatments"]
    assert by_code["211300"]["description_aliases"] == ["Fire Suppression Sprinkler System"]
    assert by_code["060573"]["source_rows"] == [1404, 1405]


def test_active_configuration_contains_owner_reference():
    config = default_configuration()
    assert config["version"] == 5
    assert config["cost_code_reference"]["record_count"] == 9330
    assert len(config["csi_references"]) == 9330
