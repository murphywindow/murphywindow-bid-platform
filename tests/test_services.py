from copy import deepcopy
from decimal import Decimal as D

import pytest

from app.alternates import add_record, new_alternate
from app.schema import INTERCHANGE_VERSION, default_configuration, new_project
from app.services import (
    DomainError, activate, calculate_project, create_change_order, job_data,
    edit_bid_source, provisional_closeout, redact, reestimate_contract, save_sov,
    select_used_quotes, submission_blockers, submit, sync_labor_candidates,
    update_change_order_status,
)


def example():
    cfg = default_configuration()
    cfg["tax_rates"][0]["rate"] = ".10"
    cfg["markup_defaults"]["base_product"]["rate"] = ".20"
    cfg["markup_defaults"]["LAF"]["rate"] = ".30"
    cfg["markup_defaults"]["LAS"]["rate"] = ".40"
    cfg["pco"]["markup_one"] = ".10"; cfg["pco"]["markup_two"] = ".20"
    doc = new_project("Service Test", "Est", "Estimator")
    doc["project"].update({
        "project_type": "New Construction - Exterior Storefront", "project_type_status": "current",
        "contract_type": "Bid to CM/GC", "contract_type_status": "current",
        "wage_type": "Non-PW", "wage_type_status": "current",
    })
    doc["cost_codes"] = [{"id":"ccd_1","code":"08 40 00","description":"Entrances","deduct":False},{"id":"ccd_2","code":"07 90 00","description":"Sealants","deduct":True}]
    doc["quotes"] = [
        {"id":"quo_base","group_id":"g1","code":"08 40 00","price":"1000","surcharge_percent":".10","tax_included":False,"used":True},
    ]
    doc["takeoff_sections"] = [{"id":"sec_1","definition_id":"frame-v1","code":"08 40 00","name":"Frames","lines":[{"id":"frm_1","quantity":1,"width_inches":12,"height_inches":12,"caulking_passes":3}],"material_overrides":{},"tie_back_qty":0,"backpan_lf":0}]
    doc["labor_estimates"] = [{"id":"lbr_1","category":"field","code":"08 40 00","description":"Install","quantity":100,"crew":2,"productivity":5,"rate":50}]
    return doc, cfg


def test_bid_assembly_tax_markups_lineage_and_alternates():
    doc, cfg = example()
    alternate = new_alternate(doc, "Added supplier scope")
    add_record(alternate, "equipment", {"id": "eqp_alt", "code": "08 40 00", "description": "Alternate lift",
                                         "quantity": 1, "duration": 1, "rate": 500, "delivery": 0, "taxable": False})
    doc["alternates"] = [alternate]
    calculate_project(doc, cfg)
    quote = next(x for x in doc["working_estimate"]["lines"] if x["category"] == "base_product")
    assert D(quote["direct_cost"]) == D("1210")  # quote cost 1100 plus 10% tax
    assert D(quote["selling_value"]) == D("1452")
    labor = next(x for x in doc["working_estimate"]["lines"] if x["category"] == "field_labor")
    assert D(labor["direct_cost"]) == D("500")
    assert D(labor["selling_value"]) == D("650")
    assert quote["lineage"][0]["source_id"] == "quo_base"
    assert not any(x["code"].startswith("ALT1") for x in doc["working_estimate"]["lines"])
    assert alternate["calculated"]["classification"] == "add"
    assert D(alternate["calculated"]["direct_cost_delta"]) == D("500.00")
    assert D(alternate["calculated"]["selling_value_delta"]) > D("500.00")
    assert not any(line.get("source_key") == "equipment:eqp_alt" for line in doc["working_estimate"]["lines"])


def test_frame_calculated_quantities_retain_fractional_results_through_project_calculation():
    doc, cfg = example()
    frame = doc["takeoff_sections"][0]["lines"][0]
    frame.update({
        "quantity": "3.05", "width_inches": "42.75", "height_inches": "120.5",
        "caulking_passes": "3.11",
    })

    calculate_project(doc, cfg)

    calculated = frame["calculated"]
    expected_perimeter = D("2") * (D("42.75") / D("12") + D("120.5") / D("12")) * D("3.05")
    assert D(calculated["square_feet"]) == D("3.05") * D("42.75") * D("120.5") / D("144")
    assert D(calculated["perimeter_lf"]) == expected_perimeter
    assert D(calculated["caulking_lf"]) == expected_perimeter * D("3.11")
    assert D(calculated["head_sill_qty"]) == D("3.05") * D("42.75") / D("6")
    assert all(not D(calculated[key]) == D(calculated[key]).to_integral_value() for key in (
        "square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty",
    ))


