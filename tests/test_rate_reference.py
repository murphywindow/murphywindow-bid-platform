from decimal import Decimal

from app.generator import generate_test_project
from app.schema import CONFIG_VERSION, default_configuration


def test_owner_rate_tables_are_normalized_into_version_three_configuration():
    config = default_configuration()
    assert CONFIG_VERSION == "cfg-2026-08-19-v5" and config["version"] == 5
    assert config["rate_reference"]["reference_id"] == "owner-rate-tables-2026-08-17-v1"
    assert len(config["wage_records"]) == 87
    assert len(config["labor_burden_records"]) == 14
    assert len(config["overhead_cost_factors"]) == 12
    assert len(config["equipment_rates"]) == 22
    assert len(config["material_rates"]) == 17


def test_supplied_standard_rates_and_unavailable_pw_rate_are_preserved():
    config = default_configuration()
    rates = {row["id"]: row for row in config["labor_rates"]}
    assert rates["labor_field_nonpw_2025"]["base_rate"] == "68.53"
    assert rates["labor_shop_2025"]["base_rate"] == "38.85"
    assert rates["per_diem_owner_2025"]["base_rate"] == "120.00"
    assert rates["labor_field_pw_unavailable_2025"]["base_rate"] is None
    assert rates["labor_field_pw_unavailable_2025"]["source_value"] == "#N/A"


def test_county_rate_preserves_source_total_and_calculates_confirmed_fringe_credit():
    config = default_configuration()
    hennepin = next(row for row in config["wage_records"] if row["county"] == "Hennepin")
    assert hennepin["published_wage"] == "54.03"
    assert hennepin["published_fringe"] == "28.25"
    assert hennepin["published_total"] == "82.28"
    assert Decimal(hennepin["fringe_credit"]) == Decimal("54.03") * Decimal("0.1425")
    assert Decimal(hennepin["estimated_company_rate"]) == Decimal("54.03") + Decimal("28.25") - Decimal(hennepin["fringe_credit"])
    assert hennepin["classification"] is None and hennepin["effective_date"] is None
    assert "pending_classification_and_effective_date" in hennepin["status"]


def test_overhead_equipment_material_and_tax_source_values_are_preserved():
    config = default_configuration()
    factors = {row["id"]: row for row in config["overhead_cost_factors"]}
    assert factors["oh_total"]["value_add_rate"] == "0.36"
    assert factors["oh_health"]["value_add_amount"] == "1.75"
    boom = next(row for row in config["equipment_rates"] if row["description"] == "60’ Boom Lift")
    assert (boom["base_rate"], boom["rate_unit"], boom["delivery"]) == ("2055.00", "month", "250.00")
    backpan = next(row for row in config["material_rates"] if row["description"].startswith("Backpans for Behind"))
    assert backpan["base_rate"] == "48.32"
    assert "not an implemented rule" in backpan["notes"]
    tax = next(row for row in config["tax_rates"] if row["id"] == "tax_mn_sherburne_owner")
    assert tax["rate"] == "0.0738" and tax["last_checked"] == "2024-09-01"


def test_generated_projects_use_versioned_owner_rates_safely():
    config = default_configuration()
    documents = [generate_test_project(config, "Tester", "Estimator", seed) for seed in range(20)]
    public = next(doc for doc in documents if doc["project"]["prevailing_wage_required"])
    non_pw = next(doc for doc in documents if not doc["project"]["prevailing_wage_required"])

    selected = next(row for row in config["wage_records"] if row["id"] == public["project"]["wage_data_id"])
    assert {row["rate"] for row in public["labor_estimates"] if row["category"] == "field"} == {selected["estimated_company_rate"]}
    assert {row["rate"] for row in non_pw["labor_estimates"] if row["category"] == "field"} == {"68.53"}
    assert {row["rate"] for row in public["labor_estimates"] if row["category"] == "shop"} == {"38.85"}
    assert all(row["per_diem_rate"] == "120.00" and not row["enabled"] for row in public["travel_estimates"])
    assert all(row["rate_id"] and row["rate_version"] == CONFIG_VERSION for row in public["equipment"])
