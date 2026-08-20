from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

import app.historical as historical
from app.historical import (
    BID_COST_CODE_SELL_PER_SF_METRIC,
    HistoricalMetricIndex,
    canonical_cost_code,
    compare_values,
    extract_project_observations,
)
from app.persistence import ConflictError, JsonStore
from app.schema import PROJECT_TYPES, default_configuration, new_project
from app.services import calculate_project
from scripts.seed_historical_bids import seed as seed_historical_bids


CODE = "08 40 00"


def _revision(document: dict, ratio: int | str, number: int, *, legacy: bool = False) -> dict:
    selling_value = Decimal(str(ratio)) * Decimal(100)
    revision_id = f"rev_{document['project']['id']}_{number}"
    estimate = {
        "lines": [
            {
                "id": f"est_{number}_a", "code": CODE, "included": True,
                "selling_value": format(selling_value * Decimal("0.6"), "f"),
            },
            {
                "id": f"est_{number}_b", "code": CODE, "included": True,
                "selling_value": format(selling_value * Decimal("0.4"), "f"),
            },
        ],
    }
    if not legacy:
        estimate["cost_code_summaries"] = [
            {
                "code": CODE, "description": "Entrances", "included": True,
                "selling_value": format(selling_value, "f"), "total_square_feet": "100",
                "metric_definition": BID_COST_CODE_SELL_PER_SF_METRIC,
            }
        ]
    return {
        "id": revision_id, "revision_number": number, "configuration_id": "1.1.0",
        "status": "submitted", "immutable": True,
        "created_at": f"2025-01-{number:02d}T12:00:00+00:00",
        "bid_version": {"display": f"B0.{number}.0"},
        "project_snapshot": deepcopy(document["project"]),
        "cost_codes": deepcopy(document["cost_codes"]),
        "source_snapshot": {
            "takeoff_sections": [
                {"id": f"sec_{number}", "code": CODE, "totals": {"square_feet": "80"}}
            ],
            "borrowed_lites": [
                {"id": f"brl_{number}", "code": CODE, "quantity": "1", "calculated_square_feet": "20"}
            ],
        },
        "estimate": estimate,
    }


def _historical_document(project_id: str, ratio: int | str, *, legacy: bool = False) -> dict:
    document = new_project(f"Comparable {project_id}", "Estimator", "Estimator")
    document["project"].update({"id": project_id, "project_number": project_id.upper()})
    document["cost_codes"] = [
        {"id": f"ccd_{project_id}", "code": CODE, "description": "Entrances", "deduct": False}
    ]
    revision = _revision(document, ratio, 1, legacy=legacy)
    document["estimate_revisions"] = [revision]
    document["submissions"] = [
        {
            "id": f"sub_{project_id}_1", "revision_id": revision["id"], "immutable": True,
            "submitted_at": "2025-02-01T12:00:00+00:00",
        }
    ]
    return document


def _current_document(project_id: str = "prj_current", ratio: int | str = 30) -> dict:
    document = new_project("Current Customer Bid", "Estimator", "Estimator")
    document["project"].update({"id": project_id, "project_number": "JOB-CURRENT"})
    document["cost_codes"] = [
        {"id": "ccd_current", "code": CODE, "description": "Entrances", "deduct": False}
    ]
    selling_value = Decimal(str(ratio)) * Decimal(100)
    document["quotes"] = [
        {
            "id": f"quo_{project_id}", "group_id": f"grp_{project_id}", "code": CODE,
            "price": format(selling_value, "f"), "surcharge_percent": "0",
            "tax_included": True, "used": True,
        }
    ]
    document["takeoff_sections"] = [
        {
            "id": f"sec_{project_id}", "definition_id": "frame-v1", "code": CODE,
            "name": "Frames", "material_overrides": {}, "tie_back_qty": 0, "backpan_lf": 0,
            "lines": [
                {
                    "id": f"frm_{project_id}", "quantity": 1, "width_inches": 120,
                    "height_inches": 96, "caulking_passes": 0,
                }
            ],
        }
    ]
    document["borrowed_lites"] = [
        {
            "id": f"brl_{project_id}", "code": CODE, "quantity": 1,
            "width_inches": 60, "height_inches": 48, "rate": None,
        }
    ]
    document["working_estimate"]["cost_code_summaries"] = [
        {
            "code": CODE, "description": "Entrances", "included": True,
            "selling_value": format(selling_value, "f"), "total_square_feet": "100",
            "metric_definition": BID_COST_CODE_SELL_PER_SF_METRIC,
        }
    ]
    return document