def test_owner_reference_validates_code_preserves_invalid_and_fills_description():
    doc,cfg=example()
    doc["cost_codes"].append({"id":"ccd_invalid","code":"NOT A CODE","description":"","deduct":False})
    doc["cost_codes"][0]["description"]=""
    calculate_project(doc,cfg)
    assert doc["cost_codes"][0]["description"]
    warning=next(x for x in doc["working_estimate"]["validation"] if x["code"]=="invalid_cost_code")
    assert warning["entity_id"]=="ccd_invalid"
    assert doc["cost_codes"][-1]["code"]=="NOT A CODE"


def test_owner_reference_does_not_overwrite_manually_adjusted_description():
    doc, cfg = example()
    doc["cost_codes"][0]["description"] = "Project-specific storefront package"
    calculate_project(doc, cfg)
    assert doc["cost_codes"][0]["description"] == "Project-specific storefront package"


def test_deduct_sign_flows_to_material_cost():
    doc, cfg = example()
    doc["takeoff_sections"][0]["code"] = "07 90 00"
    calculate_project(doc, cfg)
    materials = [x for x in doc["working_estimate"]["lines"] if x["category"] == "installation_material"]
    assert materials
    assert all(D(x["direct_cost"]) < 0 for x in materials)


def test_frame_line_material_applicability_and_pre_tax_section_summary():
    doc, cfg = example()
    section = doc["takeoff_sections"][0]
    section["lines"].append({
        "id": "frm_2", "quantity": 1, "width_inches": 12, "height_inches": 12,
        "caulking_passes": 3, "installation_material_ids": ["mat_bracing"],
    })
    section["lines"][0]["installation_material_ids"] = ["mat_sealant"]
    calculate_project(doc, cfg)
    results = {row["material_rule_id"]: row for row in section["material_results"]}
    assert D(results["mat_bracing"]["source_quantity"]) == D("4")
    assert D(results["mat_sealant"]["source_quantity"]) == D("12")
    assert results["mat_membrane"]["source_quantity"] == "0"
    assert D(results["mat_sealant"]["pre_tax_cost"]) == D("11.52")
    assert D(section["pre_tax_material_cost"]) == D("17.52")
    assert D(section["pre_tax_material_cost_per_sf"]) == D("8.76")


def test_missing_frame_material_selection_means_all_materials_selected():
    doc, cfg = example()
    calculate_project(doc, cfg)
    results = {row["material_rule_id"]: row for row in doc["takeoff_sections"][0]["material_results"]}
    assert D(results["mat_bracing"]["source_quantity"]) == D("4")
    assert D(results["mat_sealant"]["source_quantity"]) == D("12")


def test_quote_selection_is_implicit_by_code_uses_adjusted_cost_and_locks_manual_choice():
    doc, cfg = example()
    doc["quotes"] = [
        {"id": "quo_a", "group_id": "historical-a", "code": "08 40 00", "price": "1000",
         "credit_type": "percentage", "credit_value": ".10", "surcharge_type": "percentage",
         "surcharge_value": ".10", "tax_included": True, "used": False, "square_feet": None,
         "square_feet_source": "unassigned"},
        {"id": "quo_b", "group_id": "historical-b", "code": "08-40-00", "price": "950",
         "credit_type": "dollar", "credit_value": "0", "surcharge_type": "dollar",
         "surcharge_value": "0", "tax_included": True, "used": False, "square_feet": "777",
         "square_feet_source": "manual"},
    ]
    doc["working_estimate"]["quote_selection_by_code"] = {
        "08 40 00": {"mode": "automatic", "selected_quote_ids": []},
    }
    calculate_project(doc, cfg)
    assert D(doc["quotes"][0]["calculated_cost"]) == D("990")
    assert D(doc["quotes"][1]["calculated_cost"]) == D("950")
    assert [row["id"] for row in doc["quotes"] if row["used"]] == ["quo_b"]
    assert D(doc["quotes"][0]["square_feet"]) == D("1")
    assert doc["quotes"][0]["square_feet_source"] == "frame_default"
    assert doc["quotes"][1]["square_feet"] == "777"

    doc["working_estimate"]["quote_selection_by_code"]["08 40 00"] = {
        "mode": "manual", "selected_quote_ids": ["quo_b"],
    }
    doc["quotes"][1]["price"] = "5000"
    calculate_project(doc, cfg)
    assert [row["id"] for row in doc["quotes"] if row["used"]] == ["quo_b"]
    lineage = doc["quotes"][0]["calculation_lineage"]
    assert D(lineage["credit_amount"]) == D("100")
    assert D(lineage["post_credit_subtotal"]) == D("900")
    assert D(lineage["surcharge_amount"]) == D("90")


