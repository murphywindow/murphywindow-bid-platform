"""Normalized owner-provided rate tables received 2026-08-17.

Source blanks and unavailable values remain ``None``. Notes embedded in the source
are retained as data and are not interpreted as implementation instructions.
"""
from __future__ import annotations

from decimal import Decimal

RATE_REFERENCE_ID = "owner-rate-tables-2026-08-17-v1"
SOURCE = "Owner-provided rate tables received 2026-08-17"


COUNTY_RATES = """Aitkin|38.65|22.89|61.54
Anoka|54.03|28.25|82.28
Becker|54.03|28.25|82.28
Beltrami|38.65|22.89|61.54
Benton|38.65|22.89|61.54
Big Stone|54.03|28.25|82.28
Blue Earth|54.03|28.25|82.28
Brown|54.03|28.25|82.28
Carlton|41.76|28.09|69.85
Carver|54.03|28.25|82.28
Cass|54.03|28.25|82.28
Chippewa|30.43|14.90|45.33
Chisago|54.03|28.25|82.28
Clay|54.03|28.25|82.28
Clearwater|38.65|22.89|61.54
Cook|41.76|28.09|69.85
Cottonwood|54.03|28.25|82.28
Crow Wing|38.65|22.89|61.54
Dakota|54.03|28.25|82.28
Dodge|54.03|28.25|82.28
Douglas|38.65|22.89|61.54
Faribault|39.24|13.46|52.70
Fillmore|39.24|13.46|52.70
Freeborn|39.24|13.46|52.70
Goodhue|39.24|13.46|52.70
Grant|38.65|22.89|61.54
Hennepin|54.03|28.25|82.28
Houston|43.66|22.47|66.13
Hubbard|38.65|22.89|61.54
Isanti|54.03|28.25|82.28
Itasca|41.76|28.09|69.85
Jackson|54.03|28.25|82.28
Kanabec|38.65|22.89|61.54
Kandiyohi|38.65|22.89|61.54
Kittson|38.65|22.89|61.54
Koochiching|41.76|28.09|69.85
Lac qui Parle|54.03|28.25|82.28
Lake|41.76|28.09|69.85
Lake of the Woods|54.03|28.25|82.28
Le Sueur|54.03|28.25|82.28
Lincoln|48.73|23.50|72.23
Lyon|54.03|28.25|82.28
McLeod|40.65|24.21|64.86
Mahnomen|38.65|22.89|61.54
Marshall|54.03|28.25|82.28
Martin|38.65|22.89|61.54
Meeker|38.65|22.89|61.54
Mille Lacs|38.65|22.89|61.54
Morrison|38.65|22.89|61.54
Mower|39.24|13.46|52.70
Murray|37.74|12.96|50.70
Nicollet|39.24|13.46|52.70
Nobles|39.24|13.46|52.70
Norman|54.03|28.25|82.28
Olmsted|39.24|13.46|52.70
Otter Tail|38.65|22.89|61.54
Pennington|38.65|22.89|61.54
Pine|54.03|28.25|82.28
Pipestone|37.74|12.96|50.70
Polk|40.65|24.21|64.86
Pope|38.65|22.89|61.54
Ramsey|54.03|28.25|82.28
Red Lake|48.98|26.75|75.73
Redwood|54.03|28.25|82.28
Renville|38.65|22.89|61.54
Rice|54.03|28.25|82.28
Rock|39.24|13.46|52.70
Roseau|38.65|22.89|61.54
St. Louis|41.76|28.09|69.85
Scott|54.03|28.25|82.28
Sherburne|38.65|22.89|61.54
Sibley|54.03|28.25|82.28
Stearns|38.65|22.89|61.54
Steele|39.24|13.46|52.70
Stevens|54.03|28.25|82.28
Swift|54.03|28.25|82.28
Todd|38.65|22.89|61.54
Traverse|54.03|28.25|82.28
Wabasha|39.24|13.46|52.70
Wadena|38.65|22.89|61.54
Waseca|39.24|13.46|52.70
Washington|54.03|28.25|82.28
Watonwan|54.03|28.25|82.28
Wilkin|38.65|22.89|61.54
Winona|39.24|13.46|52.70
Wright|38.65|22.89|61.54
Yellow Medicine|54.03|28.25|82.28"""


