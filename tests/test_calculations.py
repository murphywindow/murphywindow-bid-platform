from decimal import Decimal as D

import pytest

from app.calculations import (
    bond_amount, borrowed_lite_area, contingency, dollars_in_words,
    effective_rate, equipment_extension, escalated_rate, frame_quantities, installation_material,
    labor_extension, labor_hours, labor_schedule, map_cost_code, markup, prevailing_wage,
    project_abbreviation, quote_adjustment, quote_cost, quote_unit_cost, sequential_pco,
    sov_values, split_variant, taxed_cost,
)


@pytest.mark.parametrize("name,expected", [
    (None, ""), ("", ""), ("The City of Rogers Center", "CRCI"),
    ("North", "NORT"), ("A & B", "B"), ("2026 Civic Center", "2026"),
    ("St. Paul Public Safety Complex", "SPPS"),
])
def test_project_abbreviation(name, expected):
    assert project_abbreviation(name) == expected


def test_variant_and_confirmed_cost_code_exceptions():
    assert split_variant("ALT2-08 20 00") == ("ALT2", "08 20 00")
    assert map_cost_code("ALT2-08 20 00", []) == {"mwd_code": "0880", "match": "confirmed_exception"}
    assert map_cost_code("01 59 40", [])["mwd_code"] == "LAF"


def test_quote_surcharge_unit_cost_and_blank_behavior():
    assert quote_cost("1000", "0.05") == D("1050.00")
    assert quote_cost(None, "0.05") is None
    assert quote_unit_cost("1050", "100") == D("10.50")
    assert quote_unit_cost("1050", 0) is None


def test_quote_credit_is_applied_before_surcharge_with_named_lineage():
    result = quote_adjustment("1000", "percentage", ".10", "percentage", ".10")
    assert result == {
        "base_price": D("1000.00"), "credit_type": "percentage", "credit_value": D(".10"),
        "credit_amount": D("100.00"), "post_credit_subtotal": D("900.00"),
        "surcharge_type": "percentage", "surcharge_value": D(".10"),
        "surcharge_amount": D("90.00"), "final_adjusted_value": D("990.00"),
    }
    dollars = quote_adjustment("1000", "dollar", "125", "dollar", "25")
    assert dollars["credit_amount"] == D("125.00")
    assert dollars["post_credit_subtotal"] == D("875.00")
    assert dollars["surcharge_amount"] == D("25.00")
    assert dollars["final_adjusted_value"] == D("900.00")
    with pytest.raises(ValueError, match="negative"):
        quote_adjustment("1000", "dollar", 0, "dollar", -1)


def test_quote_adjustment_preserves_legacy_percent_and_blank_price():
    legacy = quote_adjustment("1000", legacy_surcharge_percent=".05")
    assert legacy["final_adjusted_value"] == D("1050.00")
    blank = quote_adjustment(None, "dollar", "10", "percentage", ".05")
    assert blank["final_adjusted_value"] is None
    assert blank["credit_value"] == D("10")


def test_taxable_exempt_and_tax_included():
    assert taxed_cost(100, ".0875", taxable=True) == D("108.75")
    assert taxed_cost(100, ".0875", taxable=True, tax_included=True) == D("100.00")
    assert taxed_cost(100, ".0875", taxable=False) == D("100.00")


def test_frame_dimension_conversions_and_boundaries():
    q = frame_quantities(1, 12, 12)
    assert q == {"square_feet": D(1), "perimeter_lf": D(4), "caulking_passes": D(3), "caulking_lf": D(12), "head_sill_qty": D(2)}
    q = frame_quantities(2, 35.5, 71.25, 4)
    assert q["square_feet"] == D("35.5") * D("71.25") * D(2) / D(144)
    assert q["perimeter_lf"] == D(2) * (D("35.5") / D(12) + D("71.25") / D(12)) * D(2)
    assert q["caulking_lf"] == q["perimeter_lf"] * D(4)
    assert q["head_sill_qty"] == D(2) * D("35.5") / D(6)
    assert frame_quantities(None, 12, 12)["square_feet"] is None
    assert frame_quantities(0, 12, 12)["square_feet"] is None
    with pytest.raises(ValueError):
        frame_quantities(1, -1, 12)


