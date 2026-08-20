import pytest

from app.numeric_precision import (
    DECIMAL_PRECISION_CATEGORIES,
    default_decimal_precision,
    validate_decimal_precision,
)


def test_precision_categories_are_complete_and_defaulted():
    settings = default_decimal_precision()
    assert settings.keys() == DECIMAL_PRECISION_CATEGORIES.keys()
    assert {"currency", "currency_per_unit", "percentage", "quantity", "dimension", "square_footage", "linear_footage", "labor_hours", "rate", "multiplier", "percentile"} <= settings.keys()
    assert all(value == 2 for value in settings.values())


def test_precision_validation_merges_defaults_and_rejects_invalid_values():
    configured = validate_decimal_precision({"currency": 0, "percentage": 3, "quantity": 1, "square_footage": 4})
    assert configured["currency"] == 0
    assert configured["percentage"] == 3
    assert configured["quantity"] == 1
    assert configured["square_footage"] == 4
    assert configured["linear_footage"] == 2
    for invalid in (-1, 7, 1.5, True, "2"):
        with pytest.raises(ValueError):
            validate_decimal_precision({"currency": invalid})
    with pytest.raises(ValueError):
        validate_decimal_precision({"unknown": 2})
