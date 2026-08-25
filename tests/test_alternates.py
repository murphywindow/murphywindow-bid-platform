from copy import deepcopy
from decimal import Decimal

from app.alternates import (
    add_record, materialize, new_alternate, remove_record, reset_override,
    scope_of_change, set_override,
)
from app.proposals import compare_snapshots, create_proposal_snapshot
from app.schema import default_configuration, new_project
from app.services import calculate_project, edit_bid_source


def alternate_project():
    configuration = default_configuration()
    document = new_project("Alternate Test", "Estimator", "Estimator")
    document["project"].update({
        "project_type": "New Construction - Exterior Storefront", "project_type_status": "current",
        "contract_type": "Bid to CM/GC", "contract_type_status": "current",
        "wage_type": "Non-PW", "wage_type_status": "current",
    })
    document["cost_codes"] = [{"id": "ccd_storefront", "code": "08 40 00", "description": "Storefront", "deduct": False}]
    document["takeoff_sections"] = [{
        "id": "sec_storefront", "definition_id": "frame-v1", "code": "08 40 00", "name": "Storefront Frames",
        "lines": [{"id": "frm_f1", "mark": "F1", "quantity": 10, "width_inches": 60,
                   "height_inches": 96, "caulking_passes": 2}],
        "material_overrides": {}, "tie_back_qty": 0, "backpan_lf": 0,
    }]
    document["equipment"] = [{"id": "eqp_lift", "code": "08 40 00", "description": "Boom Lift",
                               "quantity": 1, "duration": 2, "rate": 500, "delivery": 100, "taxable": False}]
    document["labor_estimates"] = [{
        "id": "lbr_field", "code": "08 40 00", "description": "Field Labor", "labor_type": "Field",
        "man_hours": "80", "man_hours_source": "manual", "crew_size": "2", "hours_per_worker_per_day": "8",
        "workdays_per_week": "5", "controlled_rate_snapshot": {"rate": "68.53", "rate_id": "test",
        "configuration_id": configuration["id"], "status": "owner_provided"}, "rate_override": None,
        "origin": "manual", "source_links": [], "source_status": "unclassified",
    }]
    calculate_project(document, configuration)
    return document, configuration


def test_inheritance_override_conflict_and_reset_to_current_base():
    document, _ = alternate_project()
    alternate = new_alternate(document, "Reduced frame count")
    set_override(alternate, "frames", "frm_f1", "quantity", 10, 6)

    document["takeoff_sections"][0]["lines"][0]["width_inches"] = 66
    effective, conflicts = materialize(document, alternate)
    frame = effective["takeoff_sections"][0]["lines"][0]
    assert frame["width_inches"] == 66  # unrelated Base correction flows through
    assert frame["quantity"] == 6
    assert conflicts == []

    document["takeoff_sections"][0]["lines"][0]["quantity"] = 12
    effective, conflicts = materialize(document, alternate)
    assert effective["takeoff_sections"][0]["lines"][0]["quantity"] == 6
    assert conflicts == [{
        "collection": "frames", "record_id": "frm_f1", "field": "quantity",
        "original_base": 10, "current_base": 12, "alternate_override": 6,
        "reason": "base_changed_since_override",
    }]

    reset_override(alternate, "frames", "frm_f1", "quantity")
    effective, conflicts = materialize(document, alternate)
    assert effective["takeoff_sections"][0]["lines"][0]["quantity"] == 12
    assert conflicts == []


def test_added_removed_modified_records_and_deterministic_scope_of_change():
    document, _ = alternate_project()
    alternate = new_alternate(document, "VE Storefront")
    set_override(alternate, "frames", "frm_f1", "quantity", 10, 6)
    set_override(alternate, "frames", "frm_f1", "caulking_passes", 2, 3)
    set_override(alternate, "labor_estimates", "lbr_field", "man_hours", "80", "56")
    remove_record(alternate, "equipment", "eqp_lift")
    add_record(alternate, "frames", {"id": "frm_f8", "section_id": "sec_storefront", "mark": "F8",
                                      "quantity": 3, "width_inches": 48, "height_inches": 96, "caulking_passes": 2})

    effective, _ = materialize(document, alternate)
    assert not effective["equipment"]
    assert {row["id"] for row in effective["takeoff_sections"][0]["lines"]} == {"frm_f1", "frm_f8"}
    grouped = {group["area"]: group["changes"] for group in scope_of_change(document, alternate)}
    assert grouped["Frame Takeoff"] == [
        "Added F8 frames (Qty 3)", "F1 quantity reduced from 10 to 6", "F1 caulking passes changed from 2 to 3",
    ]
    assert grouped["Equipment"] == ["Removed Boom Lift"]
    assert grouped["Labor"] == ["Field Labor reduced by 24 man-hours"]
    assert all("[object Object]" not in text for values in grouped.values() for text in values)