def test_fractional_caulking_passes_preserve_fractional_linear_feet():
    quantities = frame_quantities(1, 12, 12, "3.11")
    assert quantities["perimeter_lf"] == D("4.00")
    assert quantities["caulking_passes"] == D("3.11")
    assert quantities["caulking_lf"] == D("12.44")


def test_calculations_preserve_precision_across_chained_costs():
    quantities = frame_quantities("3.7", "11.11", "22.22", "3.11")
    expected_perimeter = D(2) * (D("11.11") / D(12) + D("22.22") / D(12)) * D("3.7")
    assert quantities["perimeter_lf"] == expected_perimeter
    assert quantities["caulking_lf"] == expected_perimeter * D("3.11")
    material = installation_material(quantities["caulking_lf"], "0.137", "12.34567")
    assert material == expected_perimeter * D("3.11") * D("0.137") * D("12.34567")
    marked_up = markup(material, "0.1739")
    assert marked_up["markup"] == material * D("0.1739")
    assert marked_up["selling_value"] == material + material * D("0.1739")


def test_installation_material_defaults_and_missing():
    assert installation_material(100, ".08", 12) == D("96.00")
    assert installation_material(None, 1, 12) is None
    assert installation_material(0, 1, 12) is None


def test_equipment_extension_blank_zero_delivery_and_multiple_units():
    assert equipment_extension(2, 3, 100, 50) == D("650.00")
    assert equipment_extension(2, 3, 100, 0) == D("600.00")
    assert equipment_extension(0, 0, 0, 0) is None
    assert equipment_extension(None, 3, 100, 50) is None
    assert equipment_extension(0, 3, 100, 50) == D("50.00")


@pytest.mark.parametrize("q,w,h,expected", [(1, 12, 12, D(5)), (1, 12, 60, D(5)), (1, 24, 36, D(6)), (2, 12, 36, D(6))])
def test_borrowed_lite_five_square_foot_row_minimum(q, w, h, expected):
    assert borrowed_lite_area(q, w, h) == expected


def test_labor_productivity_override_extension_and_missing_rate():
    assert labor_hours(100, 2, 5) == D(10)
    assert labor_hours(100, 2, 5, 12) == D(12)
    assert labor_hours(100, 0, 5) is None
    assert labor_extension(10, 75) == D("750.00")
    assert labor_extension(10, None) is None


def test_effective_labor_rate_and_schedule_are_independent_of_cost_hours():
    rate = effective_rate("68.53", "75")
    assert rate == {
        "controlled_rate": D("68.53"), "rate_override": D("75"),
        "effective_rate": D("75"), "is_override": True,
    }
    schedule = labor_schedule("8", "2", "8", "5")
    assert schedule["shift_configuration"] == "5x8"
    assert schedule["working_days"] == D(".5")
    assert schedule["calendar_weeks"] == D(".1")
    assert schedule["calendar_days"] == D(".7")
    assert labor_extension(schedule["man_hours"], rate["effective_rate"]) == D("600.00")


def test_labor_schedule_bounds_and_blank_or_zero_denominators_are_safe():
    assert labor_schedule("8", 0, "8", "5")["working_days"] is None
    assert labor_schedule("8", None, None, None)["calendar_days"] is None
    with pytest.raises(ValueError, match="between 0 and 24"):
        labor_schedule("8", 2, "24.01", 5)
    with pytest.raises(ValueError, match="between 0 and 7"):
        labor_schedule("8", 2, 8, "7.01")


def test_prevailing_wage_fringe_credit_and_escalation_override():
    result = prevailing_wage(50, 20)
    assert result["fringe_credit"] == D("7.1250")
    assert result["usable_fringe"] == D("12.8750")
    assert prevailing_wage(50, 20, 2)["published_wage"] == D(52)
    assert escalated_rate(100, ".10") == D(110)
    assert escalated_rate(100, ".10", True, 95) == D(95)


