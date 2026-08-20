"""Central presentation precision policy.

These settings never quantize calculation values. They describe only how a
semantic numeric category is rendered to a user.
"""
from __future__ import annotations

from typing import Any

MIN_DECIMAL_PLACES = 0
MAX_DECIMAL_PLACES = 6

DECIMAL_PRECISION_CATEGORIES = {
    "currency": {"label": "Dollar values", "description": "Totals, costs, selling values, credits, tax, and monetary deltas.", "default": 2},
    "currency_per_unit": {"label": "Currency per unit", "description": "$/SF, $/LF, and other cost or value rates per unit.", "default": 2},
    "percentage": {"label": "Percentages", "description": "Markup, margin, tax, and allocation percentages.", "default": 2},
    "quantity": {"label": "Quantities / units", "description": "Counts and general estimating quantities that may be fractional.", "default": 2},
    "dimension": {"label": "Dimensions", "description": "Editable width, height, and other dimensional measurements.", "default": 2},
    "square_footage": {"label": "Square footage", "description": "Frame, borrowed-lite, quote, and Bid area values.", "default": 2},
    "linear_footage": {"label": "Linear footage", "description": "Perimeter, caulking, head/sill, backpan, and other LF values.", "default": 2},
    "labor_hours": {"label": "Labor and crew hours", "description": "Man hours, working days, weeks, and crew-derived durations.", "default": 2},
    "rate": {"label": "Rates and unit costs", "description": "Labor, equipment, material, and production rates.", "default": 2},
    "multiplier": {"label": "Factors / multipliers", "description": "Material factors, productivity factors, and caulking passes.", "default": 2},
    "percentile": {"label": "Historical percentiles", "description": "Percentiles and other historical statistical positions.", "default": 2},
}


def default_decimal_precision() -> dict[str, int]:
    return {key: int(meta["default"]) for key, meta in DECIMAL_PRECISION_CATEGORIES.items()}


def validate_decimal_precision(value: Any) -> dict[str, int]:
    if value is None:
        return default_decimal_precision()
    if not isinstance(value, dict):
        raise ValueError("Decimal precision settings must be an object.")
    unknown = sorted(set(value) - set(DECIMAL_PRECISION_CATEGORIES))
    if unknown:
        raise ValueError(f"Unknown decimal precision categories: {', '.join(unknown)}.")
    result = default_decimal_precision()
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(f"{DECIMAL_PRECISION_CATEGORIES[key]['label']} precision must be a whole number.")
        if not MIN_DECIMAL_PLACES <= raw <= MAX_DECIMAL_PLACES:
            raise ValueError(f"{DECIMAL_PRECISION_CATEGORIES[key]['label']} precision must be between {MIN_DECIMAL_PLACES} and {MAX_DECIMAL_PLACES}.")
        result[key] = raw
    return result
