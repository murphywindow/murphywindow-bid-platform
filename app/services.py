"""Domain services: authorization, bid assembly, revisions, and lifecycle."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from typing import Any

from .calculations import (
    bond_amount, borrowed_lite_area, contingency, dec, dollars_in_words,
    effective_rate, equipment_extension, frame_quantities, installation_material, installation_material_quantity, jsonable,
    labor_extension, labor_hours, labor_schedule, map_cost_code, markup, normalize_code,
    project_abbreviation, quote_adjustment, quote_unit_cost, sequential_pco, sov_values,
    split_variant, taxed_cost,
)
from .historical import BID_COST_CODE_SELL_PER_SF_METRIC
from .alternates import calculate_alternates
from .schema import CONTRACT_TYPES, INTERCHANGE_VERSION, PROJECT_TYPES, WAGE_TYPES, now, uid


ROLES = ("Estimator", "General Manager", "President", "Project Manager", "Support", "Systems Administrator")
ADMINISTRATOR_ROLE = "Systems Administrator"
PERMISSIONS = {
    "edit_estimate": {"Estimator"},
    "review": {"Estimator", "General Manager", "President"},
    "submit": {"Estimator"},
    "activate": {"Project Manager", "Support"},
    "contract": {"Project Manager"},
    "change_order": {"Project Manager"},
    "view_restricted_pco": {"General Manager", "President", "Project Manager"},
    "sov": {"Project Manager", "Support"},
    "closeout": {"Project Manager"},
    "configuration": {"Systems Administrator"},
    "archive": {"Estimator", "Project Manager", "Systems Administrator"},
    "export": set(ROLES),
}


class DomainError(ValueError):
    def __init__(self, message: str, code: str = "validation_error", details: list[dict] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or []


def require(role: str, permission: str) -> None:
    # Systems Administrators are the global permission authority.  Domain
    # invariants (immutable snapshots, required evidence, calculated-field
    # locks, and confirmation workflows) are enforced separately and still
    # apply; this bypass concerns role authorization only.
    if role == ADMINISTRATOR_ROLE:
        return
    if role not in PERMISSIONS.get(permission, set()):
        raise DomainError(f"{role} is not authorized to {permission.replace('_', ' ')}.", "forbidden")


def audit(doc: dict, actor: str, role: str, entity_type: str, entity_id: str, operation: str,
          prior: Any, new: Any, reason: str, correlation_id: str | None = None) -> None:
    doc.setdefault("audit_events", []).append({
        "id": uid("aud"), "timestamp": now(), "actor": actor, "role": role,
        "entity_type": entity_type, "entity_id": entity_id, "operation": operation,
        "prior_value": prior, "new_value": new, "reason": reason,
        "correlation_id": correlation_id or uid("cor")
    })


def bump_bid_version(doc: dict, event: str, level: str = "patch", amount: int = 1) -> dict:
    """Bid-semantic version: submission=minor, activation=major, recorded change=patch."""
    version = doc["project"].setdefault("bid_version", {"major": 0, "minor": 0, "patch": 0, "sequence": 0})
    if level == "major":
        version["major"] = int(version.get("major", 0)) + 1
        version["minor"] = 0; version["patch"] = 0
    elif level == "minor":
        version["minor"] = int(version.get("minor", 0)) + 1
        version["patch"] = 0
    else:
        amount = max(1, int(amount))
        version["patch"] = int(version.get("patch", 0)) + amount
    version["sequence"] = int(version.get("sequence", 0)) + (amount if level == "patch" else 1)
    version["display"] = f"B{version['major']}.{version['minor']}.{version['patch']}"
    version["last_event"] = event
    version["recorded_at"] = now()
    return version


def ensure_ids(doc: dict) -> None:
    collections = {
        "contacts": "con", "cost_codes": "ccd", "quotes": "quo", "takeoff_sections": "sec", "doors": "dor",
        "hardware_assignments": "hwa", "equipment": "eqp", "borrowed_lites": "brl", "labor_estimates": "lbr",
        "travel_estimates": "trv", "alternates": "alt", "bid_tabulations": "tab"
    }
    for key, prefix in collections.items():
        for item in doc.setdefault(key, []):
            item.setdefault("id", uid(prefix))
            if key == "takeoff_sections":
                item.setdefault("definition_id", "frame-v1")
                for line in item.setdefault("lines", []):
                    line.setdefault("id", uid("frm"))


def _cost_code(doc: dict, full_code: str) -> dict:
    _, base = split_variant(full_code)
    target = "".join(c for c in base.upper() if c.isalnum())
    for code in doc.get("cost_codes", []):
        if "".join(c for c in str(code.get("code", "")).upper() if c.isalnum()) == target:
            return code
    return {"code": base, "description": base, "deduct": False, "mwd_code": None}


def _sign(doc: dict, code: str) -> Decimal:
    return Decimal("-1") if _cost_code(doc, code).get("deduct") else Decimal("1")


def _active(doc: dict, code: str) -> bool:
    variant, _ = split_variant(code)
    return variant is None


def _stable_line_id(item: dict) -> str:
    sources = []
    for lineage in item.get("lineage", []):
        sources.append(lineage.get("source_id") or lineage.get("source_ids") or lineage.get("material_rule_id") or lineage.get("source_type"))
    key = json.dumps([item.get("code"), item.get("category"), item.get("description"), sources], sort_keys=True)
    return "est_" + hashlib.sha256(key.encode()).hexdigest()[:24]


def _tax(doc: dict, config: dict) -> tuple[bool, Decimal]:
    taxable = not bool(doc["project"].get("tax_exempt"))
    tax_id = doc["project"].get("tax_rate_id")
    row = next((x for x in config.get("tax_rates", []) if x.get("id") == tax_id), None)
    return taxable, dec(row.get("rate"), Decimal(0)) if row else Decimal(0)


def _full_code_key(code: Any) -> str:
    variant, base = split_variant(str(code or ""))
    normalized = normalize_code(base)
    return f"{variant}:{normalized}" if variant else normalized


def _display_code(code: Any) -> str:
    return str(code or "").strip().upper()


def _warning(code: str, entity_id: Any, message: str, *, blocking: bool = False,
             acknowledged: bool = False, **extra: Any) -> dict:
    return {
        "code": code, "entity_id": entity_id, "message": message,
        "blocking": bool(blocking), "acknowledged": bool(acknowledged), **extra,
    }


def _meaningful(row: dict, ignored: set[str]) -> bool:
    for key, value in row.items():
        if key in ignored or key.startswith("calculated"):
            continue
        if value not in (None, "", [], {}, False):
            return True
    return False


def _frame_row_meaningful(row: dict) -> bool:
    return _meaningful(row, {
        "id", "quantity", "caulking_passes", "installation_material_ids", "calculated",
        "missing_quantity_acknowledged", "missing_quantity_acknowledged_at",
        "missing_quantity_acknowledged_by", "acknowledged_at", "acknowledged_by",
    })


def _frame_dimensions_started(row: dict) -> bool:
    return any(row.get(key) not in (None, "") for key in ("width_inches", "height_inches"))


def _door_row_meaningful(row: dict) -> bool:
    return _meaningful(row, {
        "id", "quantity", "leaf_quantity", "calculated",
        "missing_quantity_acknowledged", "missing_quantity_acknowledged_at",
        "missing_quantity_acknowledged_by", "acknowledged_at", "acknowledged_by",
    })


def _selection_entry(selection_map: dict, code: str) -> tuple[str, dict | None]:
    target = _full_code_key(code)
    for key, value in selection_map.items():
        if _full_code_key(key) == target:
            if isinstance(value, str):
                return key, {"mode": value, "selected_quote_ids": []}
            return key, value
    return code, None


def select_used_quotes(doc: dict) -> dict[str, list[dict]]:
    """Apply implicit cost-code quote grouping and automatic/manual Used behavior."""
    groups: dict[str, list[dict]] = {}
    for quote in doc.get("quotes", []):
        if quote.get("code"):
            groups.setdefault(_full_code_key(quote.get("code")), []).append(quote)
    estimate = doc.setdefault("working_estimate", {})
    selection_map = estimate.setdefault("quote_selection_by_code", {})
    for rows in groups.values():
        display = _display_code(rows[0].get("code"))
        stored_key, entry = _selection_entry(selection_map, display)
        if entry is None:
            selected = [row["id"] for row in rows if row.get("used")]
            entry = {
                "mode": "legacy_manual" if selected else "automatic",
                "selected_quote_ids": selected,
            }
            selection_map[display] = entry
        elif stored_key != display and stored_key in selection_map:
            # Preserve the migration/UI key; comparisons remain normalized.
            display = stored_key
        if selection_map.get(display) is not entry:
            # Normalize a supported legacy string entry into the canonical
            # structured selection record so there is one live source of truth.
            selection_map[display] = entry
        mode = str(entry.get("mode") or "automatic").lower()
        if mode == "automatic":
            candidates = [row for row in rows if dec(row.get("calculated_cost")) is not None]
            selected_ids = []
            if candidates:
                selected_ids = [min(candidates, key=lambda row: (dec(row.get("calculated_cost")) or Decimal(0), row.get("id", "")))["id"]]
            entry["selected_quote_ids"] = selected_ids
        else:
            selected_ids = list(entry.get("selected_quote_ids") or [row["id"] for row in rows if row.get("used")])
            entry["selected_quote_ids"] = selected_ids
        selected_set = set(selected_ids)
        for row in rows:
            row["used"] = row.get("id") in selected_set
            row["used_selection_mode"] = entry.get("mode")
    return groups


def _source_codes(doc: dict) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def add(code: Any, source_type: str, source_id: Any) -> None:
        if not str(code or "").strip():
            return
        key = _full_code_key(code)
        item = result.setdefault(key, {"code": _display_code(code), "source_links": []})
        link = {"source_type": source_type, "source_id": source_id}
        if link not in item["source_links"]:
            item["source_links"].append(link)

    for row in doc.get("quotes", []):
        add(row.get("code"), "quote", row.get("id"))
    for row in doc.get("takeoff_sections", []):
        add(row.get("code"), "frame", row.get("id"))
    for row in doc.get("doors", []):
        add(row.get("code"), "door", row.get("id"))
    doors_by_id = {row.get("id"): row for row in doc.get("doors", []) if row.get("id")}
    for row in doc.get("hardware_assignments", []):
        linked_door = doors_by_id.get(row.get("door_id"), {})
        add(row.get("code") or linked_door.get("code"), "door_hardware", row.get("id"))
    for row in doc.get("equipment", []):
        add(row.get("code"), "equipment", row.get("id"))
    for row in doc.get("borrowed_lites", []):
        add(row.get("code"), "borrowed_lite", row.get("id"))
    return result


def _excluded_labor_codes(doc: dict) -> set[str]:
    values = doc.setdefault("working_estimate", {}).setdefault("labor_suggestion_exclusions", [])
    result = set()
    for value in values:
        code = value.get("code") if isinstance(value, dict) else value
        if code:
            result.add(_full_code_key(code))
    return result


def _controlled_labor_snapshot(doc: dict, config: dict, row: dict, labor_type: str) -> dict:
    existing = row.get("controlled_rate_snapshot")
    # A populated project snapshot is immutable lineage.  An unavailable
    # ``rate: None`` placeholder may be resolved later when the estimator makes
    # the missing controlled project/rate selection; never wrap that placeholder
    # inside another snapshot.
    if isinstance(existing, dict) and existing.get("rate") not in (None, ""):
        return deepcopy(existing)
    if existing not in (None, "", {}) and not isinstance(existing, dict):
        return {"rate": existing, "rate_id": row.get("rate_id"), "configuration_id": config.get("id"), "source": "project_snapshot", "status": "preserved"}

    wage_type = str(doc.get("project", {}).get("wage_type") or "").upper()
    rate_id = row.get("controlled_rate_id") or row.get("rate_id")
    if labor_type == "Field" and wage_type == "PW":
        wage_id = doc.get("project", {}).get("wage_data_id")
        wage = next((item for item in config.get("wage_records", []) if item.get("id") == wage_id), None)
        if wage and wage.get("estimated_company_rate") not in (None, ""):
            return {"rate": wage.get("estimated_company_rate"), "rate_id": wage.get("id"), "configuration_id": config.get("id"), "source": wage.get("source"), "status": wage.get("status")}
        return {"rate": None, "rate_id": wage_id or rate_id, "configuration_id": config.get("id"), "source": None, "status": "unavailable_prevailing_wage_record"}

    rates = config.get("labor_rates", [])
    record = next((item for item in rates if item.get("id") == rate_id), None)
    if record is None:
        category = {"Field": "field", "Shop": "shop", "Design": "design"}.get(labor_type)
        candidates = [item for item in rates if item.get("category") == category]
        if labor_type == "Field" and wage_type in {"", "NON-PW"}:
            candidates = [item for item in rates if item.get("category") == "field" and not item.get("prevailing_wage")]
        record = next((item for item in candidates if item.get("base_rate") not in (None, "")), None)
    if record:
        return {"rate": record.get("base_rate"), "rate_id": record.get("id"), "configuration_id": config.get("id"), "source": record.get("source"), "status": record.get("status")}
    return {"rate": None, "rate_id": rate_id, "configuration_id": config.get("id"), "source": None, "status": "unavailable"}


def sync_labor_candidates(doc: dict, config: dict) -> list[dict]:
    """Maintain one source-linked Labor candidate per unique active source code."""
    sources = _source_codes(doc)
    excluded = _excluded_labor_codes(doc)
    rows = doc.setdefault("labor_estimates", [])
    by_code: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("code"):
            by_code.setdefault(_full_code_key(row.get("code")), []).append(row)
    created: list[dict] = []
    for key, source in sources.items():
        existing = by_code.get(key, [])
        if not existing and key not in excluded:
            candidate = {
                "id": uid("lbr"), "code": source["code"], "description": "",
                "labor_type": "Field", "category": "field", "man_hours": None,
                "man_hours_source": "unassigned", "crew_size": None,
                "hours_per_worker_per_day": None, "workdays_per_week": None,
                "controlled_rate_snapshot": None, "rate_override": None,
                "rate_override_reason": None, "origin": "automatic",
                "source_links": deepcopy(source["source_links"]), "source_status": "active",
                "stale_acknowledged": False, "notes": "",
            }
            candidate["controlled_rate_snapshot"] = _controlled_labor_snapshot(doc, config, candidate, "Field")
            rows.append(candidate)
            by_code[key] = [candidate]
            created.append(candidate)
        else:
            for row in existing:
                if row.get("origin") == "automatic" or row.get("source_links"):
                    row["source_links"] = deepcopy(source["source_links"])
                    row["source_status"] = "active"
    for key, existing in by_code.items():
        if key not in sources:
            for row in existing:
                if row.get("origin") == "automatic" or row.get("source_links"):
                    row["source_status"] = "stale"
    return created


def submission_blockers(doc: dict) -> list[dict]:
    return [item for item in doc.get("working_estimate", {}).get("validation", []) if item.get("blocking")]


def calculate_project(doc: dict, config: dict, *, include_alternates: bool = True) -> dict:
    """Build normalized estimate lines and traceable totals from stored raw inputs."""
    ensure_ids(doc)
    doc["project"]["abbreviation"] = project_abbreviation(doc["project"].get("name"))
    taxable, tax_rate = _tax(doc, config)
    raw: list[dict] = []
    warnings: list[dict] = []

    project = doc.get("project", {})
    for field, status_field, allowed in (
        ("project_type", "project_type_status", PROJECT_TYPES),
        ("contract_type", "contract_type_status", CONTRACT_TYPES),
        ("wage_type", "wage_type_status", WAGE_TYPES),
    ):
        value = project.get(field)
        status = project.get(status_field)
        if value not in allowed or status in {"missing", "legacy_unsupported", "invalid"}:
            warnings.append(_warning(
                f"invalid_{field}", project.get("id"),
                f"{field.replace('_', ' ').title()} must be deliberately selected from the current controlled values before submission.",
                blocking=True, entity_type="project", field=field, value=value,
                allowed_values=list(allowed), controlled_status=status,
            ))
    if project.get("wage_type") == "PW" and not project.get("wage_data_id"):
        warnings.append(_warning(
            "missing_prevailing_wage_record", project.get("id"),
            "A PW project requires an explicit controlled prevailing-wage record before submission.",
            blocking=True, entity_type="project", field="wage_data_id",
        ))
    for index, issue in enumerate(doc.setdefault("working_estimate", {}).get("pending_controlled_values", [])):
        issue = issue if isinstance(issue, dict) else {"entered_value": issue}
        warnings.append(_warning(
            "pending_controlled_value", issue.get("row_id") or f"pending-{index}",
            issue.get("message") or "A pasted controlled value remains unresolved.",
            blocking=True, entity_type=issue.get("table_id") or "controlled_value",
            table_id=issue.get("table_id"), field=issue.get("field"),
            entered_value=issue.get("entered_value"),
        ))

    references = {row.get("normalized_code"): row for row in config.get("csi_references", [])}
    for code in doc.get("cost_codes", []):
        _, base = split_variant(code.get("code", ""))
        reference = references.get(normalize_code(base)) if references else None
        is_custom = bool(code.get("custom") or code.get("is_custom") or code.get("custom_code"))
        if references and reference is None and not is_custom:
            warnings.append(_warning(
                "invalid_cost_code", code.get("id"),
                f"Cost code {code.get('code')!r} is not in owner reference {config.get('cost_code_reference', {}).get('reference_id')}. The entered value is preserved for correction.",
                blocking=True,
            ))
        elif reference and not code.get("description"):
            code["description"] = reference.get("description", "")
            code["reference_id"] = reference.get("id")
        mapped = map_cost_code(code.get("code", ""), config.get("cost_code_mappings", []))
        if mapped and not code.get("mwd_code"):
            code["mwd_code"] = mapped.get("mwd_code")
            code["mwd_description"] = mapped.get("description", "")

    project_code_keys = {
        normalize_code(split_variant(str(row.get("code") or ""))[1])
        for row in doc.get("cost_codes", []) if row.get("code")
    }
    for collection in (
        "quotes", "takeoff_sections", "doors", "hardware_assignments", "equipment",
        "borrowed_lites", "labor_estimates", "travel_estimates",
    ):
        for row in doc.get(collection, []):
            code = row.get("code") or row.get("cost_code")
            if code and normalize_code(split_variant(str(code))[1]) not in project_code_keys:
                warnings.append(_warning(
                    "invalid_source_cost_code", row.get("id"),
                    f"{collection.replace('_', ' ').title()} references Cost Code {code!r}, which is not present in project Cost Codes.",
                    blocking=True, entity_type=collection.rstrip("s"),
                ))

    # Frame rows and per-section installation material.
    frame_area_by_code: dict[str, Decimal] = {}
    code_display: dict[str, str] = {}
    for section in doc.get("takeoff_sections", []):
        code = section.get("code", "")
        code_key = _full_code_key(code)
        if code_key:
            code_display.setdefault(code_key, _display_code(code))
        totals = {"quantity": Decimal(0), "square_feet": Decimal(0), "perimeter_lf": Decimal(0), "caulking_lf": Decimal(0), "head_sill_qty": Decimal(0)}
        for row in section.get("lines", []):
            quantity = dec(row.get("quantity"))
            dimensions_started = _frame_dimensions_started(row)
            if dimensions_started and quantity in (None, Decimal(0)):
                acknowledged = bool(row.get("missing_quantity_acknowledged"))
                warnings.append(_warning(
                    "missing_frame_quantity", row.get("id"),
                    "Frame row contains takeoff information but Quantity is blank or zero."
                    + (" The estimator acknowledged this line-level exception." if acknowledged else ""),
                    blocking=not acknowledged, acknowledged=acknowledged,
                    entity_type="frame_line", section_id=section.get("id"),
                ))
            try:
                q = frame_quantities(row.get("quantity"), row.get("width_inches"), row.get("height_inches"), row.get("caulking_passes"))
                row["calculated"] = jsonable(q)
                if q["perimeter_lf"] is not None and row.get("caulking_passes") in (None, ""):
                    row["caulking_passes"] = jsonable(q["caulking_passes"])
                if q["square_feet"] is not None:
                    totals["quantity"] += dec(row.get("quantity"), Decimal(0)) or Decimal(0)
                    for key in ("square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty"):
                        totals[key] += q[key] or Decimal(0)
            except ValueError as exc:
                warnings.append(_warning("invalid_frame_row", row["id"], str(exc), blocking=True, entity_type="frame_line", section_id=section.get("id")))
        section["totals"] = jsonable(totals)
        if code_key:
            frame_area_by_code[code_key] = frame_area_by_code.get(code_key, Decimal(0)) + totals["square_feet"]
        material_results = []
        excluded_material_rule_ids = {str(value) for value in section.get("excluded_material_rule_ids", [])}
        section_material_rules = [deepcopy(rule) for rule in config.get("material_rules", [])
                                  if str(rule.get("id")) not in excluded_material_rule_ids]
        controlled_rules = {str(rule.get("id")): rule for rule in config.get("material_rules", [])}
        controlled_rates = {str(rule.get("id")): rule for rule in config.get("material_rates", [])}
        for custom in section.get("additional_materials", []):
            rule = deepcopy(custom)
            reference_id = str(rule.get("controlled_rate_id") or "")
            reference = controlled_rules.get(reference_id) or controlled_rates.get(reference_id)
            if reference:
                rule.setdefault("name", reference.get("name") or reference.get("description"))
                rule.setdefault("factor", reference.get("factor"))
                rule.setdefault("unit", reference.get("unit") or reference.get("rate_unit"))
                rule.setdefault("material_code", reference.get("material_code") or reference.get("code") or "PROJECT")
                rule["rate"] = reference.get("rate", reference.get("base_rate"))
                rule["controlled_reference_status"] = "controlled"
            else:
                rule["rate"] = None
                rule["controlled_reference_status"] = "project_specific"
            rule.setdefault("source", "manual_quantity")
            rule.setdefault("factor", "1")
            rule.setdefault("unit", "each")
            rule.setdefault("material_code", "PROJECT")
            rule.setdefault("taxable", True)
            rule["project_specific"] = True
            section_material_rules.append(rule)
        for rule in section_material_rules:
            override = section.get("material_overrides", {}).get(rule["id"], {})
            controlled_source = rule.get("source", "manual_quantity")
            source_override = override.get("source_override")
            source_key = source_override if source_override not in (None, "") else controlled_source
            if source_key in totals:
                # A missing selection list is the backward-compatible equivalent of
                # "all materials selected".  New rows write the list explicitly.
                source = Decimal(0)
                for row in section.get("lines", []):
                    selections = row.get("installation_material_ids")
                    if selections is None or rule["id"] in selections:
                        value = row.get("quantity") if source_key == "quantity" else row.get("calculated", {}).get(source_key)
                        source += dec(value, Decimal(0)) or Decimal(0)
            elif source_key == "manual_quantity":
                source = dec(rule.get("manual_quantity"), Decimal(0)) or Decimal(0)
            else:
                # The workbook's Tie Back and Backpan inputs remain section-level
                # until their future line-level placement is confirmed.
                source = dec(section.get(source_key), Decimal(0)) or Decimal(0)
            controlled_operator = rule.get("operator") or "multiply"
            controlled_operand = rule.get("operand", rule.get("factor", 1))
            controlled_unit = str(rule.get("unit") or "each")
            unit_override = override.get("unit_override")
            unit = str(unit_override) if unit_override not in (None, "") else controlled_unit
            operator_override = override.get("operator_override")
            operator = operator_override if operator_override not in (None, "") else controlled_operator
            operand_override = override.get("operand_override")
            factor_override = override.get("factor_override")
            if factor_override in (None, "") and "factor" in override:
                factor_override = override.get("factor")
            operand = operand_override if operand_override not in (None, "") else factor_override if factor_override not in (None, "") else controlled_operand
            formula_override = any(value not in (None, "") for value in (source_override, operator_override, operand_override, factor_override, unit_override))
            try:
                calculated_quantity = installation_material_quantity(source, operator, operand)
            except ValueError as exc:
                calculated_quantity = None
                warnings.append(_warning(
                    "invalid_installation_material_formula", rule.get("id"), str(exc), blocking=True,
                    entity_type="installation_material", section_id=section.get("id"),
                ))
            controlled_rate = rule.get("rate")
            rate_override = override.get("rate_override")
            if rate_override in (None, "") and "rate" in override:
                rate_override = override.get("rate")
            rate_values = effective_rate(controlled_rate, rate_override)
            rate = rate_values["effective_rate"]
            cost = installation_material(calculated_quantity, 1, rate)
            material_results.append({
                "material_rule_id": rule["id"], "name": rule.get("name"), "source": source_key,
                "unit": unit, "controlled_unit": controlled_unit,
                "unit_override": str(unit_override) if unit_override not in (None, "") else None,
                "material_code": rule.get("material_code"),
                "section_id": section.get("id"), "section_name": section.get("name"),
                "project_specific": bool(rule.get("project_specific")),
                "controlled_rate_id": rule.get("controlled_rate_id"),
                "controlled_reference_status": rule.get("controlled_reference_status", "controlled"),
                "source_quantity": jsonable(source),
                "controlled_source": controlled_source, "source_override": source_override or None,
                "controlled_operator": controlled_operator, "operator_override": operator_override or None, "operator": operator,
                "controlled_operand": jsonable(dec(controlled_operand)),
                "operand_override": jsonable(dec(operand_override)) if operand_override not in (None, "") else None,
                "operand": jsonable(dec(operand)), "calculated_quantity": jsonable(calculated_quantity),
                "is_formula_override": formula_override,
                "controlled_factor": jsonable(dec(controlled_operand)), "factor_override": jsonable(dec(factor_override)) if factor_override not in (None, "") else None,
                "factor": jsonable(dec(operand)) if operator == "multiply" else None, "controlled_rate": jsonable(rate_values["controlled_rate"]),
                "rate_override": jsonable(rate_values["rate_override"]), "effective_rate": jsonable(rate),
                "rate": jsonable(rate), "is_rate_override": rate_values["is_override"],
                "rate_override_reason": override.get("rate_override_reason"),
                "pre_tax_cost": str(cost) if cost is not None else None,
            })
            if cost is not None and code:
                material_cost_code = rule.get("cost_code") or code
                raw.append({"code": code, "grouping_code": code, "actual_cost_code": material_cost_code,
                            "category": "installation_material", "description": str(rule.get("name") or material_cost_code),
                            "cost": taxed_cost(cost, tax_rate, taxable=taxable and rule.get("taxable", True)), "area": totals["square_feet"],
                            "tax_treatment": "taxed" if taxable and rule.get("taxable", True) else "exempt", "markup_type": "installation_material",
                            "source_key": f"frame_material:{section['id']}:{rule['id']}",
                            "lineage": [{"source_type": "frame_material", "source_id": section["id"], "material_rule_id": rule["id"], "source_quantity": jsonable(source),
                                         "material_name": rule.get("name"), "unit": unit,
                                         "controlled_unit": controlled_unit,
                                         "unit_override": str(unit_override) if unit_override not in (None, "") else None,
                                         "section_name": section.get("name"),
                                         "project_specific": bool(rule.get("project_specific")), "controlled_rate_id": rule.get("controlled_rate_id"),
                                         "controlled_source": controlled_source, "effective_source": source_key,
                                         "controlled_operator": controlled_operator, "effective_operator": operator,
                                         "controlled_operand": jsonable(dec(controlled_operand)),
                                         "operand_override": jsonable(dec(operand_override)) if operand_override not in (None, "") else None,
                                         "effective_operand": jsonable(dec(operand)), "calculated_quantity": jsonable(calculated_quantity),
                                         "controlled_factor": jsonable(dec(controlled_operand)), "factor_override": jsonable(dec(factor_override)) if factor_override not in (None, "") else None,
                                         "effective_factor": jsonable(dec(operand)) if operator == "multiply" else None, "controlled_rate": jsonable(rate_values["controlled_rate"]),
                                         "rate_override": jsonable(rate_values["rate_override"]), "effective_rate": jsonable(rate),
                                         "rate_override_reason": override.get("rate_override_reason"), "pre_tax_cost": str(cost), "configuration_id": config["id"]}]})
        section["material_results"] = material_results
        pre_tax_material_cost = sum((dec(item["pre_tax_cost"], Decimal(0)) or Decimal(0) for item in material_results), Decimal(0))
        section["pre_tax_material_cost"] = money_string(pre_tax_material_cost)
        section["pre_tax_material_cost_per_sf"] = money_string(pre_tax_material_cost / totals["square_feet"]) if totals["square_feet"] else None

    # Door quantities are commercial submission controls even though the exact
    # Door/Hardware-to-Bid cost route remains unresolved in INF-4320.
    for row in doc.get("doors", []):
        quantity = dec(row.get("leaf_quantity", row.get("quantity")))
        if _door_row_meaningful(row) and quantity in (None, Decimal(0)):
            acknowledged = bool(row.get("missing_quantity_acknowledged"))
            warnings.append(_warning(
                "missing_door_quantity", row.get("id"),
                "Door row contains information but Quantity is blank or zero."
                + (" The estimator acknowledged this line-level exception." if acknowledged else ""),
                blocking=not acknowledged, acknowledged=acknowledged, entity_type="door_line",
            ))

    # Borrowed-lite areas and internal costs.
    brl_area_by_code: dict[str, Decimal] = {}
    brl_cost_by_code: dict[str, Decimal] = {}
    for row in doc.get("borrowed_lites", []):
        try:
            area = borrowed_lite_area(row.get("quantity"), row.get("width_inches"), row.get("height_inches"))
        except ValueError as exc:
            warnings.append(_warning("invalid_borrowed_lite", row["id"], str(exc), blocking=True, entity_type="borrowed_lite"))
            area = None
        row["calculated_square_feet"] = jsonable(area)
        code = row.get("code", "")
        code_key = _full_code_key(code)
        if code_key:
            code_display.setdefault(code_key, _display_code(code))
        if area is not None:
            brl_area_by_code[code_key] = brl_area_by_code.get(code_key, Decimal(0)) + area
            if dec(row.get("rate")) is not None:
                brl_cost_by_code[code_key] = brl_cost_by_code.get(code_key, Decimal(0)) + area * (dec(row.get("rate")) or Decimal(0))

    area_by_code = {
        key: frame_area_by_code.get(key, Decimal(0)) + brl_area_by_code.get(key, Decimal(0))
        for key in set(frame_area_by_code) | set(brl_area_by_code)
    }

    # Quotes are grouped implicitly by full Cost Code. Historical group_id remains
    # preserved but does not control selection or Bid aggregation.
    for q in doc.get("quotes", []):
        code = q.get("code", "")
        code_key = _full_code_key(code)
        if code_key:
            code_display.setdefault(code_key, _display_code(code))
        nested_credit = q.get("credit") if isinstance(q.get("credit"), dict) else {}
        nested_surcharge = q.get("surcharge") if isinstance(q.get("surcharge"), dict) else {}
        try:
            adjustment = quote_adjustment(
                q.get("price"), q.get("credit_type", nested_credit.get("type")),
                q.get("credit_value", nested_credit.get("value", 0)),
                q.get("surcharge_type", nested_surcharge.get("type")),
                q.get("surcharge_value", nested_surcharge.get("value", 0)),
                legacy_surcharge_percent=q.get("surcharge_percent") if "surcharge_type" not in q and not nested_surcharge else None,
            )
        except ValueError as exc:
            warnings.append(_warning("invalid_quote_adjustment", q.get("id"), str(exc), blocking=True, entity_type="quote"))
            adjustment = quote_adjustment(None)
        q["calculation_lineage"] = jsonable(adjustment)
        q["calculated_credit_amount"] = jsonable(adjustment["credit_amount"])
        q["calculated_post_credit_subtotal"] = jsonable(adjustment["post_credit_subtotal"])
        q["calculated_surcharge_amount"] = jsonable(adjustment["surcharge_amount"])
        cost = adjustment["final_adjusted_value"]
        q["calculated_cost"] = jsonable(cost)
        quote_area_source = q.get("square_feet_source")
        if quote_area_source != "manual" and (q.get("square_feet") in (None, "") or quote_area_source == "frame_default"):
            frame_default = frame_area_by_code.get(code_key, Decimal(0))
            q["square_feet"] = jsonable(frame_default) if frame_default else None
            q["square_feet_source"] = "frame_default" if frame_default else (quote_area_source or "unassigned")
        quote_area = dec(q.get("square_feet"))
        q["calculated_square_feet"] = jsonable(quote_area)
        q["calculated_unit_cost"] = jsonable(quote_unit_cost(cost, quote_area))

    groups = select_used_quotes(doc)
    for group_key, rows in groups.items():
        used = [q for q in rows if q.get("used")]
        if not used and any(dec(q.get("price")) is not None for q in rows):
            warnings.append(_warning("missing_used_quote", group_key, "Select at least one quote used by this Cost Code.", blocking=False, entity_type="quote_group"))
        for q in used:
            code, cost = q.get("code", ""), dec(q.get("calculated_cost"), Decimal(0)) or Decimal(0)
            if code:
                raw.append({"code": code, "category": "base_product", "description": _cost_code(doc, code).get("description", code),
                            "cost": taxed_cost(cost, tax_rate, taxable=taxable, tax_included=bool(q.get("tax_included"))),
                            "area": area_by_code.get(_full_code_key(code), Decimal(0)),
                            "tax_treatment": "included" if q.get("tax_included") else ("taxed" if taxable else "exempt"), "markup_type": "base_product",
                            "source_key": f"quote:{q['id']}",
                            "lineage": [{"source_type": "quote", "source_id": q["id"], "entered_price": q.get("price"),
                                         "credit_type": q.get("calculation_lineage", {}).get("credit_type"), "credit_value": q.get("calculation_lineage", {}).get("credit_value"),
                                         "credit_amount": q.get("calculated_credit_amount"), "post_credit_subtotal": q.get("calculated_post_credit_subtotal"),
                                         "surcharge_type": q.get("calculation_lineage", {}).get("surcharge_type"), "surcharge_value": q.get("calculation_lineage", {}).get("surcharge_value"),
                                         "surcharge_amount": q.get("calculated_surcharge_amount"), "final_adjusted_value": q.get("calculated_cost"),
                                         "tax_included": bool(q.get("tax_included")), "selection_mode": q.get("used_selection_mode"), "configuration_id": config["id"]}]})

    for code_key, cost in brl_cost_by_code.items():
        code = code_display.get(code_key, code_key)
        source = doc["working_estimate"].get("borrowed_lite_source_by_code", {}).get(code, "quote")
        if source == "internal":
            raw.append({"code": code, "category": "borrowed_lite", "description": f"{_cost_code(doc, code).get('description', code)} — Internal borrowed-lite calculation",
                        "cost": taxed_cost(cost, tax_rate, taxable=taxable), "area": brl_area_by_code.get(code_key, Decimal(0)), "tax_treatment": "taxed" if taxable else "exempt", "markup_type": "base_product",
                        "source_key": f"borrowed_lite:{code_key}",
                        "lineage": [{"source_type": "borrowed_lite", "source_ids": [r["id"] for r in doc["borrowed_lites"] if _full_code_key(r.get("code")) == code_key], "source_choice": "internal", "configuration_id": config["id"]}]})

    equipment_subtotal = Decimal(0)
    for row in doc.get("equipment", []):
        cost = equipment_extension(row.get("quantity"), row.get("duration"), row.get("rate"), row.get("delivery"))
        row["calculated_cost"] = jsonable(cost)
        code = row.get("code", "11 00 00")
        if cost is not None and _active(doc, code):
            equipment_subtotal += cost
        if cost is not None:
            row_taxable = bool(row.get("taxable", True))
            raw.append({"code": code, "category": "equipment", "description": row.get("description") or "Equipment", "cost": taxed_cost(cost, tax_rate, taxable=taxable and row_taxable), "area": Decimal(0),
                        "tax_treatment": "taxed" if taxable and row_taxable else "exempt", "markup_type": "base_product", "source_key": f"equipment:{row['id']}",
                        "lineage": [{"source_type": "equipment", "source_id": row["id"], "quantity": row.get("quantity"), "duration": row.get("duration"),
                                     "duration_unit": row.get("duration_unit"), "rate": row.get("rate"), "delivery": row.get("delivery"), "pre_tax_cost": jsonable(cost),
                                     "row_taxable": row_taxable, "rate_version": row.get("rate_version", config["id"]), "configuration_id": config["id"]}]})
        elif _meaningful(row, {"id", "calculated_cost", "taxable"}) and row.get("rate") in (None, ""):
            warnings.append(_warning("missing_equipment_rate", row.get("id"), "Equipment line has no rate and cannot contribute to Bid.", blocking=True, entity_type="equipment"))
    doc["working_estimate"]["equipment_subtotal"] = money_string(equipment_subtotal)

    sync_labor_candidates(doc, config)
    for row in doc.get("labor_estimates", []):
        labor_type = str(row.get("labor_type") or row.get("category") or "Field").strip().title()
        if labor_type not in {"Field", "Shop", "Design"}:
            warnings.append(_warning("invalid_labor_type", row.get("id"), "Labor Type must be Field, Shop, or Design.", blocking=True, entity_type="labor"))
            labor_type = "Field"
        row["labor_type"] = labor_type
        row["category"] = labor_type.lower()
        hours = dec(row.get("man_hours"))
        if hours is None:
            hours = labor_hours(row.get("quantity"), row.get("crew"), row.get("productivity"), row.get("hours_override"))
        row["calculated_man_hours"] = row["calculated_hours"] = jsonable(hours)
        snapshot = _controlled_labor_snapshot(doc, config, row, labor_type)
        if not isinstance(row.get("controlled_rate_snapshot"), dict) or row.get("controlled_rate_snapshot", {}).get("rate") in (None, ""):
            row["controlled_rate_snapshot"] = deepcopy(snapshot)
        controlled_rate = snapshot.get("rate")
        override_value = row.get("rate_override")
        if isinstance(override_value, dict):
            override_value = override_value.get("rate", override_value.get("value"))
        legacy_rate = row.get("legacy_effective_rate", row.get("rate"))
        rate_values = effective_rate(controlled_rate, override_value)
        effective = rate_values["effective_rate"]
        legacy_effective = False
        if override_value in (None, "") and legacy_rate not in (None, ""):
            effective = dec(legacy_rate)
            legacy_effective = controlled_rate in (None, "") or dec(legacy_rate) != dec(controlled_rate)
        row["calculated_controlled_rate"] = jsonable(dec(controlled_rate))
        row["calculated_effective_rate"] = jsonable(effective)
        crew_size = row.get("crew_size", row.get("crew"))
        try:
            schedule = labor_schedule(hours, crew_size, row.get("hours_per_worker_per_day"), row.get("workdays_per_week"))
        except ValueError as exc:
            warnings.append(_warning("invalid_labor_schedule", row.get("id"), str(exc), blocking=True, entity_type="labor"))
            schedule = labor_schedule(hours, crew_size, None, None)
        row["calculated_schedule"] = jsonable(schedule)
        row["shift_configuration"] = schedule["shift_configuration"]
        row["calculated_working_days"] = jsonable(schedule["working_days"])
        row["calculated_calendar_weeks"] = jsonable(schedule["calendar_weeks"])
        row["calculated_calendar_days"] = jsonable(schedule["calendar_days"])
        cost = labor_extension(hours, effective)
        row["calculated_cost"] = jsonable(cost)
        code, category = row.get("code", ""), labor_type.lower()
        meaningful_labor = _meaningful(row, {
            "id", "code", "labor_type", "category", "origin", "source_links", "source_status",
            "stale_acknowledged", "controlled_rate_snapshot", "rate_override", "rate_override_reason", "man_hours_source",
            "calculated_man_hours", "calculated_hours", "calculated_controlled_rate", "calculated_effective_rate",
            "calculated_schedule", "calculated_working_days", "calculated_calendar_weeks",
            "calculated_calendar_days", "calculated_cost", "shift_configuration",
        })
        if row.get("source_status") == "stale":
            acknowledged = bool(row.get("stale_acknowledged"))
            warnings.append(_warning(
                "stale_labor_source", row.get("id"),
                "This source-linked Labor row no longer has an active Quote, Frame, Door, Equipment, or Borrowed Lite source."
                + (" The estimator acknowledged this exception." if acknowledged else ""),
                blocking=not acknowledged, acknowledged=acknowledged, entity_type="labor",
            ))
        if labor_type == "Design" and dec(controlled_rate) is None and meaningful_labor:
            warnings.append(_warning("unavailable_design_rate", row.get("id"), "No controlled Design labor rate is configured; synthetic or legacy values cannot authorize commercial use.", blocking=True, entity_type="labor"))
        elif meaningful_labor and effective is None:
            warnings.append(_warning("missing_labor_rate", row.get("id"), "Labor line has no effective controlled or project-override rate.", blocking=True, entity_type="labor"))
        if meaningful_labor and hours is None:
            warnings.append(_warning("missing_labor_man_hours", row.get("id"), "Labor line requires Man Hours.", blocking=True, entity_type="labor"))
        if cost is not None and code:
            markup_type = "LAS" if category == "shop" else "LAF"
            raw.append({"code": code, "category": category + "_labor", "description": row.get("description") or ("Shop labor" if category == "shop" else "Field labor"), "cost": cost,
                        "area": Decimal(0), "tax_treatment": "not_applicable", "markup_type": markup_type, "source_key": f"labor:{row['id']}",
                        "lineage": [{"source_type": "labor", "source_id": row["id"], "labor_type": labor_type, "man_hours": jsonable(hours),
                                     "man_hours_source": row.get("man_hours_source") or ("legacy_calculation" if row.get("man_hours") in (None, "") else "manual"),
                                     "legacy_quantity": row.get("quantity"), "legacy_crew": row.get("crew"), "legacy_productivity": row.get("productivity"),
                                     "crew_size": jsonable(dec(crew_size)), "hours_per_worker_per_day": row.get("hours_per_worker_per_day"), "workdays_per_week": row.get("workdays_per_week"),
                                     "shift_configuration": schedule["shift_configuration"], "working_days": jsonable(schedule["working_days"]),
                                     "calendar_weeks": jsonable(schedule["calendar_weeks"]), "controlled_rate": jsonable(dec(controlled_rate)),
                                     "rate_override": jsonable(dec(override_value)) if override_value not in (None, "") else None,
                                     "legacy_effective_rate": jsonable(dec(legacy_rate)) if legacy_rate not in (None, "") else None,
                                     "legacy_effective_rate_used": legacy_effective, "effective_rate": jsonable(effective),
                                     "rate_override_reason": row.get("rate_override_reason"), "rate_id": snapshot.get("rate_id"),
                                     "rate_version": snapshot.get("configuration_id") or row.get("rate_version", config["id"]), "configuration_id": config["id"]}]})

    for row in doc.get("travel_estimates", []):
        if row.get("enabled"):
            warnings.append(_warning(
                "travel_policy_unavailable", row.get("id"),
                "Travel/per-diem is enabled, but controlled overnight, excluded-day, lodging, mileage, and per-diem applicability rules are not configured.",
                blocking=True, entity_type="travel",
            ))

    lines: list[dict] = []
    for item in raw:
        sign = _sign(doc, item["code"])
        signed_cost = item["cost"] * sign
        markup_defaults = config.get("markup_defaults", {})
        default_record = markup_defaults.get(item["markup_type"])
        inherited_from = None
        if (
            item["markup_type"] == "installation_material"
            and (not isinstance(default_record, dict) or default_record.get("rate") in (None, ""))
        ):
            default_record = markup_defaults.get("base_product", {})
            inherited_from = "base_product"
        default_record = default_record or {}
        configuration_rate = default_record.get("rate", "0")
        project_defaults = doc["working_estimate"].get("markup_overrides", {})
        project_rate = project_defaults.get(item["markup_type"])
        if project_rate in (None, "") and item["markup_type"] == "installation_material":
            project_rate = project_defaults.get("base_product")
            inherited_from = inherited_from or "base_product"
        applicable_default = configuration_rate if project_rate in (None, "") else project_rate
        component_map = doc["working_estimate"].setdefault("component_markup_overrides", {})
        component = component_map.get(item.get("source_key"), {})
        if not isinstance(component, dict):
            component = {"rate": component}
        component_mode = component.get("mode")
        component_value = component.get("value")
        component_rate = component.get("rate", component.get("rate_override"))
        if component_mode not in {"percentage", "amount"}:
            component_mode = "percentage" if component_rate not in (None, "") else None
            component_value = component_rate if component_mode else None
        chosen_rate = component_value if component_mode == "percentage" else applicable_default
        if "".join(c for c in item["code"] if c.isalnum()) == "012116":
            chosen_rate, component_mode, component_value = "0", None, None
        if component_mode == "amount":
            manual_amount = dec(component_value)
            if manual_amount is None:
                manual_amount = Decimal(0)
            # The entered amount is an absolute markup decision; deduct lines
            # retain their commercial sign without requiring a negative entry.
            effective_amount = -manual_amount if signed_cost < 0 and manual_amount > 0 else manual_amount
            m = {"markup": effective_amount, "selling_value": signed_cost + effective_amount}
            effective_markup_rate = None if signed_cost == 0 else effective_amount / signed_cost
        else:
            m = markup(signed_cost, chosen_rate)
            effective_markup_rate = chosen_rate
        provenance = {
            "configuration_default_rate": str(configuration_rate),
            "project_category_rate": None if project_rate in (None, "") else str(project_rate),
            "component_override_rate": None if component_mode != "percentage" else str(component_value),
            "component_override_mode": component_mode,
            "component_override_value": None if component_mode is None else str(component_value),
            "effective_rate": None if effective_markup_rate is None else str(effective_markup_rate), "applicable_type": item["markup_type"],
            "inherited_from": inherited_from, "is_component_override": component_mode is not None,
            "override_reason": component.get("reason") or component.get("rate_override_reason"),
            "override_source": component.get("source"),
        }
        item["lineage"].append({"source_type": "markup", **provenance, "configuration_id": config["id"]})
        lines.append({"id": _stable_line_id(item), **item,
                      "grouping_code": item.get("grouping_code") or item["code"],
                      "actual_cost_code": item.get("actual_cost_code") or item["code"],
                      "direct_cost": money_string(signed_cost), "cost": None, "included": _active(doc, item["code"]), "deduct_sign": int(sign), "markup_rate": None if effective_markup_rate is None else str(effective_markup_rate),
                      "markup_default_rate": str(applicable_default), "markup_override_rate": provenance["component_override_rate"], "markup_provenance": provenance,
                      "markup_override_mode": component_mode, "markup_override_value": provenance["component_override_value"],
                      "markup_value": money_string(m["markup"]), "selling_value": money_string(m["selling_value"]), "area": jsonable(item["area"]), "configuration_id": config["id"]})

    direct = sum((dec(x["direct_cost"], Decimal(0)) or Decimal(0) for x in lines if x.get("included", True)), Decimal(0))
    sell_before = sum((dec(x["selling_value"], Decimal(0)) or Decimal(0) for x in lines if x.get("included", True)), Decimal(0))
    cont = contingency(direct, bool(doc["working_estimate"].get("contingency_enabled")), config["contingency"]["rate"], config["contingency"]["minimum"], doc["working_estimate"].get("contingency_override"))
    if cont:
        lines.append(_special_line("01 21 16", "Contingency", cont, config["id"], "contingency"))
    bond = bond_amount(sell_before + cont, bool(doc["working_estimate"].get("bond_enabled")), config["bond"]["bands"], doc["working_estimate"].get("bond_override"))
    if bond["amount"]:
        lines.append(_special_line("00 61 13", "Bond", bond["amount"], config["id"], "bond", {"band": bond["band"], "basis": str(sell_before + cont)}))
    direct_total = sum((dec(x["direct_cost"], Decimal(0)) or Decimal(0) for x in lines if x.get("included", True)), Decimal(0))
    selling_total = sum((dec(x["selling_value"], Decimal(0)) or Decimal(0) for x in lines if x.get("included", True)), Decimal(0))
    markup_total = selling_total - direct_total
    area_total = sum((area for key, area in area_by_code.items() if _active(doc, code_display.get(key, key))), Decimal(0))

    # One derived summary per full Cost Code. It references normalized source lines
    # and never becomes a second editable source of truth.
    ordered_codes: list[tuple[str, str]] = []
    for record in doc.get("cost_codes", []):
        key, display = _full_code_key(record.get("code")), _display_code(record.get("code"))
        if key and key not in {item[0] for item in ordered_codes}:
            ordered_codes.append((key, display))
            code_display.setdefault(key, display)
    for line in lines:
        key, display = _full_code_key(line.get("code")), _display_code(line.get("code"))
        if key and key not in {item[0] for item in ordered_codes}:
            ordered_codes.append((key, display))
            code_display.setdefault(key, display)
    for key, display in code_display.items():
        if key and key not in {item[0] for item in ordered_codes}:
            ordered_codes.append((key, display))

    component_labels = {
        "base_product": "Base Product", "installation_material": "Installation Materials",
        "field_labor": "LAF", "shop_labor": "LAS", "design_labor": "Design Labor",
        "equipment": "Equipment", "borrowed_lite": "Borrowed Lites", "door": "Doors",
        "contingency": "Contingency", "bond": "Bond",
    }
    summaries = []
    for code_key, display in ordered_codes:
        source_lines = [line for line in lines if _full_code_key(line.get("code")) == code_key]
        cost = sum((dec(line.get("direct_cost"), Decimal(0)) or Decimal(0) for line in source_lines), Decimal(0))
        value = sum((dec(line.get("selling_value"), Decimal(0)) or Decimal(0) for line in source_lines), Decimal(0))
        margin_value = value - cost
        area = area_by_code.get(code_key, Decimal(0))
        component_groups: dict[str, dict[str, Any]] = {}
        for line in source_lines:
            label = component_labels.get(line.get("category"), str(line.get("category", "Other")).replace("_", " ").title())
            group = component_groups.setdefault(label, {"category": line.get("category"), "lines": []})
            group["lines"].append(line)
        components = []
        component_order = {"Base Product": 0, "LAF": 1, "LAS": 2, "Design Labor": 3, "Installation Materials": 4}
        for label, group in sorted(component_groups.items(), key=lambda item: (component_order.get(item[0], 20), item[0])):
            component_lines = group["lines"]
            component_cost = sum((dec(line.get("direct_cost"), Decimal(0)) or Decimal(0) for line in component_lines), Decimal(0))
            component_value = sum((dec(line.get("selling_value"), Decimal(0)) or Decimal(0) for line in component_lines), Decimal(0))
            markup_rates = sorted({str(line.get("markup_rate")) for line in component_lines if line.get("markup_rate") is not None})
            components.append({
                "name": label, "category": group["category"], "direct_cost": money_string(component_cost),
                "margin_dollars": money_string(component_value - component_cost),
                "selling_value": money_string(component_value),
                "markup_rate": markup_rates[0] if len(markup_rates) == 1 else None,
                "markup_state": "mixed" if len(markup_rates) > 1 else "uniform",
                "override_count": sum(1 for line in component_lines if line.get("markup_override_mode") is not None),
                "source_count": len(component_lines),
                "source_line_ids": [line["id"] for line in component_lines],
            })
        description = _cost_code(doc, display).get("description", display)
        summaries.append({
            "code": display, "description": description, "included": _active(doc, display),
            "direct_cost": money_string(cost), "cost": money_string(cost),
            "margin_dollars": money_string(margin_value),
            "margin_percentage": str(Decimal(0) if value == 0 else margin_value / value),
            "selling_value": money_string(value), "value": money_string(value),
            "total_square_feet": jsonable(area), "square_feet": jsonable(area),
            "dollars_per_square_foot": None if area == 0 else money_string(value / area),
            "metric_definition": BID_COST_CODE_SELL_PER_SF_METRIC,
            "components": components, "source_line_ids": [line["id"] for line in source_lines],
        })
    totals = {"direct_cost": money_string(direct_total), "markup_profit": money_string(markup_total), "selling_value": money_string(selling_total),
              "margin_percentage": str(Decimal(0) if selling_total == 0 else markup_total / selling_total), "square_feet": str(area_total),
              "price_per_square_foot": None if area_total == 0 else money_string(selling_total / area_total), "reconciliation": "ok",
              "contingency": money_string(cont), "bond": money_string(bond["amount"])}
    doc["working_estimate"]["lines"] = jsonable(lines)
    doc["working_estimate"]["cost_code_summaries"] = jsonable(summaries)
    doc["working_estimate"]["totals"] = totals
    doc["working_estimate"]["validation"] = warnings
    if include_alternates:
        calculate_alternates(doc, config, calculate_project)
    return doc


def money_string(value: Decimal) -> str:
    """Serialize an exact Decimal without imposing display precision."""
    return format(value, "f")


def _special_line(code: str, description: str, amount: Decimal, config_id: str, category: str, extra: dict | None = None) -> dict:
    lineage = {"source_type": category, "configuration_id": config_id}
    lineage.update(extra or {})
    return {"id": "est_" + hashlib.sha256(f"{code}:{category}".encode()).hexdigest()[:24], "code": code, "category": category, "description": description, "direct_cost": money_string(amount), "included": True, "deduct_sign": 1,
            "markup_type": "special", "markup_rate": "0", "markup_value": "0.00", "selling_value": money_string(amount), "area": "0", "tax_treatment": "not_applicable", "configuration_id": config_id, "lineage": [lineage]}


def _bid_markup_source_key(doc: dict, source_type: str, source_id: Any) -> str:
    """Resolve a generated Bid detail to its stable canonical source-key.

    The override is stored against ``source_key`` rather than a generated Bid
    line ID, so recalculation can rebuild lines without losing the decision.
    ``source_id`` may be either the canonical record ID or the current stable
    estimate-line ID used by expanded Bid detail.
    """
    candidates: list[str] = []
    searchable_lines = list(doc.get("working_estimate", {}).get("lines", []))
    for alternate in doc.get("alternates", []):
        searchable_lines.extend(alternate.get("calculated", {}).get("effective_estimate", {}).get("lines", []))
    for line in searchable_lines:
        source_key = line.get("source_key")
        if not source_key:
            continue
        if source_id in {line.get("id"), source_key}:
            candidates.append(source_key)
            continue
        for lineage in line.get("lineage", []):
            lineage_type = str(lineage.get("source_type") or "").lower()
            type_matches = lineage_type == source_type or (
                source_type == "frame" and lineage_type == "frame_material"
            )
            if not type_matches:
                continue
            lineage_ids = lineage.get("source_ids") or []
            if lineage.get("source_id") == source_id or source_id in lineage_ids:
                candidates.append(source_key)
                break
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise DomainError(
            "That canonical record contributes more than one Bid source line; select the exact expanded source line before overriding markup.",
            "ambiguous_bid_source",
            [{"source_keys": candidates}],
        )
    if isinstance(source_id, str) and ":" in source_id:
        prefix = source_id.split(":", 1)[0]
        allowed_prefixes = {"quote", "equipment", "labor", "frame_material", "borrowed_lite"}
        if prefix in allowed_prefixes:
            return source_id
    direct_prefix = {"quote": "quote", "equipment": "equipment", "labor": "labor"}.get(source_type)
    if direct_prefix:
        return f"{direct_prefix}:{source_id}"
    raise DomainError("The originating Bid source line was not found.", "not_found")


def edit_bid_source(doc: dict, config: dict, actor: str, role: str, payload: dict) -> dict:
    """Confirm and apply a Bid-originated edit to its canonical source record."""
    require(role, "edit_estimate")
    if payload.get("confirmed") is not True:
        raise DomainError(
            "Confirm that this Bid edit will update the originating source record and recalculate the Bid.",
            "confirmation_required",
        )
    source_type = str(payload.get("source_type") or "").strip().lower()
    source_id = payload.get("source_id")
    changes = payload.get("changes")
    if not isinstance(changes, dict) or not changes:
        raise DomainError("Provide at least one source field to update.")

    markup_fields = {"markup_override", "markup_percent", "markup_amount", "markup_override_mode", "markup_override_value"}
    if set(changes) & markup_fields:
        disallowed = sorted(set(changes) - markup_fields - {"reason"})
        if disallowed:
            raise DomainError(
                "A markup override command cannot also change canonical source fields; save those edits separately."
            )
        source_key = _bid_markup_source_key(doc, source_type, source_id)
        alternate = None
        alternate_id = payload.get("alternate_id")
        if alternate_id:
            alternate = next((row for row in doc.get("alternates", []) if str(row.get("id")) == str(alternate_id)), None)
            if alternate is None:
                raise DomainError("Alternate was not found.", "not_found")
            overrides = alternate.setdefault("changes", {}).setdefault("line_markup_overrides", {}).setdefault("overrides", {})
            stored_prior = overrides.get(source_key)
            prior = deepcopy(stored_prior.get("value") if isinstance(stored_prior, dict) and "value" in stored_prior else stored_prior)
        else:
            overrides = doc.setdefault("working_estimate", {}).setdefault("component_markup_overrides", {})
            prior = deepcopy(overrides.get(source_key))
        legacy_markup_request = "markup_override" in changes and not (set(changes) & (markup_fields - {"markup_override"}))
        supplied_percent = changes.get("markup_percent", changes.get("markup_override"))
        supplied_amount = changes.get("markup_amount")
        explicit_mode = changes.get("markup_override_mode")
        explicit_value = changes.get("markup_override_value")
        if supplied_percent not in (None, "") and supplied_amount not in (None, ""):
            raise DomainError(
                "Only one manual markup authority may be supplied for a line; clear either Markup % or Markup $.",
                "ambiguous_markup_authority",
            )
        if explicit_mode not in (None, "", "percentage", "amount"):
            raise DomainError("Markup override mode must be percentage or amount.", "invalid_markup_override")
        if explicit_mode:
            mode, entered = explicit_mode, explicit_value
        elif "markup_amount" in changes:
            mode, entered = "amount", supplied_amount
        else:
            mode, entered = "percentage", supplied_percent
        reason = changes.get("reason") or payload.get("reason") or "Confirmed Bid source-line markup decision"
        if entered in (None, ""):
            overrides.pop(source_key, None)
            new_value = None
            operation = "clear_bid_markup_override" if legacy_markup_request else "line_markup_override_clear"
        else:
            try:
                normalized_value = dec(entered)
                if normalized_value is None or normalized_value < 0:
                    raise ValueError
            except Exception as exc:
                raise DomainError("Manual markup must be a non-negative numeric decimal value.", "invalid_markup_override") from exc
            new_value = ({"rate": str(normalized_value)} if legacy_markup_request else {
                "mode": mode, "value": str(normalized_value),
                **({"rate": str(normalized_value)} if mode == "percentage" else {"amount": str(normalized_value)}),
            })
            new_value.update({"reason": reason, "source": "bid_expanded_detail", "updated_by": actor, "updated_at": now()})
            if alternate is None:
                overrides[source_key] = new_value
            else:
                base_override = deepcopy(doc.setdefault("working_estimate", {}).setdefault("component_markup_overrides", {}).get(source_key))
                overrides[source_key] = {"base_value": base_override, "value": new_value, "set_at": now()}
            prior_mode = prior.get("mode") if isinstance(prior, dict) else None
            if legacy_markup_request:
                operation = "set_bid_markup_override"
            elif prior_mode and prior_mode != mode:
                operation = "line_markup_override_mode_switch"
            elif prior is None:
                operation = "line_markup_override_create"
            else:
                operation = "line_markup_override_value_change"
        calculate_project(doc, config)
        bump_bid_version(doc, "bid_markup_override")
        audit(
            doc, actor, role, "bid_markup_override", source_key, operation,
            prior, deepcopy(new_value), reason, payload.get("correlation_id"),
        )
        result = {
            "source_key": source_key,
            "markup_override": None if new_value is None else new_value.get("value", new_value.get("rate")),
            "cleared": new_value is None,
        }
        if not legacy_markup_request:
            result.update({"markup_override_mode": None if new_value is None else new_value["mode"], "alternate_id": alternate_id})
        return result

    collections = {
        "quote": ("quotes", {"code", "date", "vendor", "price", "credit_type", "credit_value", "surcharge_type", "surcharge_value", "tax_included", "used", "square_feet", "square_feet_source", "notes"}),
        "door": ("doors", {"code", "door_number", "mark", "leaf_quantity", "width_inches", "height_inches", "type", "material", "finish", "description", "glass", "style", "rails", "hardware_group_id", "fire_rating", "notes", "missing_quantity_acknowledged"}),
        "equipment": ("equipment", {"code", "description", "quantity", "duration", "duration_unit", "rate", "delivery", "taxable", "notes"}),
        "labor": ("labor_estimates", {"code", "description", "labor_type", "man_hours", "crew_size", "hours_per_worker_per_day", "workdays_per_week", "rate_override", "rate_override_reason", "stale_acknowledged", "notes"}),
        "borrowed_lite": ("borrowed_lites", {"code", "mark", "quantity", "width_inches", "height_inches", "rate", "notes"}),
    }
    target = None
    allowed: set[str] = set()
    if source_type == "frame":
        allowed = {"mark", "quantity", "width_inches", "height_inches", "caulking_passes", "head", "sill", "jamb", "type", "material", "finish", "notes", "installation_material_ids", "missing_quantity_acknowledged"}
        target = next((line for section in doc.get("takeoff_sections", []) for line in section.get("lines", []) if line.get("id") == source_id), None)
    elif source_type in collections:
        collection, allowed = collections[source_type]
        target = next((row for row in doc.get(collection, []) if row.get("id") == source_id), None)
    if target is None:
        raise DomainError("The canonical Bid source record was not found.", "not_found")
    disallowed = sorted(set(changes) - allowed)
    if disallowed:
        raise DomainError(f"Bid source edit cannot modify: {', '.join(disallowed)}.")
    prior = deepcopy(target)
    target.update(deepcopy(changes))
    if source_type == "quote" and "square_feet" in changes and "square_feet_source" not in changes:
        target["square_feet_source"] = "manual" if changes["square_feet"] not in (None, "") else "unassigned"
    if source_type == "labor" and "labor_type" in changes:
        target["controlled_rate_snapshot"] = None
    if source_type == "quote" and "used" in changes:
        code = _display_code(target.get("code"))
        selection_map = doc.setdefault("working_estimate", {}).setdefault("quote_selection_by_code", {})
        stored_key, entry = _selection_entry(selection_map, code)
        entry = entry or {"mode": "manual", "selected_quote_ids": []}
        entry["mode"] = "manual"
        selected = set(entry.get("selected_quote_ids") or [row["id"] for row in doc.get("quotes", []) if _full_code_key(row.get("code")) == _full_code_key(code) and row.get("used")])
        if changes["used"]:
            selected.add(source_id)
        else:
            selected.discard(source_id)
        entry["selected_quote_ids"] = sorted(selected)
        selection_map[stored_key if stored_key in selection_map else code] = entry
    calculate_project(doc, config)
    bump_bid_version(doc, "bid_source_edit")
    audit(
        doc, actor, role, source_type, str(source_id), "bid_source_edit", prior, deepcopy(target),
        payload.get("reason") or "Confirmed edit from expanded Bid detail", payload.get("correlation_id"),
    )
    return target


def make_revision(doc: dict, actor: str, role: str, status: str, reason: str) -> dict:
    snapshot = {
        "id": uid("rev"), "revision_number": len(doc.get("estimate_revisions", [])) + 1, "configuration_id": doc["project"]["configuration_id"],
        "status": status, "bid_version": deepcopy(doc["project"].get("bid_version")), "created_by": actor, "creator_role": role, "created_at": now(), "reason": reason,
        "project_snapshot": deepcopy(doc["project"]), "cost_codes": deepcopy(doc["cost_codes"]), "source_snapshot": {
            key: deepcopy(doc[key]) for key in ("quotes", "takeoff_sections", "doors", "hardware_assignments", "equipment", "borrowed_lites", "labor_estimates", "travel_estimates")
        },
        "estimate": deepcopy(doc["working_estimate"]), "alternates": deepcopy(doc.get("alternates", [])), "immutable": status == "submitted"
    }
    doc.setdefault("estimate_revisions", []).append(snapshot)
    return snapshot


def proposal_artifact(doc: dict, revision: dict, actor: str) -> dict:
    amount = revision["estimate"]["totals"]["selling_value"]
    body = {"project_name": revision["project_snapshot"].get("name"), "project_number": revision["project_snapshot"].get("project_number"),
            "revision_id": revision["id"], "bid_version": deepcopy(revision.get("bid_version")), "amount": amount, "written_amount": dollars_in_words(amount),
            "project_address": revision["project_snapshot"].get("address", ""), "owner_name": revision["project_snapshot"].get("owner_name", ""),
            "bid_due_date": revision["project_snapshot"].get("bid_due_date"),
            "scope": revision["project_snapshot"].get("proposal_scope", ""), "inclusions": revision["project_snapshot"].get("proposal_inclusions", ""),
            "exclusions": revision["project_snapshot"].get("proposal_exclusions", ""), "addenda": revision["project_snapshot"].get("addenda_count", 0),
            "alternates": [{"key": row.get("key"), "name": row.get("name"), "customer_description": row.get("customer_description"),
                            "scope_of_change": deepcopy(row.get("calculated", {}).get("scope_of_change", [])),
                            "classification": row.get("calculated", {}).get("classification"),
                            "selling_value_delta": row.get("calculated", {}).get("selling_value_delta")}
                           for row in revision.get("alternates", [])]}
    artifact = {"id": uid("art"), "template_version": "proposal-1.0.0", "revision_id": revision["id"], "generated_at": now(), "generated_by": actor,
                **body, "sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(), "immutable": True}
    doc.setdefault("proposal_artifacts", []).append(artifact)
    return artifact


def submit(doc: dict, config: dict, actor: str, role: str, payload: dict) -> dict:
    require(role, "submit")
    calculate_project(doc, config)
    blocking = submission_blockers(doc)
    if blocking:
        raise DomainError("Submission validation failed.", details=blocking)
    bump_bid_version(doc, "submission", "minor")
    revision = make_revision(doc, actor, role, "submitted", payload.get("reason", "Bid submission"))
    artifact = proposal_artifact(doc, revision, actor)
    submission = {"id": uid("sub"), "revision_id": revision["id"], "bid_version": deepcopy(revision.get("bid_version")), "artifact_id": artifact["id"], "recipient": payload.get("recipient", ""),
                  "method": payload.get("method", ""), "submitted_at": now(), "submitted_by": actor, "evidence": payload.get("evidence", ""), "immutable": True}
    doc.setdefault("submissions", []).append(submission)
    doc["project"]["lifecycle_state"] = "submitted"
    audit(doc, actor, role, "estimate_revision", revision["id"], "submit", None, {"submission_id": submission["id"], "total": revision["estimate"]["totals"]["selling_value"]}, payload.get("reason", "Bid submission"))
    return submission


def activate(doc: dict, actor: str, role: str, payload: dict) -> dict:
    require(role, "activate")
    if doc.get("award"):
        existing = doc["award"]
        if existing["revision_id"] == payload.get("revision_id") and existing.get("ntp_evidence") == payload.get("ntp_evidence"):
            return existing
        raise DomainError("Project already has an awarded snapshot. Reversal/correction policy is pending owner confirmation.", "duplicate_activation")
    if not payload.get("ntp_evidence") or not payload.get("ntp_date"):
        raise DomainError("Notice-to-proceed evidence and date are required.")
    revision = next((r for r in doc.get("estimate_revisions", []) if r["id"] == payload.get("revision_id") and r["status"] == "submitted"), None)
    if not revision:
        raise DomainError("Select an immutable submitted revision.")
    activation_version = deepcopy(bump_bid_version(doc, "notice_to_proceed_activation", "major"))
    award_id = uid("awd")
    award = {"id": award_id, "revision_id": revision["id"], "ntp_evidence": payload["ntp_evidence"], "ntp_date": payload["ntp_date"],
             "activated_at": now(), "activated_by": actor, "activator_role": role, "awarded_bid_snapshot": deepcopy(revision), "immutable": True,
             "accepted_bid_version": deepcopy(revision.get("bid_version")), "activation_version": activation_version, "reversal_status": "pending_policy"}
    doc["award"] = award
    allocations = []
    for line in revision["estimate"]["lines"]:
        if not line.get("included", True):
            continue
        allocations.append({"id": uid("cal"), "award_id": award_id, "source_estimate_line_id": line["id"], "code": line["code"], "description": line["description"],
                            "original_cost": line["direct_cost"], "current_estimated_cost": line["direct_cost"], "labor_hours": next((x.get("calculated_hours", "0") for x in revision["source_snapshot"]["labor_estimates"] if x["id"] in [l.get("source_id") for l in line.get("lineage", [])]), "0"),
                            "contract_value": line["selling_value"], "reestimate_history": [], "procurement_status": "not_started"})
    doc["contract_allocations"] = allocations
    doc["project"]["lifecycle_state"] = "awarded_activated"
    audit(doc, actor, role, "award", award_id, "activate", None, {"revision_id": revision["id"], "ntp_date": payload["ntp_date"]}, "Notice to proceed")
    return award


def reestimate_contract(doc: dict, actor: str, role: str, payload: dict) -> dict:
    require(role, "contract")
    line = next((x for x in doc.get("contract_allocations", []) if x["id"] == payload.get("allocation_id")), None)
    if not line:
        raise DomainError("Contract allocation line was not found.")
    if not payload.get("reason", "").strip():
        raise DomainError("A re-estimate reason is required.")
    prior = line["current_estimated_cost"]
    line["current_estimated_cost"] = money_string(dec(payload.get("new_cost"), Decimal(0)) or Decimal(0))
    entry = {"id": uid("reh"), "prior_value": prior, "new_value": line["current_estimated_cost"], "variance": money_string((dec(line["current_estimated_cost"], Decimal(0)) or Decimal(0)) - (dec(prior, Decimal(0)) or Decimal(0))),
             "reason": payload["reason"], "actor": actor, "role": role, "timestamp": now(), "approval_status": "pending_policy"}
    line["reestimate_history"].append(entry)
    bump_bid_version(doc, "contract_reestimate")
    audit(doc, actor, role, "contract_allocation", line["id"], "reestimate", prior, line["current_estimated_cost"], payload["reason"])
    return line


def create_change_order(doc: dict, config: dict, actor: str, role: str, payload: dict) -> dict:
    require(role, "change_order")
    if not doc.get("award"):
        raise DomainError("Activate an awarded revision before creating a change order.")
    one, two = config["pco"]["markup_one"], config["pco"]["markup_two"]
    taxable, tax_rate = _tax(doc, config)
    lines, total_cost, total_price = [], Decimal(0), Decimal(0)
    for raw in payload.get("cost_lines", []):
        result = sequential_pco(raw.get("cost"), one, two, tax_rate, taxable and bool(raw.get("taxable", False)))
        lines.append({"id": uid("pcl"), "description": raw.get("description", ""), "quantity": raw.get("quantity"), "unit": raw.get("unit"), "taxable": bool(raw.get("taxable", False)), **jsonable(result)})
        total_cost += result["cost"]
        total_price += result["customer_price"]
    order = {"id": uid("pco"), "identifier": payload.get("identifier", ""), "description": payload.get("description", ""), "status": "draft", "cost_lines": lines,
             "markup_configuration_id": config["id"], "markup_one_restricted": one, "markup_two_restricted": two, "total_cost": money_string(total_cost), "customer_price": money_string(total_price),
             "margin": str(Decimal(0) if total_price == 0 else (total_price - total_cost) / total_price), "approval": {"status": "pending_policy"}, "contract_effect": "not_applied", "created_at": now(), "created_by": actor}
    doc.setdefault("change_orders", []).append(order)
    bump_bid_version(doc, "change_order_create")
    audit(doc, actor, role, "change_order", order["id"], "create", None, {"identifier": order["identifier"], "customer_price": order["customer_price"]}, payload.get("reason", "Create PCO"))
    return order


def update_change_order_status(doc: dict, actor: str, role: str, order_id: str, payload: dict) -> dict:
    require(role, "change_order")
    order = next((x for x in doc.get("change_orders", []) if x["id"] == order_id), None)
    if not order:
        raise DomainError("Change order was not found.")
    status = payload.get("status")
    if status not in {"draft", "submitted", "approved", "rejected"}:
        raise DomainError("Change-order status must be draft, submitted, approved, or rejected.")
    if order.get("contract_effect") == "applied" and status != "approved":
        raise DomainError("An applied change order cannot be rejected or returned to draft without the pending correction/reversal policy.")
    if status == "approved" and not payload.get("pending_policy_acknowledged"):
        raise DomainError("Approval authority is pending. Explicitly acknowledge the pending policy before recording approval and contract effect.")
    prior = {"status": order.get("status"), "approval": deepcopy(order.get("approval")), "contract_effect": order.get("contract_effect")}
    order["status"] = status
    order["approval"] = {"status": "recorded_pending_policy" if status == "approved" else status, "actor": actor, "role": role, "timestamp": now(), "reason": payload.get("reason", "")}
    if status == "approved" and order.get("contract_effect") != "applied":
        allocation = {"id": uid("cal"), "award_id": doc["award"]["id"], "source_change_order_id": order["id"], "source_estimate_line_id": None,
                      "code": order.get("identifier") or "PCO", "description": order.get("description") or "Approved change order",
                      "original_cost": "0.00", "current_estimated_cost": order["total_cost"], "labor_hours": "0",
                      "contract_value": order["customer_price"], "reestimate_history": [], "procurement_status": "not_started", "allocation_type": "approved_change_order"}
        doc.setdefault("contract_allocations", []).append(allocation)
        order["contract_effect"] = "applied"
        order["contract_allocation_id"] = allocation["id"]
    bump_bid_version(doc, "change_order_status")
    audit(doc, actor, role, "change_order", order["id"], "status_change", prior,
          {"status": order["status"], "approval": order["approval"], "contract_effect": order["contract_effect"]}, payload.get("reason", "Change-order status"))
    return order


def save_sov(doc: dict, actor: str, role: str, payload: dict) -> dict:
    require(role, "sov")
    allocation = next((x for x in doc.get("contract_allocations", []) if x["id"] == payload.get("allocation_id")), None)
    if not allocation:
        raise DomainError("Contract allocation line was not found.")
    line = next((x for x in doc.get("sov_lines", []) if x.get("id") == payload.get("id")), None)
    prior = deepcopy(line) if line else None
    if line is None:
        line = {"id": uid("sov"), "allocation_id": allocation["id"], "revision_history": []}
        doc.setdefault("sov_lines", []).append(line)
    components = payload.get("components", [])
    own_values = sov_values(allocation["contract_value"], components)
    line.update({"description": payload.get("description", allocation["description"]), "components": components,
                 "scheduled_value": jsonable(own_values["scheduled_value"]), "allocation_percentage": jsonable(own_values["allocation_percentage"])})
    related = [x for x in doc.get("sov_lines", []) if x.get("allocation_id") == allocation["id"]]
    aggregate = sum((dec(x.get("scheduled_value"), Decimal(0)) or Decimal(0) for x in related), Decimal(0))
    aggregate_values = sov_values(allocation["contract_value"], [aggregate])
    for related_line in related:
        related_line.update({"allocation_scheduled_total": jsonable(aggregate_values["scheduled_value"]), "remaining_value": jsonable(aggregate_values["remaining_value"]),
                             "status": aggregate_values["status"], "approval_status": "blocked_overallocation" if aggregate_values["status"] == "overallocated" else ("pending_underallocation_treatment" if aggregate_values["status"] == "underallocated" else "ready")})
    line["revision_history"].append({"timestamp": now(), "actor": actor, "role": role, "prior": prior, "new": {"components": line["components"],
                                      "scheduled_value": line["scheduled_value"], "allocation_scheduled_total": line["allocation_scheduled_total"],
                                      "remaining_value": line["remaining_value"], "status": line["status"]}})
    bump_bid_version(doc, "sov_change")
    audit(doc, actor, role, "sov_line", line["id"], "save", prior, {"scheduled_value": line["scheduled_value"], "allocation_scheduled_total": line["allocation_scheduled_total"], "status": line["status"]}, payload.get("reason", "SOV allocation"))
    return line


def provisional_closeout(doc: dict, actor: str, role: str, payload: dict) -> dict:
    require(role, "closeout")
    if not doc.get("award"):
        raise DomainError("An activated award is required.")
    record = {"id": uid("clo"), "status": "provisional_pending_policy", "recorded_at": now(), "recorded_by": actor,
              "completion_evidence": payload.get("completion_evidence", ""), "final_contract_value": payload.get("final_contract_value"),
              "final_allocation": payload.get("final_allocation"), "unresolved_items": payload.get("unresolved_items", []), "approval": "pending_policy",
              "archive_location": None, "retention_disposition": "pending_policy", "notice": "This is provisional and does not assert controlled closeout completion."}
    doc["closeout"] = record
    doc["project"]["lifecycle_state"] = "provisional_closeout"
    bump_bid_version(doc, "provisional_closeout")
    audit(doc, actor, role, "closeout", record["id"], "provisional_closeout", None, record, payload.get("reason", "Provisional closeout"))
    return record


def job_data(doc: dict) -> dict:
    return {"schema": "murphywindow.job-data", "version": INTERCHANGE_VERSION, "generated_at": now(), "project": doc["project"], "contacts": doc.get("contacts", []),
            "quotes": doc.get("quotes", []), "bid": doc.get("working_estimate", {}), "submissions": doc.get("submissions", []), "award": doc.get("award"),
            "contract": doc.get("contract_allocations", []), "bid_tabulation": doc.get("bid_tabulations", [])}


def redact(doc: dict, role: str) -> dict:
    value = deepcopy(doc)
    if role not in PERMISSIONS["view_restricted_pco"]:
        for order in value.get("change_orders", []):
            order.pop("markup_one_restricted", None)
            order.pop("markup_two_restricted", None)
            for line in order.get("cost_lines", []):
                line.pop("stage_one", None)
                line.pop("stage_two", None)
    return value
