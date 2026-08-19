from copy import deepcopy
from decimal import Decimal as D

import pytest

from app.schema import default_configuration, new_project
from app.services import (
    DomainError, activate, calculate_project, create_change_order, job_data,
    provisional_closeout, redact, reestimate_contract, save_sov, submit, update_change_order_status,
)


def example():
    cfg = default_configuration()
    cfg["tax_rates"][0]["rate"] = ".10"
    cfg["markup_defaults"]["base_product"]["rate"] = ".20"
    cfg["markup_defaults"]["LAF"]["rate"] = ".30"
    cfg["markup_defaults"]["LAS"]["rate"] = ".40"
    cfg["pco"]["markup_one"] = ".10"; cfg["pco"]["markup_two"] = ".20"
    doc = new_project("Service Test", "Est", "Estimator")
    doc["cost_codes"] = [{"id":"ccd_1","code":"08 40 00","description":"Entrances","deduct":False},{"id":"ccd_2","code":"07 90 00","description":"Sealants","deduct":True}]
    doc["quotes"] = [
        {"id":"quo_base","group_id":"g1","code":"08 40 00","price":"1000","surcharge_percent":".10","tax_included":False,"used":True},
        {"id":"quo_alt","group_id":"g2","code":"ALT1-08 40 00","price":"500","surcharge_percent":"0","tax_included":True,"used":True},
    ]
    doc["takeoff_sections"] = [{"id":"sec_1","definition_id":"frame-v1","code":"08 40 00","name":"Frames","lines":[{"id":"frm_1","quantity":1,"width_inches":12,"height_inches":12,"caulking_passes":3}],"material_overrides":{},"tie_back_qty":0,"backpan_lf":0}]
    doc["labor_estimates"] = [{"id":"lbr_1","category":"field","code":"08 40 00","description":"Install","quantity":100,"crew":2,"productivity":5,"rate":50}]
    return doc, cfg


def test_bid_assembly_tax_markups_lineage_and_alternates():
    doc, cfg = example()
    calculate_project(doc, cfg)
    quote = next(x for x in doc["working_estimate"]["lines"] if x["category"] == "base_product")
    assert quote["direct_cost"] == "1210.00"  # quote cost 1100 plus 10% tax
    assert quote["selling_value"] == "1452.00"
    labor = next(x for x in doc["working_estimate"]["lines"] if x["category"] == "field_labor")
    assert labor["direct_cost"] == "500.00"
    assert labor["selling_value"] == "650.00"
    assert quote["lineage"][0]["source_id"] == "quo_base"
    disabled = next(x for x in doc["working_estimate"]["lines"] if x["code"].startswith("ALT1"))
    assert disabled["included"] is False
    total_without_alt = doc["working_estimate"]["totals"]["selling_value"]
    doc["working_estimate"]["alternate_inclusion"]["ALT1"] = True
    calculate_project(doc, cfg)
    alt = next(x for x in doc["working_estimate"]["lines"] if x["code"].startswith("ALT1"))
    assert alt["included"] is True
    assert alt["direct_cost"] == "500.00"  # tax already included
    assert D(doc["working_estimate"]["totals"]["selling_value"]) > D(total_without_alt)


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
    assert results["mat_bracing"]["source_quantity"] == "4"
    assert results["mat_sealant"]["source_quantity"] == "12"
    assert results["mat_membrane"]["source_quantity"] == "0"
    assert results["mat_sealant"]["pre_tax_cost"] == "11.52"
    assert section["pre_tax_material_cost"] == "17.52"
    assert section["pre_tax_material_cost_per_sf"] == "8.76"


def test_missing_frame_material_selection_means_all_materials_selected():
    doc, cfg = example()
    calculate_project(doc, cfg)
    results = {row["material_rule_id"]: row for row in doc["takeoff_sections"][0]["material_results"]}
    assert results["mat_bracing"]["source_quantity"] == "4"
    assert results["mat_sealant"]["source_quantity"] == "12"


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


def test_submit_permission_and_multiple_used_quote_validation():
    doc, cfg = example(); calculate_project(doc, cfg)
    with pytest.raises(DomainError):
        submit(doc, cfg, "PM", "Project Manager", {})
    doc["quotes"].append({"id":"quo_x","group_id":"g1","code":"08 40 00","price":2,"used":True})
    with pytest.raises(DomainError, match="validation failed"):
        submit(doc, cfg, "Est", "Estimator", {})


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
    assert result["current_estimated_cost"] == "999.00"
    assert result["reestimate_history"][0]["reason"] == "Supplier update"
    assert doc["project"]["bid_version"]["display"] == "B1.0.1"
    with pytest.raises(DomainError): reestimate_contract(doc,"Support","Support",{"allocation_id":line["id"],"new_cost":1,"reason":"x"})


def test_pco_sequential_hidden_redaction_and_authorization():
    doc,cfg=activated()
    order=create_change_order(doc,cfg,"PM","Project Manager",{"identifier":"PCO-1","cost_lines":[{"description":"Change","cost":"100","taxable":False}]})
    assert order["customer_price"] == "132.00"
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
    assert data["schema"] == "murphywindow.job-data" and data["version"] == "1.0.0"
    assert isinstance(data["contacts"], list) and isinstance(data["bid_tabulation"], list)