def _persist(store: JsonStore, document: dict) -> dict:
    return store.save_project(document, -1)


def test_legacy_frozen_adapter_and_award_precedence() -> None:
    document = _historical_document("prj_awarded", 10, legacy=True)
    awarded = document["estimate_revisions"][0]
    later = _revision(document, 90, 2)
    document["estimate_revisions"].append(later)
    document["submissions"].append({
        "id": "sub_later", "revision_id": later["id"], "immutable": True,
        "submitted_at": "2025-03-01T12:00:00+00:00",
    })
    document["award"] = {
        "id": "awd_1", "revision_id": awarded["id"], "immutable": True,
        "ntp_date": "2025-02-10", "activated_at": "2025-02-11T12:00:00+00:00",
        "awarded_bid_snapshot": deepcopy(awarded),
    }

    extracted = extract_project_observations(document)

    assert extracted["selected_state"]["kind"] == "awarded_snapshot"
    assert extracted["selected_state"]["revision_id"] == awarded["id"]
    assert len(extracted["observations"]) == 1
    observation = extracted["observations"][0]
    assert observation["adapter"] == "legacy_frozen_lines_and_sources_v1"
    assert observation["selling_value"] == "1000.0"
    assert observation["frame_square_feet"] == "80"
    assert observation["borrowed_lite_square_feet"] == "20"
    assert observation["value_per_square_foot"] == "10.0"


def test_malformed_award_never_falls_back_to_valid_submission() -> None:
    document = _historical_document("prj_bad_award", 25)
    document["award"] = {
        "id": "awd_bad", "revision_id": "rev_different", "immutable": True,
        "awarded_bid_snapshot": deepcopy(document["estimate_revisions"][0]),
    }

    extracted = extract_project_observations(document)

    assert extracted["observations"] == []
    assert extracted["project_exclusion"]["reason"] == "malformed_award_snapshot"


def test_orphan_submission_revision_is_not_attributed_to_project() -> None:
    wrong_project = _historical_document("prj_orphan", 25)
    wrong_project["estimate_revisions"][0]["project_snapshot"]["id"] = "prj_someone_else"
    extracted = extract_project_observations(wrong_project)
    assert extracted["observations"] == []
    assert extracted["project_exclusion"]["reason"] == "no_reliable_state"

    missing_submission = _historical_document("prj_no_submission", 25)
    missing_submission["submissions"] = []
    extracted = extract_project_observations(missing_submission)
    assert extracted["observations"] == []
    assert extracted["project_exclusion"]["reason"] == "no_reliable_state"


def test_tagged_summary_requires_frozen_source_and_line_reconciliation() -> None:
    missing_area = _historical_document("prj_missing_area", 25)
    revision = missing_area["estimate_revisions"][0]
    revision["source_snapshot"]["takeoff_sections"] = []
    revision["source_snapshot"]["borrowed_lites"] = []
    extracted = extract_project_observations(missing_area)
    assert extracted["observations"] == []
    assert "no matching Frame or Borrowed Lite source area" in extracted["exclusions"][0]["detail"]

    mismatched_value = _historical_document("prj_bad_value", 25)
    mismatched_value["estimate_revisions"][0]["estimate"]["lines"][0]["selling_value"] = "999999"
    extracted = extract_project_observations(mismatched_value)
    assert extracted["observations"] == []
    assert "does not reconcile to estimate lines" in extracted["exclusions"][0]["detail"]

    malformed_summaries = _historical_document("prj_bad_summaries", 25)
    malformed_summaries["estimate_revisions"][0]["estimate"]["cost_code_summaries"] = {"code": CODE}
    extracted = extract_project_observations(malformed_summaries)
    assert extracted["observations"] == []
    assert extracted["exclusions"][0]["reason"] == "malformed_cost_code_summaries"
    assert "legacy adapter is not used" in extracted["exclusions"][0]["detail"]

    malformed_legacy_lines = _historical_document("prj_bad_legacy_lines", 25, legacy=True)
    malformed_legacy_lines["estimate_revisions"][0]["estimate"]["lines"] = None
    extracted = extract_project_observations(malformed_legacy_lines)
    assert extracted["observations"] == []
    assert extracted["exclusions"][0]["reason"] == "invalid_metric_data"


