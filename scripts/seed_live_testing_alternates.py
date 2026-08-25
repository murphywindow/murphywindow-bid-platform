"""Seed five varied Base-plus-delta Alternates into the Live Testing Project."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.alternates import add_record, new_alternate, remove_record, set_override
from app.persistence import JsonStore
from app.services import audit, calculate_project


PROJECT_ID = "prj_8135070f334a40b1b93ab3ae8cf9fe49"


def frame(document: dict, code: str, mark: str, occurrence: int = 0) -> dict:
    matches = [
        row
        for section in document.get("takeoff_sections", [])
        if section.get("code") == code
        for row in section.get("lines", [])
        if row.get("mark") == mark
    ]
    return matches[occurrence]


def section(document: dict, code: str) -> dict:
    return next(row for row in document.get("takeoff_sections", []) if row.get("code") == code)


def override(alternate: dict, collection: str, record: dict, field: str, value) -> None:
    current = record
    for part in field.split("."):
        current = current.get(part) if isinstance(current, dict) else None
    set_override(alternate, collection, str(record["id"]), field, current, value)


def seed() -> dict:
    store = JsonStore(ROOT / "data")
    document, _ = store.load_project(PROJECT_ID)
    if document.get("project", {}).get("name") != "Live Testing Project":
        raise RuntimeError("The fixed project ID no longer identifies Live Testing Project.")
    expected_revision = int(document["project"].get("revision", 0))
    configuration = store.load_configuration(document["project"]["configuration_id"])

    alternates = sorted(document.setdefault("alternates", []), key=lambda row: int(row.get("sequence", 0)))
    while len(alternates) < 5:
        alternate = new_alternate(document, f"Comparison test scenario {len(alternates) + 1}")
        document["alternates"].append(alternate)
        alternates.append(alternate)
    alternates = alternates[:5]
    names = [
        "Storefront quantity and finish study",
        "Scope removals and labor schedule",
        "Added entrance and equipment scope",
        "Zero quantities and commercial revisions",
        "Broad mixed-scope review",
    ]
    for sequence, (alternate, name) in enumerate(zip(alternates, names), 1):
        alternate.update(sequence=sequence, key=f"ALT{sequence}", name=name,
                         customer_description=f"Seeded visual comparison scenario {sequence}", changes={})

    storefront = section(document, "08 41 13")
    curtain = section(document, "08 44 13")
    storefront_a1 = frame(document, "08 41 13", "A1")
    storefront_a3 = frame(document, "08 41 13", "A3")
    storefront_a4 = frame(document, "08 41 13", "A4")
    storefront_a5 = frame(document, "08 41 13", "A5")
    storefront_a6 = frame(document, "08 41 13", "A6")
    curtain_a1 = frame(document, "08 44 13", "A1")
    curtain_a4 = frame(document, "08 44 13", "A4")
    quotes = document.get("quotes", [])
    selected_quote = next((row for row in quotes if row.get("used")), quotes[0])
    equipment = document.get("equipment", [])
    labor = document.get("labor_estimates", [])
    borrowed = document.get("borrowed_lites", [])

    alt1 = alternates[0]
    override(alt1, "frames", storefront_a1, "quantity", 10)
    override(alt1, "frames", curtain_a1, "notes", "Coordinate Hart finish")
    override(alt1, "frames", curtain_a1, "finish", "Dark bronze fluoropolymer")
    override(alt1, "quotes", selected_quote, "price", str(float(selected_quote.get("price") or 0) + 5000))
    override(alt1, "equipment", equipment[0], "quantity", 2)
    override(alt1, "labor_estimates", labor[0], "crew_size", 4)

    alt2 = alternates[1]
    remove_record(alt2, "frames", storefront_a3["id"])
    override(alt2, "frames", storefront_a4, "caulking_passes", 4)
    override(alt2, "frames", curtain_a4, "notes", "Field verify Hart opening")
    override(alt2, "labor_estimates", labor[1], "hours_per_worker_per_day", 10)
    override(alt2, "labor_estimates", labor[1], "workdays_per_week", 4)
    remove_record(alt2, "borrowed_lites", borrowed[1]["id"])

    alt3 = alternates[2]
    add_record(alt3, "frames", {
        "id": "frm_alt_test_a11", "section_id": storefront["id"], "mark": "A11", "quantity": 6,
        "width_inches": 42, "height_inches": 96, "caulking_passes": 3, "head": "Standard",
        "sill": "Standard", "jamb": "Expansion jamb", "type": "Storefront", "material": "Extruded aluminum",
        "finish": "Dark bronze fluoropolymer", "notes": "Added test entrance framing", "installation_material_ids": [],
    })
    add_record(alt3, "doors", {
        "id": "dor_alt_test_d101", "code": "08 41 13", "door_number": "D101", "mark": "D101",
        "leaf_quantity": 2, "width_inches": 36, "height_inches": 84, "type": "Pair", "material": "Aluminum",
        "finish": "Dark bronze", "description": "Main entrance pair", "glass": "1-inch insulated",
        "style": "Narrow stile", "rails": "10-inch bottom rail", "fire_rating": "None", "notes": "Alternate-only entrance",
    })
    added_equipment = deepcopy(equipment[0])
    added_equipment.update(id="eqp_alt_test_scissor", description="Scissor Lift", quantity=2, duration=10,
                           duration_unit="day", rate="185.00", delivery="150.00", notes="Alternate-only interior lift")
    for key in list(added_equipment):
        if key.startswith("calculated"):
            added_equipment.pop(key)
    add_record(alt3, "equipment", added_equipment)

    alt4 = alternates[3]
    override(alt4, "frames", storefront_a5, "quantity", 0)
    override(alt4, "frames", storefront_a5, "finish", "Clear anodized")
    override(alt4, "quotes", selected_quote, "vendor", f"{selected_quote.get('vendor')} Hart")
    override(alt4, "quotes", selected_quote, "tax_included", not bool(selected_quote.get("tax_included")))
    override(alt4, "equipment", equipment[1], "rate", "2300.00")
    remove_record(alt4, "equipment", equipment[2]["id"])

    alt5 = alternates[4]
    override(alt5, "frames", storefront_a6, "width_inches", 54)
    override(alt5, "frames", storefront_a6, "height_inches", 114)
    override(alt5, "frames", storefront_a6, "notes", "Backpans from Hart")
    override(alt5, "takeoff_sections", storefront, "tie_back_qty", 24)
    override(alt5, "quotes", selected_quote, "notes", "Selected Hart comparison quote")
    override(alt5, "labor_estimates", labor[0], "man_hours", "240")
    override(alt5, "labor_estimates", labor[0], "notes", "Owner-provided Hart rate reference used for testing.")
    override(alt5, "borrowed_lites", borrowed[0], "quantity", 3)
    remove_record(alt5, "frames", curtain_a1["id"])
    added_quote = {
        "id": "quo_alt_test_hart", "code": "08 41 13", "date": "2026-08-25", "vendor": "Hart Glass Systems",
        "price": "151250.00", "square_feet": None, "credit_type": "dollar", "credit_value": "2500",
        "surcharge_type": "percentage", "surcharge_value": "0.025", "tax_included": False,
        "used": False, "notes": "Alternate-only testing quote",
    }
    add_record(alt5, "quotes", added_quote)

    calculate_project(document, configuration)
    audit(document, "Codex", "Systems Administrator", "project", PROJECT_ID, "alternate_test_data_seed",
          None, {"alternate_count": 5, "scenario_names": names},
          "Seeded varied Base-plus-delta comparison data for estimator visual testing")
    saved = store.save_project(document, expected_revision)
    return {"project": saved["project"]["name"], "revision": saved["project"]["revision"],
            "alternates": [{"sequence": row["sequence"], "name": row["name"],
                            "change_groups": len(row.get("changes", {}))} for row in saved["alternates"][:5]]}


if __name__ == "__main__":
    import json
    print(json.dumps(seed(), indent=2))
