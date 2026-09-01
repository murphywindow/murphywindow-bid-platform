"""Curated, seedable synthetic projects for local workflow testing."""
from __future__ import annotations

import hashlib
import random
import secrets
from datetime import date, timedelta
from decimal import Decimal

from .calculations import normalize_code
from .migrations import migrate_project_document
from .schema import CONFIG_VERSION, new_project, now, uid
from .services import audit

GENERATOR_VERSION = "1.2.0"


PROJECT_PROFILES = [
    {
        "kind": "Community recreation center",
        "project_type": "New Construction - Curtainwall",
        "names": ["Northstar Commons", "Riverbend Recreation Center", "Prairie Creek Community Center"],
        "building_type": "Municipal recreation and assembly",
        "contract_type": "Bid to CM/GC",
        "prevailing_wage": True,
        "scope": "Furnish and install aluminum storefront, curtain wall, entrances, doors, hardware, glazing, perimeter sealants, and associated installation materials.",
    },
    {
        "kind": "Medical office",
        "project_type": "New Construction - Exterior Storefront",
        "names": ["Cedar Health Pavilion", "Lakeview Specialty Clinic", "Meadowbrook Medical Offices"],
        "building_type": "Outpatient healthcare",
        "contract_type": "Bid to CM/GC",
        "prevailing_wage": False,
        "scope": "Furnish and install exterior aluminum framing, glazed entrances, interior borrowed lites, glazing, door hardware, sealants, and related installation materials.",
    },
    {
        "kind": "K-12 education addition",
        "project_type": "Addition/Renovation - Curtainwall",
        "names": ["Oak Ridge Learning Center", "Summit Ridge School Addition", "Maple Grove Academic Wing"],
        "building_type": "Education",
        "contract_type": "Bid to CM/GC",
        "prevailing_wage": True,
        "scope": "Furnish and install thermally improved storefront and curtain wall, aluminum entrances, glazing, hardware, borrowed lites, sealants, and installation accessories.",
    },
    {
        "kind": "Corporate office renovation",
        "project_type": "Addition/Renovation - Interior Storefront",
        "names": ["Granite Point Workplace", "Mill District Offices", "Pinnacle Operations Center"],
        "building_type": "Commercial office",
        "contract_type": "Bid to CM/GC",
        "prevailing_wage": False,
        "scope": "Furnish and install exterior and interior aluminum framing, entrances, glazing, borrowed lites, door hardware, perimeter sealants, and installation materials.",
    },
]

LOCATIONS = [
    ("Minneapolis", "MN", "55401", 4, "Hennepin"), ("Elk River", "MN", "55330", 18, "Sherburne"),
    ("Maple Grove", "MN", "55369", 15, "Hennepin"), ("Plymouth", "MN", "55446", 23, "Hennepin"),
    ("Brooklyn Park", "MN", "55443", 24, "Hennepin"), ("Minneapolis", "MN", "55401", 31, "Hennepin"),
    ("St. Paul", "MN", "55101", 43, "Ramsey"), ("Woodbury", "MN", "55125", 52, "Washington"),
    ("Mankato", "MN", "56001", 96, "Blue Earth"),
]

STREETS = ["Innovation Drive", "Civic Center Parkway", "Prairie Avenue", "Commerce Boulevard", "Lakeview Road", "Summit Lane"]
GENERAL_CONTRACTORS = ["Northland Builders", "Summit Construction Partners", "Ironwood Construction", "Prairie State Builders"]
ARCHITECTS = ["Studio North Architects", "Lake & Field Design", "CivicWorks Architecture", "Prairie Line Architects"]
ENGINEERS = ["Vector Building Engineering", "Northstar Structural", "Element Engineering Group"]
OWNERS = ["City Facilities Department", "Northstar Health Properties", "Independent School District 999", "Granite Point Properties"]
VENDORS = ["Midwest Architectural Metals", "Northland Glass Systems", "Prairie State Aluminum", "Metro Glazing Supply", "Lakes Area Glass"]
FINISHES = ["Clear anodized", "Dark bronze anodized", "Black fluoropolymer", "Medium bronze fluoropolymer"]
FRAME_TYPES = ["Storefront", "Curtain wall", "Ribbon window", "Entrance framing", "Interior glazed partition"]