def test_quote_frame_default_combines_frame_sections_but_excludes_borrowed_lites():
    doc, cfg = example()
    doc["takeoff_sections"].append({
        "id": "sec_2", "definition_id": "frame-v1", "code": "08 40 00", "name": "More frames",
        "lines": [{"id": "frm_2", "quantity": 2, "width_inches": 12, "height_inches": 12}],
        "material_overrides": {}, "tie_back_qty": 0, "backpan_lf": 0,
    })
    doc["borrowed_lites"] = [{
        "id": "brl_1", "code": "08 40 00", "quantity": 1, "width_inches": 12,
        "height_inches": 12, "rate": None,
    }]
    doc["quotes"][0].update({"square_feet": None, "square_feet_source": "unassigned"})
    calculate_project(doc, cfg)
    assert D(doc["quotes"][0]["square_feet"]) == D("3")
    summary = next(row for row in doc["working_estimate"]["cost_code_summaries"] if row["code"] == "08 40 00")
    assert D(summary["total_square_feet"]) == D("8")  # 3 Frame SF + BRL's five-SF row minimum.


def test_frame_and_door_missing_quantities_are_structured_blockers_and_acknowledged_exceptions():
    doc, cfg = example()
    doc["takeoff_sections"][0]["lines"].append({
        "id": "frm_missing", "mark": "F-missing", "quantity": 0,
        "width_inches": 48, "height_inches": 96, "missing_quantity_acknowledged": False,
    })
    doc["doors"] = [{
        "id": "dor_missing", "code": "08 40 00", "door_number": "D-missing",
        "leaf_quantity": None, "width_inches": 36, "height_inches": 84,
        "missing_quantity_acknowledged": False,
    }]
    calculate_project(doc, cfg)
    quantity_issues = [item for item in submission_blockers(doc) if item["code"] in {"missing_frame_quantity", "missing_door_quantity"}]
    assert {item["entity_id"] for item in quantity_issues} == {"frm_missing", "dor_missing"}

    doc["takeoff_sections"][0]["lines"][-1]["missing_quantity_acknowledged"] = True
    doc["doors"][0]["missing_quantity_acknowledged"] = True
    calculate_project(doc, cfg)
    visible = [item for item in doc["working_estimate"]["validation"] if item["entity_id"] in {"frm_missing", "dor_missing"}]
    assert all(item["acknowledged"] and not item["blocking"] for item in visible)
    assert not [item for item in submission_blockers(doc) if item["entity_id"] in {"frm_missing", "dor_missing"}]


def test_installation_material_controlled_override_and_effective_values_are_distinct():
    doc, cfg = example()
    original_rule = deepcopy(next(rule for rule in cfg["material_rules"] if rule["id"] == "mat_sealant"))
    doc["takeoff_sections"][0]["material_overrides"]["mat_sealant"] = {
        "factor_override": ".10", "rate_override": "15",
        "rate_override_reason": "Project supplier quotation",
    }
    calculate_project(doc, cfg)
    result = next(row for row in doc["takeoff_sections"][0]["material_results"] if row["material_rule_id"] == "mat_sealant")
    assert result["controlled_factor"] == "0.08"
    assert result["factor_override"] == "0.10"
    assert result["factor"] == "0.10"
    assert result["controlled_rate"] == "12.00"
    assert result["rate_override"] == "15"
    assert result["effective_rate"] == "15"
    assert result["pre_tax_cost"] == "18.00"
    assert result["rate_override_reason"] == "Project supplier quotation"
    assert next(rule for rule in cfg["material_rules"] if rule["id"] == "mat_sealant") == original_rule


def test_equipment_subtotal_is_pre_tax_and_each_row_honors_taxable_flag():
    doc, cfg = example()
    doc["equipment"] = [
        {"id": "eqp_tax", "code": "08 40 00", "description": "Taxed lift", "quantity": 1,
         "duration": 2, "rate": 100, "delivery": 10, "taxable": True},
        {"id": "eqp_exempt", "code": "08 40 00", "description": "Exempt lift", "quantity": 1,
         "duration": 1, "rate": 50, "delivery": 0, "taxable": False},
    ]
    calculate_project(doc, cfg)
    assert D(doc["working_estimate"]["equipment_subtotal"]) == D("260")
    lines = {line["lineage"][0]["source_id"]: line for line in doc["working_estimate"]["lines"] if line["category"] == "equipment"}
    assert lines["eqp_tax"]["direct_cost"] == "231.00"
    assert D(lines["eqp_tax"]["lineage"][0]["pre_tax_cost"]) == D("210")
    assert D(lines["eqp_exempt"]["direct_cost"]) == D("50")
    assert lines["eqp_exempt"]["tax_treatment"] == "exempt"


