"""Authoritative, deterministic INF-4320 calculation services.

All currency calculations use Decimal.  Functions intentionally distinguish None
(blank/not supplied) from Decimal('0') (supplied zero).
"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

D = Decimal
WHOLE = D("1")


def dec(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None or value == "":
        return default
    return D(str(value))


def money(value: Decimal) -> Decimal:
    """Return an exact monetary calculation value without display rounding.

    The legacy name remains for API compatibility. Presentation code owns the
    decision to render a value to two decimal places.
    """
    return value


def project_abbreviation(name: str | None) -> str:
    if not name or not name.strip():
        return ""
    words = re.findall(r"[A-Za-z0-9]+", name.strip().upper())
    if words and re.fullmatch(r"\d{4}", words[0]):
        return words[0]
    ignored = {"THE", "OF", "AND", "A", "AN", "AT", "BY", "FOR", "IN", "ON", "TO"}
    significant = [w for w in words if w not in ignored]
    if not significant:
        return ""
    result = "".join(w[0] for w in significant[:4])
    if len(result) < 4:
        for char in significant[0][1:]:
            if len(result) == 4:
                break
            result += char
    return result[:4]


def normalize_code(code: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def split_variant(code: str) -> tuple[str | None, str]:
    normalized = code.strip().upper()
    match = re.match(r"^(ALT[1-4])[- :/]?(.*)$", normalized)
    return (match.group(1), match.group(2).strip()) if match else (None, normalized)


def map_cost_code(code: str, mappings: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Exact, normalized, then wildcard mapping, including confirmed exceptions."""
    _, base = split_variant(code)
    exceptions = {"006113": "0121", "015940": "LAF", "082000": "0880", "017113": "LAF", "024100": "LAF"}
    key = normalize_code(base)
    if key in exceptions:
        return {"mwd_code": exceptions[key], "match": "confirmed_exception"}
    for mode in ("exact", "normalized", "wildcard"):
        for row in mappings:
            source = str(row.get("csi_code", ""))
            matched = source == base if mode == "exact" else normalize_code(source) == key
            if mode == "wildcard" and "*" in source:
                matched = key.startswith(normalize_code(source.split("*")[0]))
            if matched:
                return {"mwd_code": row.get("mwd_code"), "description": row.get("mwd_description", ""), "match": mode}
    return None


def quote_cost(price: Any, surcharge_percent: Any = 0) -> Decimal | None:
    """Backward-compatible workbook surcharge calculation.

    New records use :func:`quote_adjustment`; this wrapper intentionally keeps the
    original two-argument contract for historical project documents and callers.
    """
    p = dec(price)
    if p is None:
        return None
    surcharge = dec(surcharge_percent, D(0)) or D(0)
    return money(p * (D(1) + surcharge))


def _adjustment_type(value: Any, *, default: str) -> str:
    normalized = str(value or default).strip().lower().replace("_", " ")
    if normalized in {"percentage", "percent", "%", "rate"}:
        return "percentage"
    if normalized in {"dollar", "dollars", "dollar amount", "amount", "$"}:
        return "dollar"
    raise ValueError("Quote adjustment type must be percentage or dollar.")