def _wage_records() -> list[dict]:
    rows = []
    for line in COUNTY_RATES.splitlines():
        county, basic, fringe, total = line.split("|")
        wage, fringe_value = Decimal(basic), Decimal(fringe)
        credit = wage * Decimal("0.1425")
        rows.append({
            "id": f"pw_mn_{county.lower().replace(' ', '_').replace('.', '')}_owner_2026",
            "county": county, "classification": None, "published_wage": basic, "published_fringe": fringe,
            "published_total": total, "fringe_credit_rate": "0.1425", "fringe_credit": str(credit),
            "usable_fringe": str(fringe_value - credit),
            "estimated_company_rate": str(wage + fringe_value - credit),
            "effective_date": None, "received_date": "2026-08-17", "source": SOURCE,
            "status": "owner_provided_pending_classification_and_effective_date",
            "note": "County table did not identify labor classification or rate effective date; do not treat as a published determination without verification.",
        })
    return rows


def _burden_records() -> list[dict]:
    field = [
        ("journeyman_1", "Journeyman", "51.73", "20.37", "72.10", "74.79", "99.00"),
        ("journeyman_2", "Journeyman", "49.73", "19.65", "69.38", "71.97", "95.24"),
        ("journeyman_3", "Journeyman", "49.73", "19.65", "69.38", "71.97", "95.24"),
        ("apprentice", "Apprentice", "38.00", "15.43", "53.43", "55.41", "73.19"),
        ("average", "AVERAGE", "47.30", "18.78", "66.07", "68.53", "90.67"),
    ]
    shop = [
        ("manager", "Shop Mgr", "29.00", "12.19", "42.76", "44.21", "57.26"),
        ("tech_1", "Shop Tech", "24.00", "10.39", "35.70", "36.90", "47.70"),
        ("tech_2", "Shop Tech", "23.00", "10.03", "34.29", "35.44", "45.79"),
        ("average", "AVERAGE", "25.33", "10.87", "37.58", "38.85", "50.25"),
    ]
    result = [{"id": f"burden_field_nonpw_{key}", "group": "2025 MWD Labor Burden Field Non PW", "category": "field", "prevailing_wage": False,
               "status_name": name, "hourly_wage": hourly, "direct_overhead": overhead, "total_burden": burden,
               "total_burden_with_ot": ot, "total_burden_all_ot": all_ot, "effective_year": 2025, "source": SOURCE, "status": "owner_provided"}
              for key, name, hourly, overhead, burden, ot, all_ot in field]
    result.extend({"id": f"burden_shop_{key}", "group": "MWD Labor Burden Shop", "category": "shop", "prevailing_wage": False,
                   "status_name": name, "hourly_wage": hourly, "direct_overhead": overhead, "total_burden": burden,
                   "total_burden_with_ot": ot, "total_burden_all_ot": all_ot, "effective_year": 2025, "source": SOURCE, "status": "owner_provided_source_values_preserved"}
                  for key, name, hourly, overhead, burden, ot, all_ot in shop)
    result.extend([
        {"id": "burden_field_pw_journeyman_1", "group": "2025 MWD Labor Burden Field PW 06/2023 Metro Rates", "category": "field", "prevailing_wage": True, "status_name": "Journeyman", "hourly_wage": None, "direct_overhead": None, "pw_fringe": None, "total_burden": None, "total_burden_with_ot": None, "total_burden_all_ot": None, "source_value": "#N/A", "status": "unavailable_in_owner_source", "source": SOURCE},
        {"id": "burden_field_pw_journeyman_2", "group": "2025 MWD Labor Burden Field PW 06/2023 Metro Rates", "category": "field", "prevailing_wage": True, "status_name": "Journeyman", "hourly_wage": None, "direct_overhead": None, "pw_fringe": None, "total_burden": None, "total_burden_with_ot": None, "total_burden_all_ot": None, "source_value": "#N/A", "status": "unavailable_in_owner_source", "source": SOURCE},
        {"id": "burden_field_pw_journeyman_3", "group": "2025 MWD Labor Burden Field PW 06/2023 Metro Rates", "category": "field", "prevailing_wage": True, "status_name": "Journeyman", "hourly_wage": None, "direct_overhead": None, "pw_fringe": None, "total_burden": None, "total_burden_with_ot": None, "total_burden_all_ot": None, "source_value": "#N/A", "status": "unavailable_in_owner_source", "source": SOURCE},
        {"id": "burden_field_pw_apprentice", "group": "2025 MWD Labor Burden Field PW 06/2023 Metro Rates", "category": "field", "prevailing_wage": True, "status_name": "Apprentice", "hourly_wage": "38.00", "direct_overhead": "15.43", "pw_fringe": "0.00", "total_burden": "53.43", "total_burden_with_ot": "55.41", "total_burden_all_ot": "73.19", "status": "owner_provided", "source": SOURCE},
        {"id": "burden_field_pw_average", "group": "2025 MWD Labor Burden Field PW 06/2023 Metro Rates", "category": "field", "prevailing_wage": True, "status_name": "AVERAGE", "hourly_wage": None, "direct_overhead": None, "pw_fringe": None, "total_burden": None, "total_burden_with_ot": None, "total_burden_all_ot": None, "source_value": "#N/A", "status": "unavailable_in_owner_source", "source": SOURCE},
    ])
    return result