def test_labor_cost_schedule_rate_lineage_and_unavailable_commercial_rules():
    doc, cfg = example()
    snapshot = {
        "rate": "50", "rate_id": "labor_field_nonpw_2025", "configuration_id": cfg["id"],
        "source": "controlled test", "status": "owner_provided",
    }
    doc["labor_estimates"] = [{
        "id": "lbr_canonical", "code": "08 40 00", "description": "Canonical field work",
        "labor_type": "Field", "man_hours": "80", "man_hours_source": "manual",
        "crew_size": "2", "hours_per_worker_per_day": "8", "workdays_per_week": "5",
        "controlled_rate_snapshot": deepcopy(snapshot), "rate_override": "75",
        "rate_override_reason": "Approved project condition", "origin": "manual",
        "source_links": [], "source_status": "unclassified", "stale_acknowledged": False,
    }, {
        "id": "lbr_design", "code": "08 40 00", "description": "Design coordination",
        "labor_type": "Design", "man_hours": "10", "crew_size": "1",
        "hours_per_worker_per_day": "8", "workdays_per_week": "5",
        "controlled_rate_snapshot": {"rate": None, "rate_id": "labor_design_unavailable", "configuration_id": cfg["id"], "status": "unavailable"},
        "rate_override": None, "origin": "manual", "source_links": [], "source_status": "unclassified",
    }]
    doc["travel_estimates"] = [{"id": "trv_unresolved", "code": "08 40 00", "enabled": True}]
    calculate_project(doc, cfg)
    row = doc["labor_estimates"][0]
    assert row["controlled_rate_snapshot"] == snapshot
    assert row["calculated_controlled_rate"] == "50"
    assert row["calculated_effective_rate"] == "75"
    assert D(row["calculated_cost"]) == D("6000")
    assert row["shift_configuration"] == "5x8"
    assert row["calculated_working_days"] == "5"
    assert row["calculated_calendar_weeks"] == "1"
    assert row["calculated_calendar_days"] == "7"
    line = next(line for line in doc["working_estimate"]["lines"] if line.get("source_key") == "labor:lbr_canonical")
    assert D(line["direct_cost"]) == D("6000")
    assert line["lineage"][0]["man_hours"] == "80"
    assert line["lineage"][0]["effective_rate"] == "75"
    blocker_codes = {item["code"] for item in submission_blockers(doc)}
    assert {"unavailable_design_rate", "travel_policy_unavailable"} <= blocker_codes
    assert not [line for line in doc["working_estimate"]["lines"] if line.get("source_key") == "labor:lbr_design"]


def test_labor_suggestions_are_unique_source_linked_excludable_and_stale_acknowledgeable():
    doc, cfg = example()
    doc["quotes"] = [doc["quotes"][0]]
    doc["labor_estimates"] = []
    doc["doors"] = [{"id": "dor_1", "code": "08 40 00", "leaf_quantity": 1}]
    doc["hardware_assignments"] = [{"id": "hwa_1", "door_id": "dor_1", "code": "07 90 00"}]
    doc["equipment"] = [{"id": "eqp_1", "code": "08 40 00"}]
    doc["borrowed_lites"] = [{"id": "brl_1", "code": "08 40 00"}]
    doc["working_estimate"]["labor_suggestion_exclusions"] = ["07 90 00"]
    created = sync_labor_candidates(doc, cfg)
    assert len(created) == 1
    candidate = created[0]
    assert candidate["code"] == "08 40 00"
    assert {link["source_type"] for link in candidate["source_links"]} == {"quote", "frame", "door", "equipment", "borrowed_lite"}
    assert "door_hardware" not in {link["source_type"] for link in candidate["source_links"]}
    assert not sync_labor_candidates(doc, cfg)

    doc["working_estimate"]["labor_suggestion_exclusions"] = []
    hardware_candidates = sync_labor_candidates(doc, cfg)
    assert len(hardware_candidates) == 1
    assert hardware_candidates[0]["code"] == "07 90 00"
    assert hardware_candidates[0]["source_links"] == [{"source_type": "door_hardware", "source_id": "hwa_1"}]

    doc["quotes"] = []
    doc["takeoff_sections"] = []
    doc["doors"] = []
    doc["hardware_assignments"] = []
    doc["equipment"] = []
    doc["borrowed_lites"] = []
    sync_labor_candidates(doc, cfg)
    assert candidate["source_status"] == "stale"
    calculate_project(doc, cfg)
    assert any(item["code"] == "stale_labor_source" and item["blocking"] for item in submission_blockers(doc))
    candidate["stale_acknowledged"] = True
    calculate_project(doc, cfg)
    warning = next(item for item in doc["working_estimate"]["validation"] if item["code"] == "stale_labor_source")
    assert warning["acknowledged"] and not warning["blocking"]


