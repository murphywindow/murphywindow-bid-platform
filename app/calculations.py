"""Authoritative, deterministic INF-4320 calculation services.

All currency calculations use Decimal.  Functions intentionally distinguish None
(blank/not supplied) from Decimal('0') (supplied zero).
"""
from __future__ import annotations

import math
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

D = Decimal
CENT = D("0.01")
WHOLE = D("1")


def dec(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None or value == "":
        return default
    return D(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


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
    p = dec(price)
    if p is None:
        return None
    surcharge = dec(surcharge_percent, D(0)) or D(0)
    return money(p * (D(1) + surcharge))


def quote_unit_cost(cost: Any, square_feet: Any) -> Decimal | None:
    c, area = dec(cost), dec(square_feet)
    if c is None or area is None or area == 0:
        return None
    return money(c / area)


def taxed_cost(cost: Any, tax_rate: Any, *, taxable: bool, tax_included: bool = False) -> Decimal:
    c = dec(cost, D(0)) or D(0)
    return money(c if not taxable or tax_included else c * (D(1) + (dec(tax_rate, D(0)) or D(0))))


def _ceil(value: Decimal) -> Decimal:
    return D(math.ceil(value))


def frame_quantities(quantity: Any, width_inches: Any, height_inches: Any, caulking_passes: Any = None) -> dict[str, Decimal | None]:
    q, w, h = dec(quantity), dec(width_inches), dec(height_inches)
    if q is None or q == 0:
        return {"square_feet": None, "perimeter_lf": None, "caulking_passes": None if caulking_passes in (None, "") else dec(caulking_passes), "caulking_lf": None, "head_sill_qty": None}
    if any(v is None or v < 0 for v in (q, w, h)):
        raise ValueError("Quantity and dimensions must be nonnegative and dimensions are required for an active row.")
    passes = dec(caulking_passes, D(3))
    if passes is None or passes < 0:
        raise ValueError("Caulking passes must be nonnegative.")
    area = _ceil(w * h * q / D(144))
    perimeter = _ceil(D(2) * (w / D(12) + h / D(12)) * q)
    return {"square_feet": area, "perimeter_lf": perimeter, "caulking_passes": passes, "caulking_lf": _ceil(perimeter * passes), "head_sill_qty": _ceil(q * w / D(6))}


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