def test_exact_full_code_and_sample_status_rules() -> None:
    assert canonical_cost_code("ALT1-08 40 00") == "ALT1:084000"
    assert canonical_cost_code("ALT1-08 40 00") != canonical_cost_code("08 40 00")
    observations = [{"value_per_square_foot": str(value)} for value in (10, 20, 30, 40)]
    limited = compare_values(Decimal(25), observations)
    assert limited["status"] == "limited_history"
    assert limited["sample_size"] == 4
    assert compare_values(Decimal(25), [])["status"] == "insufficient_history"
    assert compare_values(None, observations)["status"] == "unavailable"


def test_index_statistics_detail_provenance_and_synthetic_exclusion(tmp_path) -> None:
    store = JsonStore(tmp_path)
    current = _persist(store, _current_document())
    for index, value in enumerate((10, 20, 30, 40, 50), start=1):
        document = _historical_document(f"prj_history_{index}", value)
        document["submissions"][0]["submitted_at"] = f"2025-02-{index:02d}T12:00:00+00:00"
        _persist(store, document)
    synthetic = _historical_document("prj_synthetic", 999)
    synthetic["project"]["data_classification"] = "synthetic"
    _persist(store, synthetic)

    metric_index = HistoricalMetricIndex(store)
    metric_index.rebuild()
    result = metric_index.comparisons(current)

    assert result["project_revision"] == current["project"]["revision"] == 1
    assert result["metric_definition"]["id"] == BID_COST_CODE_SELL_PER_SF_METRIC
    assert result["minimum_sample"] == 5
    comparison = result["comparisons"][0]
    assert comparison["status"] == "classified"
    assert comparison["category"] == "Normal"
    assert comparison["sample_size"] == 5
    assert comparison["current_value"] == "30"
    assert Decimal(comparison["median"]) == Decimal(30)
    assert Decimal(comparison["q1"]) == Decimal(20)
    assert Decimal(comparison["q3"]) == Decimal(40)
    assert Decimal(comparison["minimum"]) == Decimal(10)
    assert Decimal(comparison["maximum"]) == Decimal(50)
    assert comparison["percentile"] == 50.0
    assert Decimal(comparison["difference_from_median"]["amount"]) == 0
    assert Decimal(comparison["difference_from_median"]["percent"]) == 0
    assert comparison["date_range"] == {
        "start": "2025-02-01T12:00:00+00:00", "end": "2025-02-05T12:00:00+00:00",
    }

    detail = metric_index.detail(current, CODE)
    assert detail["project_revision"] == 1
    assert detail["comparison"] == comparison
    assert len(detail["observations"]) == 5
    assert all(row["selling_value"] and row["effective_date"] for row in detail["observations"])
    assert detail["provenance"]["selection_rule"] == "awarded_snapshot_else_latest_immutable_submitted_revision"
    assert detail["provenance"]["historical_calculation"] == "frozen_values_only_no_recalculation"
    assert detail["exclusion_diagnostics"]["counts"]["current_project"] == 1
    assert detail["exclusion_diagnostics"]["counts"]["synthetic_project"] == 1