def test_bid_code_summary_uses_area_once_and_preserves_component_markup_provenance():
    doc, cfg = example()
    doc["borrowed_lites"] = [{
        "id": "brl_area", "code": "08 40 00", "quantity": 1,
        "width_inches": 12, "height_inches": 12, "rate": "10",
    }]
    doc["working_estimate"]["borrowed_lite_source_by_code"] = {"08 40 00": "internal"}
    doc["working_estimate"]["component_markup_overrides"] = {
        "quote:quo_base": {"rate": ".50", "reason": "Estimator source-line decision", "source": "Estimator"},
    }
    calculate_project(doc, cfg)
    quote_line = next(line for line in doc["working_estimate"]["lines"] if line.get("source_key") == "quote:quo_base")
    assert quote_line["markup_default_rate"] == ".20"
    assert quote_line["markup_override_rate"] == ".50"
    assert quote_line["markup_provenance"]["effective_rate"] == ".50"
    assert quote_line["markup_provenance"]["override_reason"] == "Estimator source-line decision"
    summary = next(row for row in doc["working_estimate"]["cost_code_summaries"] if row["code"] == "08 40 00")
    assert D(summary["total_square_feet"]) == D("6")
    assert {component["name"] for component in summary["components"]} >= {"Base Product", "Installation Materials", "LAF", "Borrowed Lites"}
    assert set(summary["source_line_ids"]) == {
        line["id"] for line in doc["working_estimate"]["lines"] if line["code"] == "08 40 00"
    }
    assert D(summary["dollars_per_square_foot"]) == D(summary["selling_value"]) / D("6")


def test_project_specific_installation_material_calculates_and_groups_in_bid():
    doc, cfg = example()
    section = doc["takeoff_sections"][0]
    section["additional_materials"] = [{
        "id": "matp_custom", "name": "Custom perimeter flashing", "source": "perimeter_lf",
        "factor": ".5", "unit": "LF", "cost_code": "08 40 00", "project_specific": True,
    }]
    section["material_overrides"]["matp_custom"] = {"rate_override": "10", "rate_override_reason": "Project quote"}
    calculate_project(doc, cfg)
    result = next(row for row in section["material_results"] if row["material_rule_id"] == "matp_custom")
    assert D(result["source_quantity"]) == D("4")
    assert D(result["pre_tax_cost"]) == D("20")
    assert result["project_specific"] is True
    line = next(row for row in doc["working_estimate"]["lines"] if row["source_key"].endswith(":matp_custom"))
    assert line["category"] == "installation_material"
    assert line["lineage"][0]["section_name"] == "Frames"
    component = next(row for row in doc["working_estimate"]["cost_code_summaries"][0]["components"] if row["name"] == "Installation Materials")
    assert line["id"] in component["source_line_ids"]


def test_bid_components_keep_laf_las_and_markup_reconciliation_distinct():
    doc, cfg = example()
    doc["labor_estimates"].extend([
        {"id": "lbr_shop", "labor_type": "Shop", "code": "08 40 00", "description": "Shop Labor",
         "man_hours": "10", "controlled_rate_snapshot": {"rate": "40"}, "origin": "manual"},
        {"id": "lbr_design", "labor_type": "Design", "code": "08 40 00", "description": "Design Labor",
         "man_hours": "5", "controlled_rate_snapshot": {"rate": "50"}, "origin": "manual"},
    ])
    calculate_project(doc, cfg)
    summary = next(row for row in doc["working_estimate"]["cost_code_summaries"] if row["code"] == "08 40 00")
    components = {row["name"]: row for row in summary["components"]}
    assert {"Base Product", "Installation Materials", "LAF", "LAS", "Design Labor"} <= set(components)
    for component in components.values():
        assert D(component["selling_value"]) - D(component["direct_cost"]) == D(component["margin_dollars"])
        assert component["source_count"] == len(component["source_line_ids"])


def test_custom_material_manual_basis_and_frame_applicability_are_canonical():
    doc, cfg = example()
    section = doc["takeoff_sections"][0]
    section["additional_materials"] = [{"id": "matp_manual", "name": "Custom Material A", "source": "manual_quantity", "manual_quantity": "7.5", "factor": "2", "unit": "each", "cost_code": "08 40 00"}]
    section["material_overrides"]["matp_manual"] = {"rate_override": "3"}
    calculate_project(doc, cfg)
    result = next(row for row in section["material_results"] if row["material_rule_id"] == "matp_manual")
    assert D(result["source_quantity"]) == D("7.5") and D(result["pre_tax_cost"]) == D("45")
    section["additional_materials"][0].update({"source": "perimeter_lf", "factor": "1"})
    section["lines"][0]["installation_material_ids"] = ["mat_sealant"]
    calculate_project(doc, cfg)
    result = next(row for row in section["material_results"] if row["material_rule_id"] == "matp_manual")
    assert result["source_quantity"] == "0"
    section["additional_materials"][0]["source"] = "quantity"
    section["lines"][0]["installation_material_ids"].append("matp_manual")
    calculate_project(doc, cfg)
    result = next(row for row in section["material_results"] if row["material_rule_id"] == "matp_manual")
    assert result["source_quantity"] == "1"