def _equipment_rates() -> list[dict]:
    rows = [
        ("30 Ton Boom Truck", "41 62 00", "Northland Crane Service (NCS)", "210.00", "hour", None, None, None),
        ("45 Ton Boom Truck", "41 62 00", "Northland Crane Service (NCS)", "235.00", "hour", None, None, None),
        ("55 Ton Boom Truck", "41 62 00", "Northland Crane Service (NCS)", "250.00", "hour", None, None, None),
        ("60 Ton Boom Truck", "41 62 00", "Northland Crane Service (NCS)", "285.00", "hour", None, None, None),
        ("120 Ton Truck Crane", "41 22 13", "Northland Crane Service (NCS)", "405.00", "hour", None, None, None),
        ("175 Ton Truck Crane", "41 22 13", "Northland Crane Service (NCS)", "435.00", "hour", None, None, None),
        ("Truck & Trailer", "41 62 00", "Northland Crane Service (NCS)", "165.00", "hour", None, None, None),
        ("45’ Boom Lift", "14 40 00", "API", "1750.00", "month", "100.00", "200.00", "2024-01-01"),
        ("60’ Boom Lift", "14 40 00", "API", "2055.00", "month", "125.00", "250.00", "2024-01-01"),
        ("80’ Boom Lift", "14 40 00", "API", "3435.00", "month", "125.00", "250.00", "2024-01-01"),
        ("7K Telehandler", "41 62 23", "API", "2050.00", "month", "100.00", "200.00", "2024-01-01"),
        ("Scissor Lift Interior", "14 83 16", None, "350.00", "month", "100.00", "200.00", "2024-01-01"),
        ("Scissor Lift Exterior", "14 83 16", "API", "800.00", "month", "100.00", "200.00", "2024-01-01"),
        ("Fencing (Footly)", "01 56 26", None, None, None, None, None, None),
        ("Dumpster", "01 74 19", None, "600.00", "other", None, None, None),
        ("Overhead Protection", "10 73 00", None, "125.00", "month", None, None, None),
        ("Scaffold", "13 80 00", None, "125.00", "month", None, None, None),
        ("40 ft Aerial", "14 40 00", None, "2000.00", "month", None, None, None),
        ("Swingstage", "14 43 16", None, None, "call_vendor", None, None, None),
        ("Crane", "41 22 13", None, None, None, None, None, None),
        ("Container", "41 52 13.33", None, "125.00", "month", None, None, None),
        ("7,000 Telehandler", "41 62 23", None, "2800.00", "month", None, None, None),
    ]
    return [{"id": f"equipment_owner_{index:02d}", "description": description, "code": code, "category": "rental", "vendor": vendor,
             "base_rate": rate, "rate_unit": unit, "delivery_one_way": one_way, "delivery": two_way,
             "tax_included_in_base": False, "sales_tax_rate": "0.0738", "effective_date": None, "last_checked": checked,
             "source": SOURCE, "status": "owner_provided_stale_or_unverified", "notes": "Source column values preserved; verify current vendor rate and rental duration before use."}
            for index, (description, code, vendor, rate, unit, one_way, two_way, checked) in enumerate(rows, 1)]