def test_effective_commercial_delta_reconciles_and_downstream_materials_recalculate():
    document, configuration = alternate_project()
    document["takeoff_sections"][0]["additional_materials"] = [{
        "id": "matp_alt", "name": "Custom perimeter trim", "source": "perimeter_lf",
        "factor": "1", "unit": "LF", "cost_code": "08 40 00",
    }]
    document["takeoff_sections"][0]["material_overrides"]["matp_alt"] = {"rate_override": "2"}
    calculate_project(document, configuration)
    alternate = new_alternate(document, "Wider F1")
    set_override(alternate, "frames", "frm_f1", "width_inches", 60, 66)
    effective, _ = materialize(document, alternate)
    assert effective["takeoff_sections"][0]["additional_materials"][0]["id"] == "matp_alt"
    document["alternates"] = [alternate]
    base_total = Decimal(document["working_estimate"]["totals"]["selling_value"])

    calculate_project(document, configuration)
    calculated = alternate["calculated"]
    assert calculated["classification"] == "add"
    assert Decimal(calculated["direct_cost_delta"]) > 0
    assert Decimal(calculated["selling_value_delta"]) > 0
    assert Decimal(calculated["effective_totals"]["selling_value"]) - base_total == Decimal(calculated["selling_value_delta"])
    assert sum(Decimal(row["direct_cost_delta"]) for row in calculated["cost_code_impacts"]) == Decimal(calculated["direct_cost_delta"])
    assert sum(Decimal(row["selling_value_delta"]) for row in calculated["cost_code_impacts"]) == Decimal(calculated["selling_value_delta"])
    assert sum(Decimal(row["selling_value_delta"]) for row in calculated["comparison_impacts"]) == Decimal(calculated["selling_value_delta"])
    assert calculated["comparison_impacts"][0]["collection"] == "frames"
    assert calculated["comparison_impacts"][0]["record_id"] == "frm_f1"
    assert any(row["category"] == "installation_material" for row in calculated["cost_code_impacts"])
    effective = calculated["effective_estimate"]
    assert effective["totals"] == calculated["effective_totals"]
    assert effective["cost_code_summaries"]
    assert {component["name"] for component in effective["cost_code_summaries"][0]["components"]} >= {
        "Installation Materials", "LAF",
    }
    assert calculated["effective_equipment"][0]["id"] == "eqp_lift"
    assert calculated["effective_equipment"][0]["calculated_cost"] == "1100"
    assert calculated["effective_labor_estimates"][0]["id"] == "lbr_field"
    assert calculated["effective_labor_estimates"][0]["calculated_cost"] is not None
    assert calculated["effective_borrowed_lites"] == []
    assert "alternate_results" not in effective
    first = deepcopy(calculated)
    calculate_project(document, configuration)
    assert alternate["calculated"] == first  # no volatile values may alter proposal fingerprints


def test_record_comparison_impacts_are_stable_and_sum_to_the_authoritative_alternate_total():
    document, configuration = alternate_project()
    alternate = new_alternate(document, "Mixed scope")
    set_override(alternate, "frames", "frm_f1", "quantity", 10, 6)
    set_override(alternate, "labor_estimates", "lbr_field", "man_hours", "80", "56")
    remove_record(alternate, "equipment", "eqp_lift")
    document["alternates"] = [alternate]

    calculate_project(document, configuration)
    impacts = alternate["calculated"]["comparison_impacts"]

    assert [(row["collection"], row["record_id"]) for row in impacts] == [
        ("frames", "frm_f1"), ("equipment", "eqp_lift"), ("labor_estimates", "lbr_field"),
    ]
    assert sum(Decimal(row["selling_value_delta"]) for row in impacts) == Decimal(
        alternate["calculated"]["selling_value_delta"]
    )