def quote_adjustment(
    price: Any,
    credit_type: Any = None,
    credit_value: Any = 0,
    surcharge_type: Any = None,
    surcharge_value: Any = 0,
    *,
    legacy_surcharge_percent: Any = None,
) -> dict[str, Decimal | str | None]:
    """Apply a quote credit before its surcharge and retain calculation lineage.

    Percentage values are stored as decimal rates (``0.05`` means five percent).
    Historical ``surcharge_percent`` values are accepted without changing their
    meaning. Returned values retain full Decimal precision.
    """
    base = dec(price)
    if base is None:
        return {
            "base_price": None, "credit_type": _adjustment_type(credit_type, default="dollar"),
            "credit_value": dec(credit_value, D(0)) or D(0), "credit_amount": None,
            "post_credit_subtotal": None,
            "surcharge_type": _adjustment_type(surcharge_type, default="percentage"),
            "surcharge_value": dec(surcharge_value, D(0)) or D(0),
            "surcharge_amount": None, "final_adjusted_value": None,
        }

    c_type = _adjustment_type(credit_type, default="dollar")
    c_value = dec(credit_value, D(0)) or D(0)
    if legacy_surcharge_percent is not None and surcharge_type in (None, ""):
        s_type, s_value = "percentage", dec(legacy_surcharge_percent, D(0)) or D(0)
    else:
        s_type = _adjustment_type(surcharge_type, default="percentage")
        s_value = dec(surcharge_value, D(0)) or D(0)
    if s_value < 0:
        raise ValueError("Quote surcharge cannot be negative; enter a reduction as a Credit.")

    credit_amount_raw = base * c_value if c_type == "percentage" else c_value
    post_credit_raw = base - credit_amount_raw
    surcharge_amount_raw = post_credit_raw * s_value if s_type == "percentage" else s_value
    final_raw = post_credit_raw + surcharge_amount_raw
    return {
        "base_price": money(base),
        "credit_type": c_type,
        "credit_value": c_value,
        "credit_amount": money(credit_amount_raw),
        "post_credit_subtotal": money(post_credit_raw),
        "surcharge_type": s_type,
        "surcharge_value": s_value,
        "surcharge_amount": money(surcharge_amount_raw),
        "final_adjusted_value": money(final_raw),
    }


def quote_unit_cost(cost: Any, square_feet: Any) -> Decimal | None:
    c, area = dec(cost), dec(square_feet)
    if c is None or area is None or area == 0:
        return None
    return money(c / area)


def taxed_cost(cost: Any, tax_rate: Any, *, taxable: bool, tax_included: bool = False) -> Decimal:
    c = dec(cost, D(0)) or D(0)
    return money(c if not taxable or tax_included else c * (D(1) + (dec(tax_rate, D(0)) or D(0))))


def frame_quantities(quantity: Any, width_inches: Any, height_inches: Any, caulking_passes: Any = None) -> dict[str, Decimal | None]:
    q, w, h = dec(quantity), dec(width_inches), dec(height_inches)
    if q is None or q == 0:
        return {"square_feet": None, "perimeter_lf": None, "caulking_passes": None if caulking_passes in (None, "") else dec(caulking_passes), "caulking_lf": None, "head_sill_qty": None}
    if any(v is None or v < 0 for v in (q, w, h)):
        raise ValueError("Quantity and dimensions must be nonnegative and dimensions are required for an active row.")
    passes = dec(caulking_passes, D(3))
    if passes is None or passes < 0:
        raise ValueError("Caulking passes must be nonnegative.")
    raw_area = w * h * q / D(144)
    raw_perimeter = D(2) * (w / D(12) + h / D(12)) * q
    return {
        "square_feet": raw_area,
        "perimeter_lf": raw_perimeter,
        "caulking_passes": passes,
        "caulking_lf": raw_perimeter * passes,
        "head_sill_qty": q * w / D(6),
    }


def installation_material(source_quantity: Any, factor: Any, rate: Any) -> Decimal | None:
    qty, r = dec(source_quantity), dec(rate)
    if qty is None or qty == 0 or r is None:
        return None
    f = dec(factor, D(1)) or D(0)
    return money(qty * f * r)


def equipment_extension(quantity: Any, duration: Any, rate: Any, delivery: Any = 0) -> Decimal | None:
    q, d, r = dec(quantity), dec(duration), dec(rate)
    delivery_cost = dec(delivery, D(0)) or D(0)
    if q is None or d is None or r is None:
        return None
    result = money(q * d * r + delivery_cost)
    return None if result == 0 else result