def test_cached_comparisons_do_not_rescan_projects(tmp_path, monkeypatch) -> None:
    store = JsonStore(tmp_path)
    current = _persist(store, _current_document())
    _persist(store, _historical_document("prj_cached", 20))
    metric_index = HistoricalMetricIndex(store)
    metric_index.rebuild()

    def unexpected_load(*_args, **_kwargs):
        raise AssertionError("a valid derived index must not rescan project JSON")

    monkeypatch.setattr(store, "load_project", unexpected_load)
    assert metric_index.comparisons(current)["comparisons"][0]["sample_size"] == 1


def test_invalid_cache_rebuilds_and_stale_derived_write_conflicts(tmp_path) -> None:
    store = JsonStore(tmp_path)
    metric_index = HistoricalMetricIndex(store)
    invalid = store.save_historical_index({"schema": "wrong", "version": "bad"}, metric_index.name)

    rebuilt = metric_index.load_or_rebuild()

    assert invalid["revision"] == 1
    assert rebuilt["schema"] == historical.INDEX_SCHEMA
    assert rebuilt["revision"] == 2
    current = store.save_historical_index(rebuilt, metric_index.name, expected_revision=2)
    assert current["revision"] == 3
    with pytest.raises(ConflictError):
        store.save_historical_index(rebuilt, metric_index.name, expected_revision=2)


def test_malformed_project_is_isolated_during_rebuild(tmp_path) -> None:
    store = JsonStore(tmp_path)
    valid = _persist(store, _historical_document("prj_valid_alongside_bad", 20))
    malformed_id = "prj_malformed_nested"
    malformed = deepcopy(valid)
    malformed["project"] = None
    JsonStore.atomic_write(store.project_path(malformed_id), malformed)

    rebuilt = HistoricalMetricIndex(store).rebuild()

    assert rebuilt["projects"][malformed_id]["project_exclusion"]["reason"] == "malformed_project"
    assert len(rebuilt["observations_by_code"][canonical_cost_code(CODE)]) == 1


def test_synthetic_reclassification_rebuilds_duplicate_descendants(tmp_path) -> None:
    store = JsonStore(tmp_path)
    source = _persist(store, _historical_document("prj_source", 20))
    duplicate = _historical_document("prj_duplicate_descendant", 30)
    duplicate["audit_events"] = [{
        "operation": "duplicate", "prior_value": {"source_project_id": source["project"]["id"]},
    }]
    _persist(store, duplicate)
    metric_index = HistoricalMetricIndex(store)
    initial = metric_index.rebuild()
    assert len(initial["observations_by_code"][canonical_cost_code(CODE)]) == 2

    source["project"]["data_classification"] = " synthetic-test "
    source = store.save_project(source, source["project"]["revision"])
    refreshed = metric_index.refresh_project(source)

    assert refreshed["projects"][source["project"]["id"]]["synthetic"] is True
    assert refreshed["projects"][duplicate["project"]["id"]]["synthetic"] is True
    assert canonical_cost_code(CODE) not in refreshed["observations_by_code"]


def test_working_only_save_skips_evidence_reextraction_and_cache_write(tmp_path, monkeypatch) -> None:
    store = JsonStore(tmp_path)
    document = _persist(store, _historical_document("prj_stable", 20))
    metric_index = HistoricalMetricIndex(store)
    initial = metric_index.rebuild()
    path = store.historical_index_path(metric_index.name)
    before = path.read_bytes()

    document["project"]["notes"] = "Ordinary autosave after the frozen submission"
    document["working_estimate"]["cost_code_summaries"] = deepcopy(
        _current_document("prj_unused", 999)["working_estimate"]["cost_code_summaries"]
    )
    document = store.save_project(document, document["project"]["revision"])

    def unexpected_extract(*_args, **_kwargs):
        raise AssertionError("unchanged frozen evidence must not be re-extracted")

    monkeypatch.setattr(historical, "_extract_state", unexpected_extract)
    refreshed = metric_index.refresh_project(document)

    assert refreshed["revision"] == initial["revision"]
    assert path.read_bytes() == before