def test_effective_frame_projection_preserves_section_structure_and_section_deltas():
    document, configuration = alternate_project()
    document["takeoff_sections"].append({
        "id": "sec_curtainwall", "definition_id": "frame-v1", "code": "08 40 00",
        "name": "Curtainwall", "lines": [{
            "id": "frm_c1", "mark": "C1", "quantity": "2", "width_inches": "48",
            "height_inches": "120", "caulking_passes": "3",
        }], "material_overrides": {}, "additional_materials": [], "tie_back_qty": 0, "backpan_lf": 0,
    })
    calculate_project(document, configuration)
    base_before = deepcopy(document["takeoff_sections"])
    alternate = new_alternate(document, "Structured frame scenario")
    set_override(alternate, "frames", "frm_f1", "width_inches", 60, "66.25")
    set_override(alternate, "takeoff_sections", "sec_storefront", "material_overrides.mat_sealant.factor_override", None, ".137")
    set_override(alternate, "takeoff_sections", "sec_storefront", "material_overrides.mat_sealant.source_override", None, "square_feet")
    set_override(alternate, "takeoff_sections", "sec_storefront", "material_overrides.mat_sealant.operator_override", None, "divide")
    set_override(alternate, "takeoff_sections", "sec_storefront", "material_overrides.mat_sealant.operand_override", None, "2")
    remove_record(alternate, "takeoff_sections", "sec_curtainwall")
    add_record(alternate, "takeoff_sections", {
        "id": "sec_alt_only", "definition_id": "frame-v1", "code": "08 40 00",
        "name": "ALT-only frames", "lines": [], "material_overrides": {},
        "additional_materials": [], "tie_back_qty": 0, "backpan_lf": 0,
    })
    add_record(alternate, "frames", {
        "id": "frm_alt_only", "section_id": "sec_alt_only", "mark": "A1", "quantity": "1.5",
        "width_inches": "42.75", "height_inches": "120.5", "caulking_passes": "3.11",
    })
    document["alternates"] = [alternate]

    calculate_project(document, configuration)

    projected = alternate["calculated"]["effective_takeoff_sections"]
    assert [section["id"] for section in projected] == ["sec_storefront", "sec_alt_only"]
    inherited = projected[0]
    assert Decimal(inherited["lines"][0]["width_inches"]) == Decimal("66.25")
    assert Decimal(inherited["material_overrides"]["mat_sealant"]["factor_override"]) == Decimal(".137")
    formula = next(row for row in inherited["material_results"] if row["material_rule_id"] == "mat_sealant")
    assert formula["source"] == "square_feet" and formula["operator"] == "divide"
    assert Decimal(formula["operand"]) == Decimal("2")
    added = projected[1]
    assert added["lines"][0]["id"] == "frm_alt_only"
    assert Decimal(added["lines"][0]["calculated"]["caulking_lf"]) != Decimal(
        added["lines"][0]["calculated"]["caulking_lf"]
    ).to_integral_value()
    assert document["takeoff_sections"] == base_before

    alternate["changes"]["takeoff_sections"]["removed"].remove("sec_curtainwall")
    calculate_project(document, configuration)
    assert [section["id"] for section in alternate["calculated"]["effective_takeoff_sections"]] == [
        "sec_storefront", "sec_curtainwall", "sec_alt_only",
    ]


def test_mixed_content_uses_net_commercial_direction_without_manual_add_deduct_flag():
    document, configuration = alternate_project()
    alternate = new_alternate(document, "Mixed VE")
    remove_record(alternate, "equipment", "eqp_lift")
    add_record(alternate, "equipment", {"id": "eqp_small", "code": "08 40 00", "description": "Small Lift",
                                         "quantity": 1, "duration": 1, "rate": 100, "delivery": 0, "taxable": False})
    document["alternates"] = [alternate]
    calculate_project(document, configuration)
    assert alternate["calculated"]["classification"] == "deduct"
    assert Decimal(alternate["calculated"]["selling_value_delta"]) < 0
    assert "classification" not in {key for key in alternate if key != "calculated"}


