"""Create deterministic, clearly labeled historical-reference Bid evidence.

These records live outside data/projects so they do not crowd the normal project
picker.  Each record contains one immutable submitted revision and is processed
by the same historical evidence validator as completed live projects.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import random
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.historical import BID_COST_CODE_SELL_PER_SF_METRIC, HistoricalMetricIndex
from app.persistence import JsonStore
from app.schema import PROJECT_TYPES, new_project


CENT = Decimal("0.01")
AREA = Decimal("0.0001")
CODES = (
    ("08 41 13", "Aluminum-Framed Entrances and Storefronts", Decimal("43")),
    ("08 44 13", "Glazed Aluminum Curtain Walls", Decimal("61")),
    ("08 80 00", "Glazing", Decimal("34")),
    ("ALT1-08 41 13", "Aluminum-Framed Entrances and Storefronts", Decimal("48")),
)
BUILDINGS = ("Commercial", "Education", "Healthcare", "Municipal", "Hospitality", "Retail")


def q(value: Decimal, places: Decimal = CENT) -> Decimal:
    return value.quantize(places, rounding=ROUND_HALF_UP)


def frame_section(rng: random.Random, project_id: str, code: str, index: int) -> tuple[dict, Decimal]:
    lines, total = [], Decimal(0)
    for line_index in range(3):
        width = rng.choice((48, 60, 72, 96, 120, 144))
        height = rng.choice((72, 84, 96, 108, 120, 144))
        quantity = rng.randint(2, 14)
        square_feet = q(Decimal(width * height * quantity) / Decimal(144), AREA)
        total += square_feet
        lines.append({
            "id": f"frm_{project_id}_{index}_{line_index}", "mark": f"F{index + 1}-{line_index + 1}",
            "quantity": quantity, "width_inches": width, "height_inches": height,
            "caulking_passes": 3, "calculated": {"square_feet": str(square_feet)},
        })
    return {
        "id": f"sec_{project_id}_{index}", "code": code, "name": CODES[index][1],
        "lines": lines, "totals": {"square_feet": str(q(total, AREA))},
    }, q(total, AREA)


def historical_bid(index: int, seed: int) -> dict:
    rng = random.Random(seed * 100_003 + index)
    project_id = f"prj_histref_{index + 1:04d}"
    project_type = PROJECT_TYPES[index % len(PROJECT_TYPES)]
    document = new_project(f"Historical Reference Bid {index + 1:04d}", "Historical Reference Seeder", "Estimator")
    submitted = datetime(2019, 1, 15, 12, tzinfo=UTC) + timedelta(days=index * 11)
    project = document["project"]
    project.update({
        "id": project_id, "project_number": f"HIST-{index + 1:04d}",
        "data_classification": "historical_reference_fixture",
        "project_type": project_type, "project_type_status": "current",
        "building_type": BUILDINGS[index % len(BUILDINGS)],
        "contract_type": "Bid as GC" if index % 7 == 0 else "Bid to CM/GC",
        "wage_type": "PW" if index % 5 == 0 else "Non-PW",
        "bid_due_date": submitted.date().isoformat(),
        "notes": "Controlled simulated historical reference evidence; never a live customer project.",
    })
    cost_codes, sections, summaries, estimate_lines = [], [], [], []
    total_cost = Decimal(0)
    total_value = Decimal(0)
    total_area = Decimal(0)
    type_family = project_type.split(" - ")[-1]
    family_factor = {"Curtainwall": Decimal("1.18"), "Exterior Storefront": Decimal("1.00"),
                     "Interior Storefront": Decimal("0.88"), "Windows": Decimal("1.08")}[type_family]
    phase_factor = Decimal("1.10") if project_type.startswith(("Repair", "Replacement")) else Decimal("1.04") if project_type.startswith("Addition") else Decimal("1.00")
    base_margin = Decimal("0.105") + Decimal(index % 9) * Decimal("0.009")
    for code_index, (code, description, base_rate) in enumerate(CODES):
        section, square_feet = frame_section(rng, project_id, code, code_index)
        sections.append(section)
        rate_noise = Decimal(str(rng.uniform(.88, 1.16)))
        annual_factor = Decimal("1") + Decimal(str((submitted.year - 2019) * .035))
        selling_value = q(square_feet * base_rate * family_factor * phase_factor * annual_factor * rate_noise)
        margin = min(Decimal("0.245"), base_margin + Decimal(code_index) * Decimal("0.006"))
        direct_cost = q(selling_value * (Decimal("1") - margin))
        margin_dollars = selling_value - direct_cost
        total_cost += direct_cost
        total_value += selling_value
        total_area += square_feet
        cost_codes.append({"id": f"ccd_{project_id}_{code_index}", "code": code, "description": description, "deduct": False, "status": "active"})
        summaries.append({
            "code": code, "description": description, "included": True,
            "direct_cost": str(direct_cost), "selling_value": str(selling_value),
            "margin_dollars": str(margin_dollars), "margin_percentage": str(margin),
            "total_square_feet": str(square_feet), "dollars_per_square_foot": str(q(selling_value / square_feet, AREA)),
            "metric_definition": BID_COST_CODE_SELL_PER_SF_METRIC,
        })
        estimate_lines.append({
            "id": f"est_{project_id}_{code_index}", "code": code, "description": description,
            "included": True, "direct_cost": str(direct_cost), "selling_value": str(selling_value), "area": str(square_feet),
        })
    revision_id = f"rev_{project_id}_1"
    revision = {
        "id": revision_id, "revision_number": 1, "configuration_id": project["configuration_id"],
        "status": "submitted", "immutable": True, "created_at": submitted.isoformat(),
        "bid_version": {"display": "B1.0.0", "major": 1, "minor": 0, "patch": 0, "sequence": 1},
        "project_snapshot": deepcopy(project), "cost_codes": cost_codes,
        "source_snapshot": {"takeoff_sections": sections, "borrowed_lites": []},
        "estimate": {
            "lines": estimate_lines, "cost_code_summaries": summaries,
            "totals": {"direct_cost": str(q(total_cost)), "selling_value": str(q(total_value)),
                       "markup_profit": str(q(total_value - total_cost)),
                       "margin_percentage": str((total_value - total_cost) / total_value),
                       "square_feet": str(q(total_area, AREA))},
        },
    }
    document["cost_codes"] = deepcopy(cost_codes)
    document["estimate_revisions"] = [revision]
    document["submissions"] = [{
        "id": f"sub_{project_id}_1", "revision_id": revision_id, "immutable": True,
        "submitted_at": submitted.isoformat(), "recipient": "Historical Reference Archive",
    }]
    document["takeoff_sections"] = deepcopy(sections)
    return document


def seed(store: JsonStore, count: int, seed_value: int) -> dict:
    if not 100 <= count <= 500:
        raise ValueError("Historical reference count must be between 100 and 500.")
    for index in range(count):
        document = historical_bid(index, seed_value)
        store.save_historical_reference(document)
    index = HistoricalMetricIndex(store).rebuild()
    references = [record for record in index["projects"].values() if record.get("data_classification") == "historical_reference_fixture"]
    observations = [item for record in references for item in record.get("observations", [])]
    return {"bids": len(references), "observations": len(observations), "cost_codes": len(index["observations_by_code"]), "index_revision": index["revision"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=240)
    parser.add_argument("--seed", type=int, default=4320)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    print(seed(JsonStore(args.data_root), args.count, args.seed))


if __name__ == "__main__":
    main()