def test_stable_submission_metadata_change_refreshes_effective_date(tmp_path) -> None:
    store = JsonStore(tmp_path)
    document = _persist(store, _historical_document("prj_date_change", 20))
    metric_index = HistoricalMetricIndex(store)
    initial = metric_index.rebuild()
    document["submissions"][0]["submitted_at"] = "2025-04-15T09:30:00+00:00"
    document = store.save_project(document, document["project"]["revision"])

    refreshed = metric_index.refresh_project(document)

    assert refreshed["revision"] == initial["revision"] + 1
    observation = refreshed["observations_by_code"][canonical_cost_code(CODE)][0]
    assert observation["effective_date"] == "2025-04-15T09:30:00+00:00"


def test_new_calculations_tag_cost_code_summary_metric() -> None:
    document = new_project("Metric tag", "Estimator", "Estimator")
    document["cost_codes"] = [
        {"id": "ccd_metric", "code": CODE, "description": "Entrances", "deduct": False}
    ]
    calculate_project(document, default_configuration())
    assert document["working_estimate"]["cost_code_summaries"][0]["metric_definition"] == BID_COST_CODE_SELL_PER_SF_METRIC


def test_historical_api_contract(tmp_path, monkeypatch) -> None:
    import app.main as main

    store = JsonStore(tmp_path)
    store.save_configuration(default_configuration())
    current = _persist(store, _current_document("prj_api_current", 30))
    for index, value in enumerate((10, 20, 30, 40, 50), start=1):
        _persist(store, _historical_document(f"prj_api_history_{index}", value))
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)

    bulk = client.get(f"/api/projects/{current['project']['id']}/historical/bid-cost-codes")
    assert bulk.status_code == 200
    payload = bulk.json()
    assert set(payload) == {
        "project_revision", "metric_definition", "minimum_sample",
        "comparable_project_type", "comparisons", "alternate_id",
    }
    assert payload["alternate_id"] is None
    assert payload["project_revision"] == 1
    assert payload["comparisons"][0]["status"] == "classified"
    assert {"minimum", "maximum", "current_value", "median", "q1", "q3", "percentile"} <= set(payload["comparisons"][0])

    detail = client.get(
        f"/api/projects/{current['project']['id']}/historical/bid-cost-code",
        params={"code": CODE},
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["project_revision"] == 1
    assert detail_payload["comparison"]["code"] == CODE
    assert len(detail_payload["observations"]) == 5
    assert {"provenance", "rules", "exclusion_diagnostics"} <= set(detail_payload)


def test_historical_reference_seed_has_takeoff_margin_and_project_type_context(tmp_path) -> None:
    store = JsonStore(tmp_path)
    result = seed_historical_bids(store, 100, 4320)

    assert result == {"bids": 100, "observations": 400, "cost_codes": 4, "index_revision": 1}
    assert list(store.projects.glob("*.json")) == []
    assert len(list(store.historical_reference.glob("*.json"))) == 100
    index = HistoricalMetricIndex(store).load_or_rebuild()
    observations = [item for values in index["observations_by_code"].values() for item in values]
    assert len(observations) == 400
    assert {item["project_type"] for item in observations} == set(PROJECT_TYPES)
    assert all(item["data_classification"] == "historical_reference_fixture" for item in observations)
    assert all(Decimal(item["direct_cost"]) > 0 and Decimal(item["margin_percentage"]) > 0 for item in observations)
    first_document = store._read(next(store.historical_reference.glob("*.json")))
    frozen = first_document["estimate_revisions"][0]
    assert frozen["immutable"] is True and frozen["status"] == "submitted"
    assert all(section["lines"] and Decimal(section["totals"]["square_feet"]) > 0 for section in frozen["source_snapshot"]["takeoff_sections"])


def test_historical_compatibility_prefers_same_project_type() -> None:
    current = {"deduct": False, "project_type": "New Construction - Curtainwall"}
    matching = {"project_id": "a", "deduct": False, "metric_definition": BID_COST_CODE_SELL_PER_SF_METRIC,
                "project_type": "New Construction - Curtainwall"}
    different = {**matching, "project_id": "b", "project_type": "Repair - Windows"}
    assert HistoricalMetricIndex._compatible(matching, current, "current") is True
    assert HistoricalMetricIndex._compatible(different, current, "current") is False