def test_installation_material_markup_inherits_configured_base_product_rate_until_distinct_rate_exists():
    doc, cfg = example()
    cfg["markup_defaults"]["base_product"]["rate"] = ".25"
    cfg["markup_defaults"]["installation_material"] = {
        "rate": None, "inherits": "base_product", "status": "pending_distinct_rate",
    }
    doc["working_estimate"]["markup_overrides"] = {}
    calculate_project(doc, cfg)

    material = next(
        line for line in doc["working_estimate"]["lines"]
        if line["category"] == "installation_material"
    )
    assert material["markup_rate"] == ".25"
    assert material["markup_provenance"]["configuration_default_rate"] == ".25"
    assert material["markup_provenance"]["inherited_from"] == "base_product"


def test_bid_source_edit_requires_confirmation_updates_canonical_record_and_audits():
    doc, cfg = example()
    calculate_project(doc, cfg)
    with pytest.raises(DomainError) as exc:
        edit_bid_source(doc, cfg, "Est", "Estimator", {
            "source_type": "quote", "source_id": "quo_base", "changes": {"price": "1200"},
        })
    assert exc.value.code == "confirmation_required"
    prior_version = doc["project"]["bid_version"]["patch"]
    edited = edit_bid_source(doc, cfg, "Est", "Estimator", {
        "confirmed": True, "source_type": "quote", "source_id": "quo_base",
        "changes": {"price": "1200"}, "reason": "Confirmed supplier revision",
    })
    assert edited is doc["quotes"][0]
    assert doc["quotes"][0]["price"] == "1200"
    assert doc["quotes"][0]["calculated_cost"] == "1320.00"
    assert doc["project"]["bid_version"]["patch"] == prior_version + 1
    event = doc["audit_events"][-1]
    assert event["operation"] == "bid_source_edit"
    assert event["entity_id"] == "quo_base"
    assert event["reason"] == "Confirmed supplier revision"

    edit_bid_source(doc, cfg, "Est", "Estimator", {
        "confirmed": True, "source_type": "quote", "source_id": "quo_base",
        "changes": {"square_feet": "250"}, "reason": "Estimator confirmed quote area",
    })
    assert doc["quotes"][0]["square_feet"] == "250"
    assert doc["quotes"][0]["square_feet_source"] == "manual"


def test_bid_markup_override_uses_stable_source_key_and_can_be_cleared_without_editing_source():
    doc, cfg = example()
    calculate_project(doc, cfg)
    original_quote = deepcopy(doc["quotes"][0])
    result = edit_bid_source(doc, cfg, "Est", "Estimator", {
        "confirmed": True, "source_type": "quote", "source_id": "quo_base",
        "changes": {"markup_override": ".55"}, "reason": "Unique quote risk",
        "correlation_id": "cor_markup_set",
    })
    assert result == {"source_key": "quote:quo_base", "markup_override": "0.55", "cleared": False}
    assert doc["quotes"][0]["price"] == original_quote["price"]
    assert doc["working_estimate"]["component_markup_overrides"]["quote:quo_base"]["rate"] == "0.55"
    line = next(item for item in doc["working_estimate"]["lines"] if item.get("source_key") == "quote:quo_base")
    assert line["markup_override_rate"] == "0.55"
    assert doc["audit_events"][-1]["operation"] == "set_bid_markup_override"
    assert doc["audit_events"][-1]["correlation_id"] == "cor_markup_set"

    cleared = edit_bid_source(doc, cfg, "Est", "Estimator", {
        "confirmed": True, "source_type": "quote", "source_id": line["id"],
        "changes": {"markup_override": None}, "reason": "Return to current default",
    })
    assert cleared["cleared"] is True
    assert "quote:quo_base" not in doc["working_estimate"]["component_markup_overrides"]
    line = next(item for item in doc["working_estimate"]["lines"] if item.get("source_key") == "quote:quo_base")
    assert line["markup_override_rate"] is None
    assert line["markup_rate"] == ".20"
    assert doc["audit_events"][-1]["operation"] == "clear_bid_markup_override"