def borrowed_lite_area(quantity: Any, width_inches: Any, height_inches: Any) -> Decimal | None:
    q, w, h = dec(quantity), dec(width_inches), dec(height_inches)
    if q is None or q == 0:
        return None
    if any(v is None or v < 0 for v in (q, w, h)):
        raise ValueError("Borrowed-lite quantity and dimensions must be nonnegative.")
    return max(D(5), w / D(12) * h / D(12) * q)


def labor_hours(quantity: Any, crew: Any, productivity: Any, override: Any = None) -> Decimal | None:
    if override not in (None, ""):
        return dec(override)
    q, c, p = dec(quantity), dec(crew), dec(productivity)
    if q is None:
        return None
    if c is None or p is None or c <= 0 or p <= 0:
        return None
    return q / c / p


def labor_extension(hours: Any, rate: Any) -> Decimal | None:
    h, r = dec(hours), dec(rate)
    return None if h is None or r is None else money(h * r)


def effective_rate(controlled_rate: Any, override_rate: Any = None) -> dict[str, Decimal | bool | None]:
    """Resolve a project rate without ever mutating its controlled reference."""
    controlled = dec(controlled_rate)
    override = dec(override_rate) if override_rate not in (None, "") else None
    return {
        "controlled_rate": controlled,
        "rate_override": override,
        "effective_rate": override if override is not None else controlled,
        "is_override": override is not None,
    }


def _schedule_number(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.normalize(), "f")


def labor_schedule(
    man_hours: Any,
    crew_size: Any,
    hours_per_worker_per_day: Any,
    workdays_per_week: Any,
) -> dict[str, Decimal | str | None]:
    """Calculate schedule duration without changing labor cost or inventing nights."""
    hours = dec(man_hours)
    crew = dec(crew_size)
    hours_per_day = dec(hours_per_worker_per_day)
    days_per_week = dec(workdays_per_week)
    if hours is not None and hours < 0:
        raise ValueError("Man Hours must be nonnegative.")
    if crew is not None and crew < 0:
        raise ValueError("Crew Size must be nonnegative.")
    if hours_per_day is not None and (hours_per_day < 0 or hours_per_day > 24):
        raise ValueError("Hours per Worker per Day must be between 0 and 24.")
    if days_per_week is not None and (days_per_week < 0 or days_per_week > 7):
        raise ValueError("Workdays per Week must be between 0 and 7.")

    shift = None
    if hours_per_day is not None and days_per_week is not None:
        shift = f"{_schedule_number(days_per_week)}x{_schedule_number(hours_per_day)}"
    denominator = None if crew is None or hours_per_day is None else crew * hours_per_day
    working_days = None if hours is None or denominator is None or denominator == 0 else hours / denominator
    calendar_weeks = None if working_days is None or days_per_week in (None, D(0)) else working_days / days_per_week
    return {
        "man_hours": hours,
        "crew_size": crew,
        "hours_per_worker_per_day": hours_per_day,
        "workdays_per_week": days_per_week,
        "shift_configuration": shift,
        "working_days": working_days,
        "calendar_weeks": calendar_weeks,
        "calendar_days": None if calendar_weeks is None else calendar_weeks * D(7),
    }


def prevailing_wage(published_wage: Any, published_fringe: Any, classification_addition: Any = 0, credit_rate: Any = "0.1425") -> dict[str, Decimal]:
    wage = (dec(published_wage, D(0)) or D(0)) + (dec(classification_addition, D(0)) or D(0))
    fringe = dec(published_fringe, D(0)) or D(0)
    credit = wage * (dec(credit_rate, D("0.1425")) or D(0))
    return {"published_wage": wage, "published_fringe": fringe, "fringe_credit": credit, "usable_fringe": fringe - credit}


def escalated_rate(base: Any, escalation: Any = 0, override_enabled: bool = False, override: Any = None) -> Decimal | None:
    if override_enabled:
        return dec(override)
    b = dec(base)
    return None if b is None else b * (D(1) + (dec(escalation, D(0)) or D(0)))