def test_alternate_quote_selection_is_explicit_and_does_not_change_base_selection():
    document, configuration = alternate_project()
    document["quotes"] = [{"id": "quo_base", "code": "08 40 00", "vendor": "Base Glass", "price": "1000",
                           "credit_type": "dollar", "credit_value": 0, "surcharge_type": "dollar", "surcharge_value": 0,
                           "tax_included": True, "used": True}]
    document["working_estimate"]["quote_selection_by_code"] = {
        "08 40 00": {"mode": "manual", "selected_quote_ids": ["quo_base"]},
    }
    calculate_project(document, configuration)
    alternate = new_alternate(document, "Supplier substitution")
    set_override(alternate, "quotes", "quo_base", "used", True, False)
    add_record(alternate, "quotes", {"id": "quo_alt", "code": "08 40 00", "vendor": "Alternate Glass", "price": "800",
                                      "credit_type": "dollar", "credit_value": 0, "surcharge_type": "dollar", "surcharge_value": 0,
                                      "tax_included": True, "used": True})
    document["alternates"] = [alternate]
    calculate_project(document, configuration)

    assert document["working_estimate"]["quote_selection_by_code"]["08 40 00"]["selected_quote_ids"] == ["quo_base"]
    assert alternate["calculated"]["classification"] == "deduct"
    effective, _ = materialize(document, alternate)
    calculate_project(effective, configuration, include_alternates=False)
    assert [row["id"] for row in effective["quotes"] if row["used"]] == ["quo_alt"]


def test_proposal_snapshot_freezes_alternate_state_and_comparison_is_business_aware():
    document, configuration = alternate_project()
    alternate = new_alternate(document, "Frame Quantity")
    alternate["customer_description"] = "Reduce the west elevation frame count."
    set_override(alternate, "frames", "frm_f1", "quantity", 10, 6)
    document["alternates"] = [alternate]
    calculate_project(document, configuration)
    first = create_proposal_snapshot(document, configuration, "Estimator", "Estimator", "Original")
    frozen = deepcopy(first["state"]["alternates"])

    set_override(document["alternates"][0], "frames", "frm_f1", "quantity", 10, 4)
    calculate_project(document, configuration)
    second = create_proposal_snapshot(document, configuration, "Estimator", "Estimator", "Revision 1")
    comparison = compare_snapshots(first, second)

    assert first["state"]["alternates"] == frozen
    alternate_changes = comparison["alternates"]["changes"]
    assert alternate_changes[0]["status"] == "changed"
    assert "F1 quantity reduced from 10 to 4" in alternate_changes[0]["scope_added"]
    assert "[object Object]" not in str(comparison)


def test_base_and_alternate_line_markup_override_inheritance_and_clearing():
    document, configuration = alternate_project()
    alternate = new_alternate(document)
    document["alternates"] = [alternate]
    calculate_project(document, configuration)

    edit_bid_source(document, configuration, "Estimator", "Estimator", {
        "confirmed": True, "source_type": "equipment", "source_id": "eqp_lift",
        "changes": {"markup_percent": ".31"}, "reason": "Base line authority",
    })
    inherited = next(row for row in alternate["calculated"]["effective_estimate"]["lines"]
                     if row.get("source_key") == "equipment:eqp_lift")
    assert inherited["markup_override_mode"] == "percentage"
    assert Decimal(inherited["markup_override_value"]) == Decimal(".31")

    edit_bid_source(document, configuration, "Estimator", "Estimator", {
        "confirmed": True, "source_type": "equipment", "source_id": "eqp_lift",
        "alternate_id": alternate["id"], "changes": {"markup_amount": "80"},
        "reason": "Alternate line authority",
    })
    explicit = next(row for row in alternate["calculated"]["effective_estimate"]["lines"]
                    if row.get("source_key") == "equipment:eqp_lift")
    assert explicit["markup_override_mode"] == "amount"
    assert explicit["markup_value"] == "80"

    edit_bid_source(document, configuration, "Estimator", "Estimator", {
        "confirmed": True, "source_type": "equipment", "source_id": "eqp_lift",
        "changes": {"markup_percent": ""}, "reason": "Clear Base authority",
    })
    still_explicit = next(row for row in alternate["calculated"]["effective_estimate"]["lines"]
                          if row.get("source_key") == "equipment:eqp_lift")
    assert still_explicit["markup_override_mode"] == "amount"
    assert still_explicit["markup_value"] == "80"

    edit_bid_source(document, configuration, "Estimator", "Estimator", {
        "confirmed": True, "source_type": "equipment", "source_id": "eqp_lift",
        "alternate_id": alternate["id"], "changes": {"markup_amount": ""},
        "reason": "Return Alternate to current Base inheritance",
    })
    reset = next(row for row in alternate["calculated"]["effective_estimate"]["lines"]
                 if row.get("source_key") == "equipment:eqp_lift")
    assert reset["markup_override_mode"] is None
    assert reset["markup_rate"] == configuration["markup_defaults"]["base_product"]["rate"]