def test_submission_blockers_include_controlled_project_and_pending_paste_states():
    doc, cfg = example()
    doc["project"]["project_type"] = "Historical freeform type"
    doc["project"]["project_type_status"] = "legacy_unsupported"
    doc["working_estimate"]["pending_controlled_values"] = [{
        "table_id": "quotes", "row_id": "quo_base", "field": "code",
        "entered_value": "bad", "message": "Select a controlled Cost Code.",
    }]
    calculate_project(doc, cfg)
    blockers = submission_blockers(doc)
    assert any(item["code"] == "invalid_project_type" and item["field"] == "project_type" for item in blockers)
    pending = next(item for item in blockers if item["code"] == "pending_controlled_value")
    assert pending["entity_id"] == "quo_base" and pending["entered_value"] == "bad"
    with pytest.raises(DomainError) as exc:
        submit(doc, cfg, "Est", "Estimator", {})
    assert {item["code"] for item in exc.value.details} >= {"invalid_project_type", "pending_controlled_value"}


def test_historical_source_code_missing_from_project_scope_is_a_submission_blocker():
    doc, cfg = example()
    doc["equipment"] = [{
        "id": "eqp_legacy_orphan", "code": "99 99 99", "description": "Legacy orphan",
        "quantity": 1, "duration": 1, "rate": "100", "delivery": "0", "taxable": True,
    }]
    calculate_project(doc, cfg)
    blocker = next(item for item in submission_blockers(doc) if item["code"] == "invalid_source_cost_code")
    assert blocker["entity_id"] == "eqp_legacy_orphan"


def test_pw_without_selected_controlled_record_never_falls_back_to_non_pw_rate():
    doc, cfg = example()
    doc["project"].update({"wage_type": "PW", "wage_type_status": "current", "wage_data_id": None})
    doc["labor_estimates"] = [{
        "id": "lbr_pw", "code": "08 40 00", "description": "PW field work",
        "labor_type": "Field", "man_hours": "10", "origin": "manual",
    }]
    calculate_project(doc, cfg)
    row = doc["labor_estimates"][0]
    assert row["calculated_controlled_rate"] is None
    assert row["calculated_cost"] is None
    assert {item["code"] for item in submission_blockers(doc)} >= {"missing_prevailing_wage_record", "missing_labor_rate"}

    wage = next(item for item in cfg["wage_records"] if item.get("estimated_company_rate") not in (None, ""))
    doc["project"]["wage_data_id"] = wage["id"]
    calculate_project(doc, cfg)
    assert doc["labor_estimates"][0]["calculated_controlled_rate"] == str(wage["estimated_company_rate"])
    assert doc["labor_estimates"][0]["calculated_cost"] is not None


def test_submission_immutable_revision_and_later_working_edit():
    doc, cfg = example(); calculate_project(doc, cfg)
    assert doc["project"]["bid_version"]["display"] == "B0.0.0"
    submission = submit(doc, cfg, "Est", "Estimator", {"recipient":"GC","method":"email","reason":"Initial"})
    assert doc["project"]["bid_version"]["display"] == "B0.1.0"
    assert doc["estimate_revisions"][0]["bid_version"]["display"] == "B0.1.0"
    frozen = deepcopy(doc["estimate_revisions"][0])
    doc["quotes"][0]["price"] = "2000"; calculate_project(doc, cfg)
    assert doc["estimate_revisions"][0] == frozen
    assert submission["artifact_id"] == doc["proposal_artifacts"][0]["id"]
    assert doc["proposal_artifacts"][0]["immutable"] is True
    assert doc["proposal_artifacts"][0]["bid_version"]["display"] == "B0.1.0"


def test_submit_permission_and_multiple_used_quotes_are_additive_not_blocking():
    doc, cfg = example(); calculate_project(doc, cfg)
    with pytest.raises(DomainError):
        submit(doc, cfg, "PM", "Project Manager", {})
    doc["quotes"].append({"id":"quo_x","group_id":"historical-other","code":"08 40 00","price":"200","used":True})
    doc["working_estimate"]["quote_selection_by_code"]["08 40 00"] = {
        "mode": "manual", "selected_quote_ids": ["quo_base", "quo_x"],
    }
    calculate_project(doc, cfg)
    used = [row for row in doc["quotes"] if row["code"] == "08 40 00" and row["used"]]
    assert {row["id"] for row in used} == {"quo_base", "quo_x"}
    assert not [item for item in submission_blockers(doc) if item["code"] == "multiple_used_quotes"]
    assert submit(doc, cfg, "Est", "Estimator", {})["revision_id"]


def activated():
    doc, cfg = example(); calculate_project(doc, cfg); submit(doc, cfg, "Est", "Estimator", {"recipient":"GC"})
    rev = doc["estimate_revisions"][0]
    activate(doc, "PM", "Project Manager", {"revision_id":rev["id"],"ntp_date":"2026-01-01","ntp_evidence":"Email 123"})
    return doc, cfg