def _material_rates() -> list[dict]:
    rows = [
        ("Metal", "OBE", None, None, None, "OBE (Base + Sales Tax)", "2022-10-12"),
        ("Glass (Frames by Others)", "OBE", None, None, "0.145", "OBE (Base + Sales Tax + 14.5% Surcharge)", "2022-10-12"),
        ("Glass (Frames by OBE)", "OBE", None, None, "0.095", "Glass size rounds up to the even inch when using sqft (Base + Sales Tax + 9.5% Surcharge)", "2022-10-12"),
        ("20oz Sausage - Standard Colors", "Dymonic FC", "9.85", "unit", None, "S&S", "2022-04-12"),
        ("20oz Sausage", "Dow795", "16.03", "unit", None, "S&S", "2022-04-12"),
        ("2-inch Mineral Wool Insulation", "Insulation Distributors Inc.", "0.62", "unit", None, "Rockwool", "2025-12-05"),
        ("3-inch Mineral Wool Insulation", "Insulation Distributors Inc.", "0.94", "unit", None, "Rockwool", "2025-12-05"),
        ("4-inch Mineral Wool Insulation", "Insulation Distributors Inc.", "1.25", "unit", None, "Rockwool", "2025-12-05"),
        ("6-inch Mineral Wool Insulation", "Insulation Distributors Inc.", "1.88", "unit", None, "Rockwool", "2025-12-05"),
        (".040 Back Pans in Standard Colors", None, "12.00", "sqft", None, "Americlad, Bell Pro, Division 8; quote if possible", None),
        ("BRM 5.5 x 2.5 .040 Standard Color Sill Flashing", None, "8.00", "sqft", None, "If sills are not standard they should be quoted", None),
        ("Insulated Metal Panels (Mapes 1-inch OA, foam core, poly interlayer)", None, "30.00", "sqft", None, None, None),
        ("Hilti Quick Seal Slab Edge Firestopping", "Hilti", "11.00", "sqft", None, "In 60-inch sticks; source says factor waste and confirm specification", None),
        ("AC Chill Stopper (Interior plastic cover)", "MidStates Plastic / Karls", "55.00", "unit", None, None, None),
        ("AC Sleeve", "GE / THS / Inthermo / Quality Painting", "350.00", "unit", None, "Includes sleeve, louver, stripping, and painting", None),
        ("Tie Back for CW", "Fabricated", "45.00", "unit", None, "Source notes 0.5 field labor hour each", None),
        ("Backpans for Behind Spandrel (pan only)", None, "48.32", "other", None, "Source note says update to amount times square feet; retained as source note, not an implemented rule", "2025-12-05"),
    ]
    return [{"id": f"material_owner_{index:02d}", "description": description, "vendor": vendor, "base_rate": rate, "rate_unit": unit,
             "tax_included_in_base": True, "sales_tax_rate": "0.0738", "surcharge_rate": surcharge, "notes": notes,
             "effective_date": None, "last_checked": checked, "source": SOURCE, "status": "owner_provided_stale_or_unverified"}
            for index, (description, vendor, rate, unit, surcharge, notes, checked) in enumerate(rows, 1)]


def owner_rate_reference() -> dict:
    return {
        "reference_id": RATE_REFERENCE_ID, "received_date": "2026-08-17", "source": SOURCE,
        "status": "owner_provided_with_field_level_uncertainties",
        "labor_rates": [
            {"id": "labor_field_nonpw_2025", "description": "MWD Field Labor Cost / Rate", "category": "field", "base_rate": "68.53", "rate_basis": "total_burden_with_ot", "effective_date": "2025-01-01", "source": SOURCE, "status": "owner_provided"},
            {"id": "labor_field_pw_unavailable_2025", "description": "MWD Field Labor PW Cost / Rate", "category": "field_prevailing", "base_rate": None, "source_value": "#N/A", "effective_date": "2025-01-01", "source": SOURCE, "status": "unavailable_in_owner_source"},
            {"id": "labor_shop_2025", "description": "MWD Shop Labor Cost", "category": "shop", "base_rate": "38.85", "rate_basis": "total_burden_with_ot", "effective_date": "2025-01-01", "source": SOURCE, "status": "owner_provided"},
            {"id": "per_diem_owner_2025", "description": "Per Diem", "category": "travel", "base_rate": "120.00", "rate_basis": "per_diem", "effective_date": "2025-01-01", "source": SOURCE, "status": "owner_provided_pending_travel_policy"},
        ],
        "labor_burden_records": _burden_records(),
        "overhead_cost_factors": [
            {"id": "oh_health", "description": "Health Insurance", "value_add_rate": None, "value_add_amount": "1.75"},
            *[{"id": key, "description": name, "value_add_rate": rate, "value_add_amount": None} for key, name, rate in [
                ("oh_gl", "GL Insurance", "0.05"), ("oh_wc", "WC Insurance", "0.07"), ("oh_401k", "401k Match", "0.04"),
                ("oh_pto", "PTO", "0.0625"), ("oh_ss", "SS Tax", "0.062"), ("oh_medicare", "Medicare Tax", "0.0145"),
                ("oh_suta", "SUTA", "0.045"), ("oh_futa", "FUTA", "0.006"), ("oh_dwa", "DWA", "0.001"), ("oh_add_med", "Add Med", "0.009")]],
            {"id": "oh_total", "description": "TOTAL", "value_add_rate": "0.36", "value_add_amount": "1.75"},
        ],
        "wage_records": _wage_records(), "equipment_rates": _equipment_rates(), "material_rates": _material_rates(),
        "tax_rates": [{"id": "tax_mn_sherburne_owner", "name": "Minnesota + Sherburne County combined", "rate": "0.0738",
                       "effective_date": None, "last_checked": "2024-09-01", "source": "Owner table; cited sale-tax.com/Minnesota",
                       "status": "owner_provided_stale_check", "note": "Verify jurisdiction and current rate for each project before selection."}],
    }
