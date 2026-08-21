"""Versioned JSON document factories and application defaults."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from .rate_reference import owner_rate_reference
from .numeric_precision import default_decimal_precision

SCHEMA_VERSION = "1.3.0"
INTERCHANGE_VERSION = "1.3.0"
CONFIG_VERSION = "cfg-2026-08-19-v5"

PROJECT_TYPES = (
    "New Construction - Curtainwall",
    "New Construction - Exterior Storefront",
    "New Construction - Interior Storefront",
    "New Construction - Windows",
    "Addition/Renovation - Curtainwall",
    "Addition/Renovation - Exterior Storefront",
    "Addition/Renovation - Interior Storefront",
    "Addition/Renovation - Windows",
    "Repair - Curtainwall",
    "Repair - Exterior Storefront",
    "Repair - Interior Storefront",
    "Repair - Windows",
    "Replacement - Curtainwall",
    "Replacement - Exterior Storefront",
    "Replacement - Interior Storefront",
    "Replacement - Windows",
)
CONTRACT_TYPES = ("Bid to CM/GC", "Bid as GC")
WAGE_TYPES = ("Non-PW", "PW")
LABOR_TYPES = ("Field", "Shop", "Design")
CONTACT_ROLES = ("Owner", "Architect", "Vendor", "Engineer", "GC", "CM")


def now() -> str:
    return datetime.now(UTC).isoformat()


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def default_configuration() -> dict:
    """Seeded from INF-4320; unsupported commercial numbers remain zero/disabled."""
    rates = owner_rate_reference()
    material_rules = [
        ("mat_bracing", "Bracing and Anchoring", "06 00 00", "perimeter_lf", "1", "1.50", "linear foot", "Anchoring"),
        ("mat_membrane", "Sheet Metal Membrane Air Barriers", "07 25 00", "perimeter_lf", "1.00", "1.00", "linear foot", "Membrane"),
        ("mat_flashing", "Flashing and Sheet Metal", "07 60 00", "head_sill_qty", "1.00", "8.00", "linear foot", "Flashing"),
        ("mat_backer", "Backer Rods", "07 90 00", "caulking_lf", "1.00", "0.50", "linear foot", "Sealants"),
        ("mat_sealant", "Joint Sealants", "07 90 00", "caulking_lf", "0.08", "12.00", "sausage", "Sealants"),
        ("mat_tieback", "Tie Back", "06 00 00", "tie_back_qty", "1", "45.00", "each", "Anchoring"),
        ("mat_backpan", "Backpans / Insulation", "07 60 00", "backpan_lf", "1", "48.32", "linear foot", "Flashing"),
    ]
    reference_path = Path(__file__).resolve().parents[1] / "data" / "reference" / "codes.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8")) if reference_path.exists() else {"records": [], "reference_id": None, "source": None}
    return {
        "schema_version": SCHEMA_VERSION,
        "id": CONFIG_VERSION,
        "version": 5,
        "effective_date": "2026-08-19",
        "status": "active",
        "created_at": now(),
        "source": "INF-4320 v2.1.0 + owner-provided codes.xlsx + owner-provided rate tables received 2026-08-17",
        "cost_code_reference": {"reference_id": reference.get("reference_id"), "source": reference.get("source"), "record_count": len(reference.get("records", [])), "status": "owner_confirmed_reference"},
        "rate_reference": {"reference_id": rates["reference_id"], "received_date": rates["received_date"], "source": rates["source"], "status": rates["status"]},
        "rule_status_legend": {
            "verified": "Observed directly in the workbook/formulas.",
            "confirmed": "Confirmed by the business owner.",
            "pending": "Not resolved; safe default is configurable and not policy."
        },
        "tax_rates": [{"id": "tax_default", "name": "Unconfigured local tax", "rate": "0", "status": "pending", "note": "Select and verify the correct project jurisdiction."}, *rates["tax_rates"]],
        "markup_defaults": {"base_product": {"rate": "0", "status": "pending"}, "installation_material": {"rate": None, "inherits": "base_product", "status": "pending_distinct_rate"}, "LAF": {"rate": "0", "status": "pending"}, "LAS": {"rate": "0", "status": "pending"}},
        "contingency": {"enabled_default": False, "rate": "0.01", "minimum": "3000", "formula_status": "confirmed", "enablement_status": "pending"},
        "bond": {
            "enabled_default": False,
            "status": "pending",
            "note": "Six-band method is confirmed, but INF-4320 does not publish thresholds or rates. Configure before enabling.",
            "bands": [{"id": f"band_{i}", "min_exclusive": str(i - 1), "max_inclusive": str(i) if i < 6 else None, "rate": "0"} for i in range(1, 7)]
        },
        "pco": {"markup_one": "0", "markup_two": "0", "status": "pending", "restricted_roles": ["General Manager", "President", "Project Manager", "Systems Administrator"]},
        "fringe_credit_rate": {"value": "0.1425", "status": "confirmed"},
        "labor_parameters": {"burden_1_038": {"value": "1.038", "status": "pending"}, "blend_52_percent": {"value": "0.52", "status": "pending"}, "blend_50_percent": {"value": "0.50", "status": "pending"}},
        "material_rules": [{"id": a, "name": b, "material_code": c, "source": d, "factor": e, "rate": f, "unit": g, "keyword": h, "taxable": True, "status": "verified"} for a, b, c, d, e, f, g, h in material_rules],
        "hardware_groups": [{"id": f"HW{i}", "name": f"Hardware Group {i}", "price": "1500" if i == 1 else ("3000" if i == 2 else "5000"), "status": "verified"} for i in range(1, 11)],
        "equipment_rates": rates["equipment_rates"], "labor_rates": [*rates["labor_rates"], {"id": "labor_design_unavailable", "description": "Design Labor Cost / Rate", "category": "design", "base_rate": None, "rate_basis": "hour", "effective_date": None, "source": "No controlled owner rate supplied", "status": "unavailable_requires_configuration"}], "labor_burden_records": rates["labor_burden_records"],
        "overhead_cost_factors": rates["overhead_cost_factors"], "wage_records": rates["wage_records"], "material_rates": rates["material_rates"],
        "csi_references": reference.get("records", []), "cost_code_mappings": [],
        "schedule_definitions": [
            {"id": "frame-v1", "type": "frame", "version": 1, "status": "verified"},
            {"id": "door-v1", "type": "door", "version": 1, "status": "verified"},
            {"id": "equipment-v1", "type": "equipment", "version": 1, "status": "verified"},
            {"id": "borrowed-lite-v1", "type": "borrowed_lite", "version": 1, "status": "verified"},
        ],
        "pending_rules": [
            "Remaining required fields, file naming/reuse, and submission evidence", "Large-bid threshold and review evidence", "Activation reversal/correction authority",
            "Contract re-estimate control total and approval", "Bond and contingency enable/override authority", "PCO markup rates and change authority",
            "Rate update cadence and effective-date policy", "Travel, per diem, excluded-day, lodging, and tax-exemption rules",
            "SOV operating approval roles", "Closeout gates, approval, archive, and retention"
        ],
        "application_settings": {"autosave_seconds": 0, "autosave_debounce_ms": 250, "autosave_status": "confirmed_user_request", "backup_retention": 20, "default_port": 8765, "large_bid_threshold": None, "large_bid_threshold_status": "pending", "retention_days": None, "retention_status": "pending", "decimal_precision": default_decimal_precision(),
                                 "mileage": {"origin_label": "Rogers, Minnesota 55374 city center", "origin_latitude": "45.1888596", "origin_longitude": "-93.5524563", "origin_status": "owner_requested_city_origin_configurable", "geocoder_primary": "US Census Geocoder Public_AR_Current", "geocoder_fallback": "OpenStreetMap Nominatim public service", "router": "OSRM public routing service", "online_required": True, "rounding": "nearest 0.1 mile, ROUND_HALF_UP"}}
    }


def new_project(name: str, actor: str, role: str, configuration_id: str = CONFIG_VERSION) -> dict:
    ts, project_id = now(), uid("prj")
    return {
        "schema_version": SCHEMA_VERSION,
        "interchange_version": INTERCHANGE_VERSION,
        "project": {
            "id": project_id, "revision": 0, "name": name, "abbreviation": "", "project_number": "", "mwd_po": "", "address": "",
            "address_street": "", "address_city": "", "address_state": "", "zip": "", "county": "", "address_match_metadata": None,
            "miles_from_rogers": None, "project_type": "", "project_type_status": "missing", "building_type": "", "estimator": actor if role == "Estimator" else "",
            "project_manager": "", "owner_name": "", "owner_organization_id": None, "owner_legal_name": "", "owner_address": "",
            "owner_website": "", "owner_phone": "", "owner_email": "", "architect": "", "engineer": "", "general_contractor": "",
            "construction_manager": "", "plan_source": "", "contract_type": "", "contract_type_status": "missing", "wage_type": "", "wage_type_status": "missing", "addenda_count": 0, "walkthrough": "", "frame_sealant_colors": "",
            "additional_information": "", "notes": "", "proposal_scope": "", "proposal_inclusions": "", "proposal_exclusions": "",
            "wage_data_id": None, "wage_selection_source": None, "wage_selected_at": None, "tax_exempt": False, "tax_rate_id": "tax_default",
            "tax_selection_source": None, "tax_selected_at": None, "bid_due_date": None, "start_date": None, "completion_date": None,
            "fabrication_due_date": None, "fabrication_start_date": None, "lifecycle_state": "estimate_created", "archived": False,
            "configuration_id": configuration_id, "bid_version": {"major": 0, "minor": 0, "patch": 0, "display": "B0.0.0", "sequence": 0, "last_event": "create", "recorded_at": ts},
            "created_at": ts, "updated_at": ts
        },
        "contacts": [], "cost_codes": [], "quotes": [], "takeoff_sections": [], "doors": [], "hardware_assignments": [], "equipment": [],
        "borrowed_lites": [], "labor_estimates": [], "travel_estimates": [], "working_estimate": {
            "id": uid("wrk"),
            "markup_overrides": {}, "contingency_enabled": False, "contingency_override": None, "contingency_override_reason": "",
            "bond_enabled": False, "bond_override": None, "bond_override_reason": "", "borrowed_lite_source_by_code": {},
            "quote_selection_by_code": {}, "labor_suggestion_exclusions": [], "component_markup_overrides": {}, "pending_controlled_values": [],
            "lines": [], "code_summaries": [], "cost_code_summaries": [], "category_subtotals": {}, "totals": {}
        },
        "estimate_revisions": [], "alternates": [], "reviews": [], "submissions": [], "proposal_artifacts": [],
        "proposal_history": [], "working_branch": None, "bid_tabulations": [], "award": None,
        "contract_allocations": [], "change_orders": [], "sov_lines": [], "closeout": None,
        "configuration_lineage": [{"configuration_id": configuration_id, "adopted_at": ts, "actor": actor}],
        "audit_events": [{"id": uid("aud"), "timestamp": ts, "actor": actor, "role": role, "entity_type": "project", "entity_id": project_id,
                          "operation": "create", "prior_value": None, "new_value": {"name": name}, "reason": "New project", "correlation_id": uid("cor")}]
    }


def duplicate_project(source: dict, name: str, actor: str, role: str) -> dict:
    result = deepcopy(source)
    ts, old_id, new_id = now(), source["project"]["id"], uid("prj")
    result["project"].update({"id": new_id, "revision": 0, "name": name, "lifecycle_state": "estimate_created", "archived": False,
                              "bid_version": {"major": 0, "minor": 0, "patch": 0, "display": "B0.0.0", "sequence": 0, "last_event": "duplicate", "recorded_at": ts},
                              "created_at": ts, "updated_at": ts})
    result["estimate_revisions"] = []
    result["reviews"] = []
    result["submissions"] = []
    result["proposal_artifacts"] = []
    result["proposal_history"] = []
    result["working_branch"] = None
    result["award"] = None
    result["contract_allocations"] = []
    result["change_orders"] = []
    result["sov_lines"] = []
    result["closeout"] = None
    result["audit_events"] = [{"id": uid("aud"), "timestamp": ts, "actor": actor, "role": role, "entity_type": "project", "entity_id": new_id,
                               "operation": "duplicate", "prior_value": {"source_project_id": old_id}, "new_value": {"name": name}, "reason": "Duplicate Project", "correlation_id": uid("cor")}]
    return result


def test_project(actor: str = "Test Estimator") -> dict:
    """Reusable local sandbox. Startup creates it once and never overwrites edits."""
    doc = new_project("MW Bid Platform Test Project", actor, "Estimator")
    doc["project"].update({
        "id": "prj_00000000000000000000000000004320", "project_number": "TEST-4320", "address": "Rogers, MN",
        "address_city": "Rogers", "address_state": "MN", "project_type": "New Construction - Exterior Storefront", "project_type_status": "current", "building_type": "Commercial",
        "contract_type": "Bid to CM/GC", "contract_type_status": "current", "wage_type": "Non-PW", "wage_type_status": "current", "bid_due_date": "2026-09-01T14:00",
        "proposal_scope": "Test storefront and frame scope for learning the local bid workflow.",
        "proposal_exclusions": "Training data only. This is not a customer offer.", "notes": "Reusable sandbox seeded by the application. Safe to edit, duplicate, submit, and activate for testing."
    })
    doc["audit_events"][0]["entity_id"] = doc["project"]["id"]
    doc["cost_codes"] = [
        {"id": "ccd_test_frames", "code": "08 40 00", "description": "Entrances, Storefronts, and Curtain Walls", "mwd_code": "0840", "mwd_description": "Aluminum Entrances", "deduct": False, "status": "active"},
        {"id": "ccd_test_sealants", "code": "07 90 00", "description": "Joint Sealants", "mwd_code": "0790", "mwd_description": "Sealants", "deduct": False, "status": "active"},
        {"id": "ccd_test_lifts", "code": "14 40 00", "description": "Lifts", "mwd_code": "", "mwd_description": "", "deduct": False, "status": "active"},
    ]
    doc["contacts"] = [{"id": "con_test_gc", "role": "General Contractor", "organization": "Test Construction", "name": "Taylor Example", "position": "Estimator", "email": "test@example.invalid", "phone": "555-0100", "active": True}]
    doc["quotes"] = [
        {"id": "quo_test_a", "group_id": "test-frames", "code": "08 40 00", "date": "2026-08-17", "vendor": "Example Glass A", "price": "12500", "surcharge_percent": "0.03", "tax_included": True, "used": True, "notes": "Selected training quote"},
        {"id": "quo_test_b", "group_id": "test-frames", "code": "08 40 00", "date": "2026-08-17", "vendor": "Example Glass B", "price": "13200", "surcharge_percent": "0", "tax_included": False, "used": False, "notes": "Comparison training quote"}
    ]
    doc["takeoff_sections"] = [{
        "id": "sec_test_main", "definition_id": "frame-v1", "name": "Main Entry Frames", "code": "08 40 00", "material_overrides": {}, "tie_back_qty": 2, "backpan_lf": 12,
        "lines": [
            {"id": "frm_test_1", "mark": "F1", "quantity": 2, "width_inches": 48, "height_inches": 96, "caulking_passes": 3, "head": "Standard", "jamb": "Standard", "sill": "Standard", "type": "Storefront", "material": "Aluminum", "finish": "Clear anodized", "notes": "Main entry"},
            {"id": "frm_test_2", "mark": "F2", "quantity": 1, "width_inches": 36, "height_inches": 84, "caulking_passes": 3, "head": "Standard", "jamb": "Standard", "sill": "Standard", "type": "Door frame", "material": "Aluminum", "finish": "Dark bronze", "notes": "Side entry"}
        ]
    }]
    doc["equipment"] = [{"id": "eqp_test_lift", "code": "14 40 00", "description": "45’ Boom Lift", "quantity": 1, "duration": 1, "duration_unit": "month", "rate": "1750", "delivery": "200", "taxable": True, "rate_id": "equipment_owner_08", "rate_version": CONFIG_VERSION, "notes": "Owner-provided rental reference; verify stale vendor rate before commercial use."}]
    doc["borrowed_lites"] = [{"id": "brl_test_1", "code": "08 40 00", "mark": "BL1", "quantity": 1, "width_inches": 12, "height_inches": 12, "rate": "25", "notes": "Exercises five ft² minimum"}]
    doc["labor_estimates"] = [
        {"id": "lbr_test_field", "category": "field", "code": "08 40 00", "description": "Field installation", "quantity": 160, "quantity_unit": "SF", "crew": 2, "productivity": 4, "rate": "68.53", "rate_id": "labor_field_nonpw_2025", "rate_version": CONFIG_VERSION, "notes": "Owner-provided 2025 non-PW field rate"},
        {"id": "lbr_test_shop", "category": "shop", "code": "08 40 00", "description": "Shop preparation", "quantity": 40, "quantity_unit": "units", "crew": 1, "productivity": 5, "rate": "38.85", "rate_id": "labor_shop_2025", "rate_version": CONFIG_VERSION, "notes": "Owner-provided 2025 shop rate"}
    ]
    doc["working_estimate"]["markup_overrides"] = {"base_product": "0.10", "LAF": "0.15", "LAS": "0.12"}
    doc["alternates"] = [{
        "id": "alt_test_1", "sequence": 1, "key": "ALT1", "name": "Value-engineered storefront quote",
        "customer_description": "Optional storefront supplier substitution.", "created_at": now(), "base_created_revision": 0,
        "changes": {"quotes": {"added": [{"id": "quo_test_alt", "group_id": "test-alt", "code": "08 40 00", "date": "2026-08-17", "vendor": "Example Glass A", "price": "11000", "surcharge_percent": "0", "tax_included": True, "used": True, "notes": "ALT-only quote"}], "removed": ["quo_test_a"], "overrides": {}}},
        "calculated": {},
    }]
    return doc