def _seed_value(seed: int | str | None) -> int:
    if seed is None or seed == "":
        return secrets.randbits(32)
    if isinstance(seed, int):
        return seed
    text = str(seed).strip()
    try:
        return int(text)
    except ValueError:
        return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _reference(config: dict, code: str) -> dict:
    row = next((r for r in config.get("csi_references", []) if r.get("normalized_code") == normalize_code(code)), None)
    return row or {"id": None, "display_code": code, "description": code, "status": "pending"}


def _cost_code(config: dict, code: str, *, deduct: bool = False) -> dict:
    row = _reference(config, code)
    return {
        "id": uid("ccd"), "code": row.get("display_code") or code, "description": row.get("description") or code,
        "mwd_code": normalize_code(code), "mwd_description": row.get("description") or code,
        "deduct": deduct, "status": "active", "reference_id": row.get("id"),
        "reference_status": row.get("status", "pending"),
    }


def _quote(rng: random.Random, group: str, code: str, vendor: str, base_price: int, used: bool, note: str) -> dict:
    variation = Decimal(str(rng.uniform(0.93, 1.09))).quantize(Decimal("0.0001"))
    return {
        "id": uid("quo"), "group_id": group, "code": code, "date": "2026-08-12", "vendor": vendor,
        "price": str((Decimal(base_price) * variation).quantize(Decimal("1"))),
        "credit_type": "dollar", "credit_value": "0",
        "surcharge_type": "percentage", "surcharge_value": rng.choice(["0", "0.015", "0.025", "0.035"]),
        "surcharge_percent": "0", "square_feet": None, "square_feet_source": "unassigned",
        "tax_included": rng.choice([True, False]), "used": False,
        "notes": note + (" Automatic selection will choose the lowest final adjusted value." if used else ""),
    }


def _frame_line(rng: random.Random, section_index: int, line_index: int, frame_type: str, finish: str) -> dict:
    width = rng.choice([36, 42, 48, 60, 72, 84, 96, 120, 144])
    height = rng.choice([84, 96, 108, 120, 144])
    return {
        "id": uid("frm"), "mark": f"{chr(65 + section_index)}{line_index + 1}", "quantity": rng.randint(1, 6),
        "width_inches": width, "height_inches": height, "caulking_passes": rng.choice([2, 3, 3, 3, 4]),
        "head": rng.choice(["Standard", "Steel-reinforced", "Thermally broken"]),
        "jamb": rng.choice(["Standard", "Steel-reinforced", "Expansion jamb"]),
        "sill": rng.choice(["Standard", "High-performance", "Subsill"]),
        "type": frame_type, "material": "Extruded aluminum", "finish": finish,
        "notes": rng.choice(["Per architectural elevations", "Field verify opening", "Coordinate adjacent finish", "Typical condition"]),
        "missing_quantity_acknowledged": False,
    }