def test_separate_markup_types_and_negative_cost():
    assert markup(100, ".2") == {"markup": D("20.00"), "selling_value": D("120.00")}
    assert markup(-100, ".2") == {"markup": D("-20.00"), "selling_value": D("-120.00")}


def test_contingency_floor_percentage_disabled_and_override():
    assert contingency(100_000, True) == D("3000.00")
    assert contingency(400_000, True) == D("4000.00")
    assert contingency(400_000, False) == 0
    assert contingency(400_000, True, override="1234.56") == D("1234.56")


SIX_BANDS = [
    {"id": f"b{i}", "min_exclusive": str(-1 if i == 1 else (i-1)*100), "max_inclusive": str(i*100) if i < 6 else None, "flat_amount": str(i*10)}
    for i in range(1, 7)
]


@pytest.mark.parametrize("value,band,amount", [
    (0, "b1", "10.00"), (99, "b1", "10.00"), (100, "b1", "10.00"), (101, "b2", "20.00"),
    (199, "b2", "20.00"), (200, "b2", "20.00"), (201, "b3", "30.00"), (299, "b3", "30.00"),
    (300, "b3", "30.00"), (301, "b4", "40.00"), (399, "b4", "40.00"), (400, "b4", "40.00"),
    (401, "b5", "50.00"), (499, "b5", "50.00"), (500, "b5", "50.00"), (501, "b6", "60.00"),
])
def test_every_bond_band_boundaries(value, band, amount):
    result = bond_amount(value, True, SIX_BANDS)
    assert result == {"amount": D(amount), "band": band}


def test_bond_disabled_override_and_missing_band():
    assert bond_amount(100, False, SIX_BANDS)["amount"] == 0
    assert bond_amount(100, True, SIX_BANDS, 77)["amount"] == D("77.00")
    with pytest.raises(ValueError):
        bond_amount(-5, True, SIX_BANDS)


def test_pco_markup_is_sequential_not_additive_and_taxable():
    result = sequential_pco(100, ".10", ".20")
    assert result["stage_one"] == D("110.00")
    assert result["stage_two"] == D("132.00")
    assert result["customer_price"] != D("130.00")
    taxed = sequential_pco(100, ".10", ".20", ".05", True)
    assert taxed["customer_price"] == D("138.60")


@pytest.mark.parametrize("components,status,remaining", [([20, 30], "underallocated", "50.00"), ([40, 60], "exact", "0.00"), ([60, 50], "overallocated", "-10.00")])
def test_sov_under_exact_overallocation(components, status, remaining):
    result = sov_values(100, components)
    assert result["status"] == status
    assert result["remaining_value"] == D(remaining)


@pytest.mark.parametrize("value,words", [(0,"ZERO DOLLARS"),(100,"ONE HUNDRED DOLLARS"),(999.49,"NINE HUNDRED NINETY-NINE DOLLARS"),(999.5,"ONE THOUSAND DOLLARS"),(1_000_001,"ONE MILLION ONE DOLLARS")])
def test_written_dollars(value, words):
    assert dollars_in_words(value) == words


def test_pssc_golden_output_fixture_reconciles_documented_metrics():
    # INF-4320 publishes outputs but not the source rows or numeric bond bands.
    golden = {"direct_cost": D("4586371"), "markup_profit": D("898992.79"), "bid": D("5485367"), "margin": D("0.163889"), "area": D("61195"), "price_per_sf": D("89.64")}
    assert golden["bid"].quantize(D("1")) == D("5485367")
    assert (golden["bid"] and golden["markup_profit"] / golden["bid"]).quantize(D("0.000001")) == golden["margin"]
    assert (golden["bid"] / golden["area"]).quantize(D("0.01")) == golden["price_per_sf"]
    assert golden["bid"] != D("5485822")