def markup(cost: Any, rate: Any) -> dict[str, Decimal]:
    c, r = dec(cost, D(0)) or D(0), dec(rate, D(0)) or D(0)
    value = c * r
    return {"markup": money(value), "selling_value": money(c + value)}


def contingency(basis: Any, enabled: bool, rate: Any = "0.01", minimum: Any = "3000", override: Any = None) -> Decimal:
    if not enabled:
        return D(0)
    if override not in (None, ""):
        return money(dec(override, D(0)) or D(0))
    return money(max((dec(basis, D(0)) or D(0)) * (dec(rate, D("0.01")) or D(0)), dec(minimum, D("3000")) or D(0)))


def bond_amount(basis: Any, enabled: bool, bands: list[dict[str, Any]], override: Any = None) -> dict[str, Any]:
    """Apply an effective-dated six-band configuration.

    Each band supports min_exclusive/max_inclusive and either flat_amount or rate.
    INF-4320 confirms six bands but does not publish their numeric thresholds/rates;
    production defaults therefore leave bonding disabled pending owner confirmation.
    """
    b = dec(basis, D(0)) or D(0)
    if not enabled:
        return {"amount": D(0), "band": None}
    if override not in (None, ""):
        return {"amount": money(dec(override, D(0)) or D(0)), "band": "override"}
    for band in bands:
        low = dec(band.get("min_exclusive"), D("-1"))
        high = dec(band.get("max_inclusive"))
        if b > low and (high is None or b <= high):
            amount = dec(band.get("flat_amount"))
            if amount is None:
                amount = b * (dec(band.get("rate"), D(0)) or D(0))
            return {"amount": money(amount), "band": band.get("id")}
    raise ValueError("No configured bond band covers the basis amount.")


def sequential_pco(cost: Any, markup_one: Any, markup_two: Any, tax_rate: Any = 0, taxable: bool = False) -> dict[str, Decimal]:
    c = dec(cost, D(0)) or D(0)
    stage_one = c * (D(1) + (dec(markup_one, D(0)) or D(0)))
    stage_two = stage_one * (D(1) + (dec(markup_two, D(0)) or D(0)))
    price = stage_two * (D(1) + (dec(tax_rate, D(0)) or D(0))) if taxable else stage_two
    price = money(price)
    return {"cost": money(c), "stage_one": money(stage_one), "stage_two": money(stage_two), "customer_price": price, "margin": D(0) if price == 0 else (price - c) / price}


def sov_values(contract_allocation: Any, components: Iterable[Any]) -> dict[str, Decimal | str]:
    allocation = dec(contract_allocation, D(0)) or D(0)
    scheduled = money(sum((dec(v, D(0)) or D(0) for v in components), D(0)))
    remaining = money(allocation - scheduled)
    status = "exact" if remaining == 0 else ("underallocated" if remaining > 0 else "overallocated")
    return {"scheduled_value": scheduled, "allocation_percentage": D(0) if allocation == 0 else scheduled / allocation, "remaining_value": remaining, "status": status}


_ONES = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
_TENS = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]


def _under_thousand(n: int) -> str:
    parts: list[str] = []
    if n >= 100:
        parts += [_ONES[n // 100], "HUNDRED"]
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else ""))
    elif n:
        parts.append(_ONES[n])
    return " ".join(parts)


def dollars_in_words(value: Any) -> str:
    rounded = int((dec(value, D(0)) or D(0)).quantize(WHOLE, rounding=ROUND_HALF_UP))
    if rounded < 0 or rounded >= 1_000_000_000_000:
        raise ValueError("Proposal amount must be between zero and 999,999,999,999.")
    if rounded == 0:
        return "ZERO DOLLARS"
    parts: list[str] = []
    for divisor, label in ((1_000_000_000, "BILLION"), (1_000_000, "MILLION"), (1000, "THOUSAND"), (1, "")):
        chunk, rounded = divmod(rounded, divisor)
        if chunk:
            parts.append(_under_thousand(chunk) + (" " + label if label else ""))
    return " ".join(parts) + " DOLLARS"


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value