def generate_test_project(config: dict, actor: str, role: str, seed: int | str | None = None, *, project_id: str | None = None) -> dict:
    """Return a rich draft generated from curated pools, suitable only for testing."""
    seed_value = _seed_value(seed)
    rng = random.Random(seed_value)
    profile = rng.choice(PROJECT_PROFILES)
    city, state, zip_code, miles, county = rng.choice(LOCATIONS)
    project_name = f"{rng.choice(profile['names'])} — TEST {seed_value % 10000:04d}"
    doc = new_project(project_name, actor, role, config.get("id", CONFIG_VERSION), project_id=project_id)
    project_number = f"TEST-{seed_value % 100000:05d}"
    bid_due = date(2026, 9, 1) + timedelta(days=rng.randint(0, 150))
    start = bid_due + timedelta(days=rng.randint(45, 120))
    finish = start + timedelta(days=rng.randint(120, 320))
    owner = rng.choice(OWNERS)
    gc = rng.choice(GENERAL_CONTRACTORS)
    architect = rng.choice(ARCHITECTS)
    engineer = rng.choice(ENGINEERS)
    street_number = rng.randrange(100, 9900, 10)
    wage_record = next((row for row in config.get("wage_records", []) if row.get("county") == county), None)
    standard_rates = {row.get("id"): row for row in config.get("labor_rates", [])}
    field_standard = standard_rates.get("labor_field_nonpw_2025", {}).get("base_rate", "68.53")
    shop_standard = standard_rates.get("labor_shop_2025", {}).get("base_rate", "38.85")
    per_diem = standard_rates.get("per_diem_owner_2025", {}).get("base_rate", "120.00")
    use_prevailing = bool(profile.get("prevailing_wage")) and wage_record is not None
    field_rate = wage_record.get("estimated_company_rate") if use_prevailing else field_standard
    field_rate_id = wage_record.get("id") if use_prevailing else "labor_field_nonpw_2025"
    selected_tax = next((row for row in config.get("tax_rates", []) if row.get("id") == "tax_mn_sherburne_owner"), None) if county == "Sherburne" else None

    doc["project"].update({
        "project_number": project_number, "address": f"{street_number} {rng.choice(STREETS)}, {city}, {state}", "zip": zip_code,
        "miles_from_minneapolis": miles, "project_type": profile["project_type"], "building_type": profile["building_type"],
        "project_type_status": "current", "contract_type": profile["contract_type"], "contract_type_status": "current",
        "owner_name": owner, "owner_address": f"100 Civic Plaza, {city}, {state} {zip_code}",
        "architect": architect, "engineer": engineer, "general_contractor": gc,
        "construction_manager": gc if "manager" in profile["contract_type"].lower() else "",
        "plan_source": "Synthetic issued-for-bid drawing set", "addenda_count": rng.randint(0, 4),
        "walkthrough": f"{(bid_due - timedelta(days=7)).isoformat()}T10:00", "frame_sealant_colors": rng.choice(["Black", "Bronze", "Aluminum gray"]),
        "additional_information": "Synthetic testing project generated from curated estimating profiles. Validate all values before any real-world use.",
        "notes": "TRAINING / TEST DATA ONLY. Not a customer quotation and not suitable for commercial reliance.",
        "proposal_scope": profile["scope"],
        "proposal_inclusions": "Standard manufacturer warranties; shop drawings; normal delivery; installation materials; final perimeter sealants; one mobilization per phase.",
        "proposal_exclusions": "Testing artifact only. Excludes permits, engineering delegated by others, temporary heat, hazardous-material remediation, after-hours premiums, and unresolved travel policy.",
        "bid_due_date": f"{bid_due.isoformat()}T14:00", "start_date": start.isoformat(), "completion_date": finish.isoformat(), "final_completion_date": (finish + timedelta(days=30)).isoformat(),
        "fabrication_due_date": (start - timedelta(days=35)).isoformat(), "fabrication_start_date": (start - timedelta(days=70)).isoformat(),
        "prevailing_wage_required": use_prevailing,
        "wage_type": "PW" if use_prevailing else "Non-PW",
        "wage_type_status": "current",
        "wage_data_id": wage_record.get("id") if use_prevailing else None,
        "wage_selection_source": wage_record.get("source") if use_prevailing else "Non-PW profile",
        "wage_selected_at": now() if use_prevailing else None,
        "tax_rate_id": selected_tax.get("id") if selected_tax else "tax_default",
        "tax_selection_source": selected_tax.get("source") if selected_tax else "No jurisdiction-specific owner rate selected",
        "tax_selected_at": now(),
        "test_generation": {"seed": seed_value, "profile": profile["kind"], "generator_version": GENERATOR_VERSION,
                            "generated_at": now(), "purpose": "training_test_only", "curated": True,
                            "rate_reference_id": config.get("rate_reference", {}).get("reference_id"), "county": county,
                            "prevailing_wage_applied": use_prevailing, "field_rate_id": field_rate_id,
                            "shop_rate_id": "labor_shop_2025", "tax_rate_id": selected_tax.get("id") if selected_tax else "tax_default"},
    })

    people = [
        ("Owner", owner, "Morgan Lee", "Facilities Director"), ("General Contractor", gc, "Casey Miller", "Lead Estimator"),
        ("General Contractor", gc, "Jordan Patel", "Project Manager"), ("Architect", architect, "Avery Nguyen", "Project Architect"),
        ("Engineer", engineer, "Riley Johnson", "Building Envelope Engineer"), ("Supplier", rng.choice(VENDORS), "Taylor Brooks", "Architectural Sales"),
    ]
    doc["contacts"] = [{
        "id": uid("con"), "role": contact_role, "organization": org, "name": name, "position": position,
        "email": f"{name.lower().replace(' ', '.')}@example.com", "phone": f"555-{rng.randint(200, 899)}-{rng.randint(1000, 9999)}", "active": True,
    } for contact_role, org, name, position in people]

    base_codes = ["01 59 40", "02 41 00", "07 92 00", "08 11 00", "08 41 13", "08 44 13", "08 71 00", "08 80 00", "11 00 00"]
    doc["cost_codes"] = [_cost_code(config, code) for code in base_codes]

    quote_specs = [
        ("storefront-base", "08 41 13", 148000), ("curtainwall-base", "08 44 13", 226000),
        ("glass-base", "08 80 00", 92000), ("storefront-alt1", "ALT1-08 41 13", 132000),
    ]
    doc["quotes"] = []
    for group, code, price in quote_specs:
        vendors = rng.sample(VENDORS, 3)
        selected = rng.randrange(3)
        for index, vendor in enumerate(vendors):
            doc["quotes"].append(_quote(rng, group, code, vendor, price, index == selected,
                                        "Selected synthetic comparison quote" if index == selected else "Synthetic comparison quote"))
    doc["working_estimate"]["quote_selection_by_code"] = {
        code: {"mode": "automatic", "selected_quote_ids": []}
        for code in dict.fromkeys(row["code"] for row in doc["quotes"])
    }

    section_specs = [
        ("Level 1 Storefront", "08 41 13", "Storefront"), ("Main Curtain Wall", "08 44 13", "Curtain wall"),
        ("Interior Glazed Frames", "08 41 13", "Interior glazed partition"), ("Upper-Level Ribbon Windows", "08 44 13", "Ribbon window"),
        ("ALT1 Value-Engineered Storefront", "ALT1-08 41 13", "Storefront"),
    ]
    doc["takeoff_sections"] = []
    for section_index, (name, code, frame_type) in enumerate(section_specs):
        finish = rng.choice(FINISHES)
        doc["takeoff_sections"].append({
            "id": uid("sec"), "definition_id": "frame-v1", "name": name, "code": code,
            "material_overrides": {}, "tie_back_qty": rng.randint(6, 24), "backpan_lf": rng.randint(30, 180),
            "lines": [_frame_line(rng, section_index, line_index, frame_type, finish) for line_index in range(8)],
        })

    door_types = ["Narrow stile entrance", "Medium stile entrance", "Wide stile entrance", "All-glass entrance"]
    doc["doors"] = []
    doc["hardware_assignments"] = []
    for index in range(18):
        door_id = uid("dor")
        hw = f"HW{rng.randint(1, 6)}"
        doc["doors"].append({
            "id": door_id, "code": "08 11 00", "door_number": f"{101 + index}", "mark": f"D{index + 1}", "leaf_quantity": rng.choice([1, 1, 1, 2]),
            "width_inches": rng.choice([36, 42, 48]), "height_inches": rng.choice([84, 96]), "type": rng.choice(door_types),
            "material": "Aluminum", "finish": rng.choice(FINISHES), "description": "Glazed aluminum entrance door",
            "glass": rng.choice(["1-inch insulated", "1/4-inch tempered", "Laminated safety glass"]),
            "style": rng.choice(["Full vision", "10-inch bottom rail", "ADA bottom rail"]), "rails": "Standard top / optional mid / 10-inch bottom",
            "hardware_group_id": hw, "fire_rating": "None", "notes": "Synthetic door schedule; coordinate final handing.",
            "missing_quantity_acknowledged": False,
        })
        doc["hardware_assignments"].append({
            "id": uid("hwa"), "door_id": door_id, "hardware_group_id": hw, "quantity": 1,
            "code": "08 71 00", "notes": "Synthetic hardware assignment linked to door schedule.",
        })

    configured_equipment = {row.get("description"): row for row in config.get("equipment_rates", [])}
    equipment_specs = [
        ("45’ Boom Lift", 1, 2), ("60’ Boom Lift", 1, 2), ("7K Telehandler", 1, 1),
        ("Scissor Lift Interior", 2, 2), ("Truck & Trailer", 1, 12),
    ]
    doc["equipment"] = [{
        "id": uid("eqp"), "code": configured_equipment.get(description, {}).get("code", "11 00 00"), "description": description,
        "quantity": quantity, "duration": duration, "duration_unit": configured_equipment.get(description, {}).get("rate_unit") or None,
        "rate": configured_equipment.get(description, {}).get("base_rate"), "delivery_direction": "two_way", "delivery": configured_equipment.get(description, {}).get("delivery") or "0",
        "taxable": True, "rate_id": configured_equipment.get(description, {}).get("id"), "rate_version": config.get("id"),
        "notes": "Owner-provided rental reference used for synthetic testing; verify stale vendor rate and duration before commercial use.",
    } for description, quantity, duration in equipment_specs]
    existing_codes = {normalize_code(row.get("code")) for row in doc["cost_codes"]}
    for equipment in doc["equipment"]:
        normalized = normalize_code(equipment.get("code"))
        if normalized and normalized not in existing_codes:
            doc["cost_codes"].append(_cost_code(config, equipment["code"]))
            existing_codes.add(normalized)

    doc["borrowed_lites"] = [{
        "id": uid("brl"), "code": "08 80 00", "mark": f"BL-{index + 1}", "quantity": rng.randint(1, 5),
        "width_inches": rng.choice([12, 18, 24, 30, 36, 48]), "height_inches": rng.choice([12, 18, 24, 36, 48, 60]),
        "rate": str(rng.choice([28, 32, 36, 42])), "notes": "Synthetic borrowed-lite takeoff; five ft² minimum applies per row quantity.",
    } for index in range(8)]

    labor_specs = [
        ("field", "08 41 13", "Storefront layout and installation", 1680, "SF", 2, 5.5, field_rate, field_rate_id),
        ("field", "08 44 13", "Curtain-wall layout and installation", 2750, "SF", 3, 4.2, field_rate, field_rate_id),
        ("field", "08 11 00", "Entrance door installation", 18, "doors", 1, 0.34, field_rate, field_rate_id),
        ("field", "08 71 00", "Door hardware installation", 18, "openings", 1, 0.22, field_rate, field_rate_id),
        ("field", "08 80 00", "Glass setting and glazing", 3180, "SF", 2, 8.0, field_rate, field_rate_id),
        ("field", "07 92 00", "Exterior perimeter sealants", 1240, "LF", 1, 22, field_rate, field_rate_id),
        ("shop", "08 41 13", "Storefront fabrication", 1680, "SF", 1, 18, shop_standard, "labor_shop_2025"),
        ("shop", "08 44 13", "Curtain-wall fabrication", 2750, "SF", 2, 16, shop_standard, "labor_shop_2025"),
        ("shop", "08 11 00", "Entrance preparation", 18, "doors", 1, 1.8, shop_standard, "labor_shop_2025"),
        ("shop", "08 71 00", "Hardware preparation", 18, "openings", 1, 1.5, shop_standard, "labor_shop_2025"),
        ("design", "08 41 13", "Storefront shop drawings", 1, "package", 1, 0.025, "95", "synthetic_design_rate"),
        ("design", "08 44 13", "Curtain-wall engineering coordination", 1, "package", 1, 0.016, "105", "synthetic_design_rate"),
        ("design", "08 80 00", "Glazing submittals", 1, "package", 1, 0.05, "92", "synthetic_design_rate"),
        ("field", "ALT1-08 41 13", "ALT1 storefront installation", 1420, "SF", 2, 5.5, field_rate, field_rate_id),
    ]
    doc["labor_estimates"] = []
    for category, code, description, quantity, unit, crew, productivity, rate, rate_id in labor_specs:
        labor_type = category.title()
        controlled_available = labor_type != "Design"
        controlled_rate = str(rate) if controlled_available else None
        controlled_id = rate_id if controlled_available else "labor_design_unavailable"
        man_hours = Decimal(str(quantity)) / Decimal(str(crew)) / Decimal(str(productivity))
        doc["labor_estimates"].append({
            "id": uid("lbr"), "labor_type": labor_type, "category": category, "code": code, "description": description,
            "man_hours": str(man_hours), "man_hours_source": "synthetic_test_input", "crew_size": crew,
            "hours_per_worker_per_day": "8", "workdays_per_week": "5",
            "controlled_rate_snapshot": {
                "rate": controlled_rate, "rate_id": controlled_id, "configuration_id": config.get("id"),
                "source": config.get("rate_reference", {}).get("source"),
                "status": "owner_provided" if controlled_available else "unavailable_no_owner_design_rate",
            },
            "legacy_effective_rate": None, "rate_override": None, "rate_override_reason": None,
            "rate": controlled_rate, "rate_id": controlled_id, "rate_version": config.get("id"),
            "origin": "manual", "source_links": [], "source_status": "unclassified", "stale_acknowledged": False,
            # Retained only as clearly labeled test lineage; new cost uses Man Hours.
            "quantity": quantity, "quantity_unit": unit, "crew": crew, "productivity": productivity,
            "notes": "Owner-provided controlled rate reference used for testing." if controlled_available else "No owner-controlled Design rate exists; this line intentionally blocks commercial submission and contributes no Design cost.",
        })

    doc["travel_estimates"] = [
        {"id": uid("trv"), "code": "01 59 40", "enabled": False, "crew_load": 6, "days_per_week": 5, "row_days": 65,
         "excluded_days": 3, "lodging": "0", "per_diem_rate": per_diem, "rate_id": "per_diem_owner_2025", "rate_version": config.get("id"), "notes": "Owner-provided per diem retained, but disabled because travel policy is pending."},
        {"id": uid("trv"), "code": "01 59 40", "enabled": False, "crew_load": 4, "days_per_week": 4, "row_days": 24,
         "excluded_days": 2, "lodging": "0", "per_diem_rate": per_diem, "rate_id": "per_diem_owner_2025", "rate_version": config.get("id"), "notes": "Owner-provided per diem retained, but disabled because travel policy is pending."},
        {"id": uid("trv"), "code": "ALT1-01 59 40", "enabled": False, "crew_load": 3, "days_per_week": 5, "row_days": 18,
         "excluded_days": 0, "lodging": "0", "per_diem_rate": per_diem, "rate_id": "per_diem_owner_2025", "rate_version": config.get("id"), "notes": "Owner-provided per diem retained, but disabled because travel policy is pending."},
    ]

    doc["working_estimate"].update({
        "alternate_inclusion": {"ALT1": True, "ALT2": False, "ALT3": False, "ALT4": False},
        "markup_overrides": {"base_product": "0.12", "LAF": "0.18", "LAS": "0.15"},
        "contingency_enabled": False, "bond_enabled": False,
        "labor_suggestion_exclusions": [], "component_markup_overrides": {},
    })
    doc["alternates"] = [
        {"id": uid("alt"), "variant": "ALT1", "name": "Value-engineered storefront system", "included": True,
         "description": "Synthetic priced alternate using matching quote, frame, labor, and travel-source records.", "status": "testing"},
        {"id": uid("alt"), "variant": "ALT2", "name": "Alternate finish", "included": False,
         "description": "Placeholder for testing; no commercial value asserted.", "status": "pending_scope"},
    ]
    doc["bid_tabulations"] = [
        {"id": uid("tab"), "participant": gc, "bid_value": str(rng.randrange(780000, 980000, 5000)), "alternates": "ALT1 included",
         "qualifications": "Synthetic comparison only", "source": "Test bid opening", "date": bid_due.isoformat(), "status": "pending", "notes": "Not a real competitor bid."},
        {"id": uid("tab"), "participant": "Metro Envelope Systems", "bid_value": str(rng.randrange(800000, 1030000, 5000)), "alternates": "ALT1 separate",
         "qualifications": "Synthetic comparison only", "source": "Test bid opening", "date": bid_due.isoformat(), "status": "pending", "notes": "Fictitious participant."},
        {"id": uid("tab"), "participant": "Twin Cities Glassworks", "bid_value": str(rng.randrange(770000, 1010000, 5000)), "alternates": "No alternates",
         "qualifications": "Synthetic comparison only", "source": "Test bid opening", "date": bid_due.isoformat(), "status": "pending", "notes": "Fictitious participant."},
        {"id": uid("tab"), "participant": "Internal target", "bid_value": "0", "alternates": "Calculated in Bid area",
         "qualifications": "Training benchmark", "source": "Generated test project", "date": bid_due.isoformat(), "status": "pending", "notes": "Update after calculation review."},
    ]

    audit(doc, actor, role, "project", doc["project"]["id"], "generate_test_project", None,
          {"seed": seed_value, "profile": profile["kind"], "generator_version": GENERATOR_VERSION},
          "Generated curated synthetic project for training and workflow testing")
    # Feed the former prefixed fixtures through the same one-time migration used
    # for real 1.1 projects so generated work exercises only Base-plus-delta.
    doc["schema_version"] = "1.1.0"; doc["interchange_version"] = "1.1.0"
    return migrate_project_document(doc)