def test_activation_requires_ntp_authorization_is_idempotent_and_preserves_award():
    doc, cfg = example(); calculate_project(doc, cfg); submit(doc, cfg, "Est", "Estimator", {})
    rev = doc["estimate_revisions"][0]
    with pytest.raises(DomainError): activate(doc,"Est","Estimator",{"revision_id":rev["id"],"ntp_date":"2026-01-01","ntp_evidence":"x"})
    with pytest.raises(DomainError): activate(doc,"PM","Project Manager",{"revision_id":rev["id"]})
    payload={"revision_id":rev["id"],"ntp_date":"2026-01-01","ntp_evidence":"x"}
    first=activate(doc,"PM","Project Manager",payload); second=activate(doc,"PM","Project Manager",payload)
    assert first["id"] == second["id"]
    assert doc["project"]["bid_version"]["display"] == "B1.0.0"
    assert first["accepted_bid_version"]["display"] == "B0.1.0"
    assert first["activation_version"]["display"] == "B1.0.0"
    assert len(doc["contract_allocations"]) == len([x for x in rev["estimate"]["lines"] if x.get("included", True)])
    with pytest.raises(DomainError, match="already"):
        activate(doc,"PM","Project Manager",{**payload,"ntp_evidence":"different"})


def test_contract_reestimate_history_does_not_change_original_award():
    doc, _ = activated(); line=doc["contract_allocations"][0]; original=line["original_cost"]
    result=reestimate_contract(doc,"PM","Project Manager",{"allocation_id":line["id"],"new_cost":"999","reason":"Supplier update"})
    assert result["original_cost"] == original
    assert D(result["current_estimated_cost"]) == D("999")
    assert result["reestimate_history"][0]["reason"] == "Supplier update"
    assert doc["project"]["bid_version"]["display"] == "B1.0.1"
    with pytest.raises(DomainError): reestimate_contract(doc,"Support","Support",{"allocation_id":line["id"],"new_cost":1,"reason":"x"})


def test_pco_sequential_hidden_redaction_and_authorization():
    doc,cfg=activated()
    order=create_change_order(doc,cfg,"PM","Project Manager",{"identifier":"PCO-1","cost_lines":[{"description":"Change","cost":"100","taxable":False}]})
    assert D(order["customer_price"]) == D("132")
    assert redact(doc,"Estimator")["change_orders"][0].get("markup_one_restricted") is None
    assert redact(doc,"Project Manager")["change_orders"][0]["markup_one_restricted"] == ".10"
    with pytest.raises(DomainError, match="acknowledge"):
        update_change_order_status(doc,"PM","Project Manager",order["id"],{"status":"approved","reason":"Email"})
    approved=update_change_order_status(doc,"PM","Project Manager",order["id"],{"status":"approved","reason":"Email","pending_policy_acknowledged":True})
    assert approved["contract_effect"] == "applied"
    allocation=next(x for x in doc["contract_allocations"] if x.get("source_change_order_id")==order["id"])
    assert allocation["contract_value"] == order["customer_price"]
    with pytest.raises(DomainError, match="cannot be rejected"):
        update_change_order_status(doc,"PM","Project Manager",order["id"],{"status":"rejected"})
    with pytest.raises(DomainError): create_change_order(doc,cfg,"Est","Estimator",{"cost_lines":[]})


def test_sov_status_and_closeout_provisional():
    doc,_=activated(); allocation=doc["contract_allocations"][0]
    line=save_sov(doc,"PM","Project Manager",{"allocation_id":allocation["id"],"components":[allocation["contract_value"]]})
    assert line["status"] == "exact" and line["approval_status"] == "ready"
    over=save_sov(doc,"PM","Project Manager",{"allocation_id":allocation["id"],"components":[D(allocation["contract_value"])+1]})
    assert over["approval_status"] == "blocked_overallocation"
    close=provisional_closeout(doc,"PM","Project Manager",{"completion_evidence":"Punch list"})
    assert close["status"] == "provisional_pending_policy"


def test_multiple_sov_lines_reconcile_one_allocation_in_aggregate():
    doc,_=activated();allocation=doc["contract_allocations"][0];value=D(allocation["contract_value"])
    first=save_sov(doc,"PM","Project Manager",{"allocation_id":allocation["id"],"description":"A","components":[value/2]})
    assert first["status"] == "underallocated"
    second=save_sov(doc,"PM","Project Manager",{"allocation_id":allocation["id"],"description":"B","components":[value/2]})
    assert second["status"] == "exact"
    assert first["status"] == "exact"
    assert D(second["allocation_scheduled_total"]) == value


def test_job_data_has_deterministic_empty_arrays_and_version():
    doc,_=example(); data=job_data(doc)
    assert data["schema"] == "murphywindow.job-data" and data["version"] == INTERCHANGE_VERSION
    assert isinstance(data["contacts"], list) and isinstance(data["bid_tabulation"], list)
