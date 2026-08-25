"""Canonical Base-plus-delta alternates.

Base remains the only primary estimate. Alternate records retain additions,
removals, and explicit field overrides; effective states are materialized only
for authoritative calculation, comparison, and immutable snapshotting.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any, Callable

from .calculations import dec, normalize_code, split_variant
from .schema import now, uid
from .services_shared import money_string


COLLECTIONS = ("quotes", "takeoff_sections", "doors", "equipment", "borrowed_lites", "labor_estimates", "travel_estimates", "frames")
COMPARISON_COLLECTIONS = ("quotes", "takeoff_sections", "frames", "doors", "equipment", "borrowed_lites", "labor_estimates", "travel_estimates")
LABELS = {"quotes": "Quotes", "takeoff_sections": "Installation Materials", "doors": "Doors", "equipment": "Equipment",
          "borrowed_lites": "Borrowed Lites", "labor_estimates": "Labor", "travel_estimates": "Travel", "frames": "Frame Takeoff"}


def new_alternate(document: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    sequence = max([int(row.get("sequence", 0)) for row in document.get("alternates", [])] or [0]) + 1
    key = f"ALT{sequence}"
    return {"id": uid("alt"), "sequence": sequence, "key": key, "name": str(name or "").strip(),
            "customer_description": "", "created_at": now(), "base_created_revision": document.get("project", {}).get("revision", 0),
            "changes": {}, "calculated": {}}


def alternate_label(alternate: dict[str, Any]) -> str:
    """Return customer-facing text without exposing the stable ALT key."""
    sequence = int(alternate.get("sequence") or 1)
    base = f"Alternate {sequence}"
    name = str(alternate.get("name") or "").strip()
    return base if not name or name == base else f"{base} — {name}"


def _bucket(alternate: dict[str, Any], collection: str) -> dict[str, Any]:
    if collection not in COLLECTIONS:
        raise ValueError(f"Unsupported alternate source area: {collection}")
    return alternate.setdefault("changes", {}).setdefault(collection, {"added": [], "removed": [], "overrides": {}})


def set_override(alternate: dict[str, Any], collection: str, record_id: str, field: str,
                 base_value: Any, value: Any) -> None:
    bucket = _bucket(alternate, collection)
    bucket.setdefault("overrides", {}).setdefault(str(record_id), {})[str(field)] = {
        "base_value": deepcopy(base_value), "value": deepcopy(value), "set_at": now(),
    }


def reset_override(alternate: dict[str, Any], collection: str, record_id: str, field: str) -> None:
    bucket = _bucket(alternate, collection)
    fields = bucket.get("overrides", {}).get(str(record_id), {})
    fields.pop(str(field), None)
    if not fields:
        bucket.get("overrides", {}).pop(str(record_id), None)


def add_record(alternate: dict[str, Any], collection: str, record: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(record)
    item.setdefault("id", uid({"quotes": "quo", "takeoff_sections": "sec", "doors": "dor", "equipment": "eqp",
                               "borrowed_lites": "brl", "labor_estimates": "lbr", "travel_estimates": "trv", "frames": "frm"}[collection]))
    _bucket(alternate, collection).setdefault("added", []).append(item)
    return item


def remove_record(alternate: dict[str, Any], collection: str, record_id: str) -> None:
    bucket = _bucket(alternate, collection)
    if str(record_id) not in bucket.setdefault("removed", []):
        bucket["removed"].append(str(record_id))


def _find_frame(document: dict[str, Any], record_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for section in document.get("takeoff_sections", []):
        row = next((item for item in section.get("lines", []) if str(item.get("id")) == str(record_id)), None)
        if row:
            return section, row
    return None, None


def _get_record(document: dict[str, Any], collection: str, record_id: str) -> dict[str, Any] | None:
    if collection == "frames":
        return _find_frame(document, record_id)[1]
    return next((row for row in document.get(collection, []) if str(row.get("id")) == str(record_id)), None)


def _set_field(record: dict[str, Any], path: str, value: Any) -> None:
    target = record
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = deepcopy(value)


def _get_field(record: dict[str, Any] | None, path: str) -> Any:
    value: Any = record
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def materialize(document: dict[str, Any], alternate: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    effective = deepcopy(document)
    effective["alternates"] = []
    effective.get("working_estimate", {}).pop("alternate_results", None)
    conflicts: list[dict[str, Any]] = []
    changes = alternate.get("changes", {})
    # Materialization order is structural, never dependent on the order in
    # which an estimator happened to make edits. Sections must exist before
    # ALT-only frames are placed into them.
    for collection in COLLECTIONS:
        bucket = changes.get(collection, {})
        if not isinstance(bucket, dict) or not bucket:
            continue
        removed = {str(value) for value in bucket.get("removed", [])}
        if collection == "frames":
            for section in effective.get("takeoff_sections", []):
                section["lines"] = [row for row in section.get("lines", []) if str(row.get("id")) not in removed]
            for row in bucket.get("added", []):
                section_id = row.get("section_id")
                section = next((item for item in effective.get("takeoff_sections", []) if item.get("id") == section_id), None)
                if section is None and effective.get("takeoff_sections"):
                    section = effective["takeoff_sections"][0]
                if section is not None:
                    added = deepcopy(row); added.pop("section_id", None); section.setdefault("lines", []).append(added)
        else:
            effective[collection] = [row for row in effective.get(collection, []) if str(row.get("id")) not in removed]
            effective[collection].extend(deepcopy(bucket.get("added", [])))
        for record_id, fields in bucket.get("overrides", {}).items():
            current = _get_record(effective, collection, record_id)
            if current is None:
                conflicts.append({"collection": collection, "record_id": record_id, "field": None, "reason": "base_record_missing"})
                continue
            for field, override in fields.items():
                stored = override if isinstance(override, dict) else {"base_value": None, "value": override}
                current_value = _get_field(current, field)
                if current_value != stored.get("base_value"):
                    conflicts.append({"collection": collection, "record_id": record_id, "field": field,
                                      "original_base": deepcopy(stored.get("base_value")), "current_base": deepcopy(current_value),
                                      "alternate_override": deepcopy(stored.get("value")), "reason": "base_changed_since_override"})
                _set_field(current, field, stored.get("value"))
    # Line markup decisions are deltas against the current Base override map.
    # Clearing an Alternate entry therefore resumes current Base inheritance.
    markup_changes = changes.get("line_markup_overrides", {})
    for source_key, stored in markup_changes.get("overrides", {}).items():
        override = stored.get("value") if isinstance(stored, dict) and "value" in stored else stored
        if override is None:
            effective.setdefault("working_estimate", {}).setdefault("component_markup_overrides", {}).pop(source_key, None)
        else:
            effective.setdefault("working_estimate", {}).setdefault("component_markup_overrides", {})[source_key] = deepcopy(override)
    quote_changes = alternate.get("changes", {}).get("quotes", {})
    if quote_changes:
        quotes = {str(row.get("id")): row for row in effective.get("quotes", [])}
        touched_codes: dict[str, set[str]] = {}
        for row in quote_changes.get("added", []):
            if row.get("used") and row.get("code"):
                touched_codes.setdefault(str(row["code"]), set()).add(str(row.get("id")))
        for record_id, fields in quote_changes.get("overrides", {}).items():
            used = fields.get("used")
            row = quotes.get(str(record_id))
            if used is not None and row and row.get("code"):
                value = used.get("value") if isinstance(used, dict) else used
                selected = touched_codes.setdefault(str(row["code"]), set())
                if value:
                    selected.add(str(record_id))
        removed = {str(value) for value in quote_changes.get("removed", [])}
        selection_map = effective.setdefault("working_estimate", {}).setdefault("quote_selection_by_code", {})
        for code, explicit_ids in touched_codes.items():
            inherited = selection_map.get(code, {})
            selected = set(inherited.get("selected_quote_ids", [])) if isinstance(inherited, dict) else set()
            selected.update(explicit_ids)
            for record_id, fields in quote_changes.get("overrides", {}).items():
                used = fields.get("used")
                row = quotes.get(str(record_id))
                if used is not None and row and normalize_code(row.get("code")) == normalize_code(code):
                    value = used.get("value") if isinstance(used, dict) else used
                    if not value:
                        selected.discard(str(record_id))
            selection_map[code] = {"mode": "manual", "selected_quote_ids": sorted(selected - removed),
                                   "source": "alternate_explicit_selection"}
    return effective, conflicts


def _record_label(collection: str, record: dict[str, Any] | None) -> str:
    row = record or {}
    label = row.get("mark") or row.get("vendor") or row.get("door_number") or row.get("description") or row.get("name")
    if label:
        return str(label)
    if collection == "labor_estimates":
        return f"{row.get('labor_type') or 'Labor'} labor"
    if collection == "travel_estimates":
        return "Travel allowance"
    singular = {"quotes": "Quote", "takeoff_sections": "Frame section", "doors": "Door", "equipment": "Equipment item",
                "borrowed_lites": "Borrowed lite", "frames": "Frame line"}.get(collection, "Record")
    return f"{singular} {row.get('code')}" if row.get("code") else singular


def scope_of_change(document: dict[str, Any], alternate: dict[str, Any]) -> list[dict[str, Any]]:
    groups = []
    for collection in COLLECTIONS:
        bucket = alternate.get("changes", {}).get(collection, {})
        items = []
        for record_id in bucket.get("removed", []):
            row = _get_record(document, collection, record_id)
            label = _record_label(collection, row)
            if collection == "frames": items.append(f"Removed {label} frames (Qty {(row or {}).get('quantity') or 0})")
            else: items.append(f"Removed {label}")
        for row in bucket.get("added", []):
            label = _record_label(collection, row)
            if collection == "frames": items.append(f"Added {label} frames (Qty {row.get('quantity') or 0})")
            else: items.append(f"Added {label}")
        for record_id, fields in bucket.get("overrides", {}).items():
            row = _get_record(document, collection, record_id)
            label = _record_label(collection, row)
            for field, override in fields.items():
                change = override if isinstance(override, dict) else {"base_value": None, "value": override}
                old, new = change.get("base_value"), change.get("value")
                if collection == "frames" and field == "quantity":
                    direction = "reduced" if dec(new, Decimal(0)) < dec(old, Decimal(0)) else "increased"
                    items.append(f"{label} quantity {direction} from {old} to {new}")
                elif collection == "frames" and field == "caulking_passes":
                    items.append(f"{label} caulking passes changed from {old} to {new}")
                elif collection == "labor_estimates" and field in {"man_hours", "calculated_man_hours"}:
                    difference = dec(new, Decimal(0)) - dec(old, Decimal(0))
                    direction = "increased" if difference > 0 else "reduced"
                    items.append(f"{label} {direction} by {abs(difference)} man-hours")
                elif field == "installation_material_ids":
                    removed = sorted(set(old or []) - set(new or []))
                    added = sorted(set(new or []) - set(old or []))
                    if removed: items.append(f"{', '.join(removed)} excluded from {label}")
                    if added: items.append(f"{', '.join(added)} added to {label}")
                else:
                    items.append(f"{label} {field.replace('_', ' ')} changed from {old} to {new}")
        if items:
            groups.append({"area": LABELS[collection], "changes": items})
    markup_items = []
    for source_key, stored in alternate.get("changes", {}).get("line_markup_overrides", {}).get("overrides", {}).items():
        value = stored.get("value") if isinstance(stored, dict) else stored
        if value:
            mode = value.get("mode") if isinstance(value, dict) else "percentage"
            amount = value.get("value", value.get("rate")) if isinstance(value, dict) else value
            markup_items.append(f"{source_key} manual markup changed to {mode} {amount}")
    if markup_items:
        groups.append({"area": "Line Markup", "changes": markup_items})
    return groups


def _commercial_groups(lines: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Decimal]]:
    grouped: dict[tuple[str, str], dict[str, Decimal]] = {}
    for line in lines:
        if line.get("included") is False:
            continue
        _, base = split_variant(line.get("code", "")); key = (normalize_code(base), str(line.get("category") or "Other"))
        item = grouped.setdefault(key, {"direct_cost": Decimal(0), "selling_value": Decimal(0)})
        item["direct_cost"] += dec(line.get("direct_cost"), Decimal(0)) or Decimal(0)
        item["selling_value"] += dec(line.get("selling_value"), Decimal(0)) or Decimal(0)
    return grouped


def _comparison_change_steps(alternate: dict[str, Any]) -> list[dict[str, Any]]:
    """Return stable record-level delta steps for exact, summable UI impacts."""
    changes = alternate.get("changes", {})
    steps: list[dict[str, Any]] = []
    for collection in COMPARISON_COLLECTIONS:
        bucket = changes.get(collection, {})
        if not isinstance(bucket, dict):
            continue
        records: dict[str, dict[str, Any]] = {}
        for record_id in bucket.get("removed", []):
            key = str(record_id)
            records.setdefault(key, {"added": [], "removed": [], "overrides": {}})["removed"].append(key)
        for row in bucket.get("added", []):
            key = str(row.get("id") or f"added-{len(records)}")
            records.setdefault(key, {"added": [], "removed": [], "overrides": {}})["added"].append(deepcopy(row))
        for record_id, fields in bucket.get("overrides", {}).items():
            key = str(record_id)
            records.setdefault(key, {"added": [], "removed": [], "overrides": {}})["overrides"][key] = deepcopy(fields)
        for record_id, payload in records.items():
            steps.append({"collection": collection, "record_id": record_id, "payload": payload})
    markup = changes.get("line_markup_overrides", {})
    for source_key, stored in (markup.get("overrides", {}) if isinstance(markup, dict) else {}).items():
        steps.append({"collection": "line_markup_overrides", "record_id": str(source_key),
                      "payload": {"overrides": {str(source_key): deepcopy(stored)}}})
    return steps


def _comparison_impacts(document: dict[str, Any], alternate: dict[str, Any], configuration: dict[str, Any],
                        calculator: Callable[..., dict[str, Any]], final_selling_value: Decimal) -> list[dict[str, str]]:
    """Attribute authoritative selling-value movement in a telescoping sequence."""
    steps = _comparison_change_steps(alternate)
    if not steps:
        return []
    cumulative = {"changes": {}}
    prior = dec(document.get("working_estimate", {}).get("totals", {}).get("selling_value"), Decimal(0)) or Decimal(0)
    impacts: list[dict[str, str]] = []
    for index, step in enumerate(steps):
        collection, payload = step["collection"], step["payload"]
        if collection == "line_markup_overrides":
            cumulative["changes"].setdefault(collection, {"overrides": {}})["overrides"].update(deepcopy(payload["overrides"]))
        else:
            target = cumulative["changes"].setdefault(collection, {"added": [], "removed": [], "overrides": {}})
            target["added"].extend(deepcopy(payload["added"]))
            target["removed"].extend(deepcopy(payload["removed"]))
            target["overrides"].update(deepcopy(payload["overrides"]))
        if index == len(steps) - 1:
            current = final_selling_value
        else:
            effective, _ = materialize(document, cumulative)
            calculator(effective, configuration, include_alternates=False)
            current = dec(effective.get("working_estimate", {}).get("totals", {}).get("selling_value"), Decimal(0)) or Decimal(0)
        impacts.append({"collection": collection, "record_id": step["record_id"],
                        "selling_value_delta": money_string(current - prior)})
        prior = current
    return impacts


def calculate_alternates(document: dict[str, Any], configuration: dict[str, Any], calculator: Callable[..., dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    base_lines = document.get("working_estimate", {}).get("lines", [])
    base_groups = _commercial_groups(base_lines)
    base_totals = document.get("working_estimate", {}).get("totals", {})
    for alternate in document.get("alternates", []):
        effective, conflicts = materialize(document, alternate)
        calculator(effective, configuration, include_alternates=False)
        effective_groups = _commercial_groups(effective.get("working_estimate", {}).get("lines", []))
        impacts = []
        for (code, category) in sorted(set(base_groups) | set(effective_groups)):
            before, after = base_groups.get((code, category), {}), effective_groups.get((code, category), {})
            cost_delta = (after.get("direct_cost", Decimal(0)) - before.get("direct_cost", Decimal(0)))
            value_delta = (after.get("selling_value", Decimal(0)) - before.get("selling_value", Decimal(0)))
            if cost_delta or value_delta:
                impacts.append({"code": code, "category": category, "direct_cost_delta": money_string(cost_delta),
                                "selling_value_delta": money_string(value_delta)})
        effective_totals = effective.get("working_estimate", {}).get("totals", {})
        direct_delta = (dec(effective_totals.get("direct_cost"), Decimal(0)) or Decimal(0)) - (dec(base_totals.get("direct_cost"), Decimal(0)) or Decimal(0))
        value_delta = (dec(effective_totals.get("selling_value"), Decimal(0)) or Decimal(0)) - (dec(base_totals.get("selling_value"), Decimal(0)) or Decimal(0))
        comparison_impacts = _comparison_impacts(document, alternate, configuration, calculator,
                                                 dec(effective_totals.get("selling_value"), Decimal(0)) or Decimal(0))
        calculated = {"scope_of_change": scope_of_change(document, alternate), "conflicts": conflicts,
                      "direct_cost_delta": money_string(direct_delta), "selling_value_delta": money_string(value_delta),
                      "classification": "add" if value_delta > 0 else "deduct" if value_delta < 0 else "zero",
                      "effective_totals": deepcopy(effective_totals), "cost_code_impacts": impacts,
                      "comparison_impacts": comparison_impacts,
                      # A calculated projection, never an independently editable estimate.
                      # This lets every commercial workspace render the effective ALT
                      # through the same authoritative Bid outputs as Base.
                      "effective_estimate": deepcopy({key: effective.get("working_estimate", {}).get(key)
                                                       for key in ("lines", "cost_code_summaries", "totals", "validation")}),
                      # Read-only calculated projection for the shared Frame workspace.
                      # Canonical ALT storage remains inheritance plus explicit deltas.
                      "effective_takeoff_sections": deepcopy(effective.get("takeoff_sections", [])),
                      # Read-only row projections let the shared tabular workspaces
                      # retain their authoritative calculated columns in Alternates.
                      "effective_equipment": deepcopy(effective.get("equipment", [])),
                      "effective_borrowed_lites": deepcopy(effective.get("borrowed_lites", [])),
                      "effective_labor_estimates": deepcopy(effective.get("labor_estimates", []))}
        alternate["calculated"] = calculated
        results.append(calculated)
    document.setdefault("working_estimate", {})["alternate_results"] = deepcopy(results)
    return results
