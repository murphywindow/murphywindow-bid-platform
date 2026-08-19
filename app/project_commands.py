"""Server-side guards and canonical Cost Code project commands."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from .calculations import normalize_code, split_variant
from .schema import CONTRACT_TYPES, PROJECT_TYPES, WAGE_TYPES, now, uid
from .services import DomainError


EDITABLE_COLLECTIONS = (
    "contacts", "cost_codes", "quotes", "takeoff_sections", "doors",
    "hardware_assignments", "equipment", "borrowed_lites", "labor_estimates",
    "travel_estimates", "alternates", "bid_tabulations",
)

SOURCE_CODE_COLLECTIONS = (
    "quotes", "takeoff_sections", "doors", "hardware_assignments", "equipment",
    "borrowed_lites", "labor_estimates", "travel_estimates",
)


def _base_code(value: Any) -> str:
    _, base = split_variant(str(value or ""))
    return normalize_code(base)


def _row_code(row: dict[str, Any]) -> str:
    return _base_code(row.get("code") or row.get("cost_code"))


def _is_ui_draft(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    row_id = str(row.get("id") or "")
    return bool(
        row.get("_ui_only")
        or row.get("ui_only")
        or row.get("row_kind") == "draft"
        or row_id.startswith("draft-")
    )


def _meaningful_without_id(collection: str, row: dict[str, Any]) -> bool:
    ignored = {
        "id", "calculated", "created_at", "updated_at", "active", "status",
        "deduct", "taxable", "duration_unit", "missing_quantity_acknowledged",
        "stale_acknowledged", "installation_material_ids", "caulking_passes",
        "used", "tax_included", "credit_type", "credit_value", "surcharge_type",
        "surcharge_value", "used_selection_mode", "labor_type", "category",
        "hours_per_worker_per_day", "workdays_per_week", "origin", "source_status",
    }
    # A Quote group's implicit code does not make its working row canonical.
    if collection == "quotes":
        ignored.add("code")
    for key, value in row.items():
        if key in ignored or key.startswith("calculated_"):
            continue
        if value not in (None, "", False, [], {}):
            return True
    return False


def strip_ui_working_rows(document: dict[str, Any]) -> dict[str, Any]:
    """Remove only browser working rows; preserve identified historical blanks."""
    for collection in EDITABLE_COLLECTIONS:
        rows = document.get(collection)
        if not isinstance(rows, list):
            continue
        retained = []
        for row in rows:
            if _is_ui_draft(row):
                continue
            if isinstance(row, dict) and not row.get("id") and not _meaningful_without_id(collection, row):
                continue
            if collection == "takeoff_sections" and isinstance(row, dict):
                lines = row.get("lines")
                if isinstance(lines, list):
                    row["lines"] = [
                        line for line in lines
                        if not _is_ui_draft(line)
                        and not (isinstance(line, dict) and not line.get("id") and not _meaningful_without_id("frame_lines", line))
                    ]
            retained.append(row)
        document[collection] = retained
    return document


def preserve_quote_square_feet_intent(incoming: dict[str, Any], current: dict[str, Any]) -> None:
    """Mark estimator-entered Quote area as manual across stale client saves."""
    prior_by_id = {
        row.get("id"): row for row in current.get("quotes", []) if row.get("id")
    }
    for row in incoming.get("quotes", []):
        prior = prior_by_id.get(row.get("id"))
        value = row.get("square_feet")
        if prior is None:
            if value not in (None, "") and row.get("square_feet_source") in (None, "", "unassigned"):
                row["square_feet_source"] = "manual"
            continue
        changed = str(value if value is not None else "") != str(
            prior.get("square_feet") if prior.get("square_feet") is not None else ""
        )
        if changed:
            row["square_feet_source"] = "manual" if value not in (None, "") else "unassigned"
        elif prior.get("square_feet_source") == "manual":
            # A save response may settle while the user is already editing the
            # next cell. Preserve the server's manual provenance even if that
            # still-dirty browser snapshot contains the older source flag.
            row["square_feet_source"] = "manual"


def refresh_labor_rate_selection(incoming: dict[str, Any], current: dict[str, Any]) -> None:
    """Invalidate only working Labor snapshots whose controlling choice changed."""
    incoming_project = incoming.get("project", {})
    current_project = current.get("project", {})
    project_rate_context_changed = any(
        incoming_project.get(field) != current_project.get(field)
        for field in ("wage_type", "wage_data_id")
    )
    prior_by_id = {
        row.get("id"): row for row in current.get("labor_estimates", []) if row.get("id")
    }
    for row in incoming.get("labor_estimates", []):
        prior = prior_by_id.get(row.get("id"))
        labor_type_changed = prior is not None and str(
            row.get("labor_type") or row.get("category") or ""
        ).casefold() != str(
            prior.get("labor_type") or prior.get("category") or ""
        ).casefold()
        if project_rate_context_changed or labor_type_changed:
            row["controlled_rate_snapshot"] = None


def _controlled_status(value: Any, allowed: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    if not text:
        return "missing"
    return "current" if text in allowed else "legacy_unsupported"


def _validate_local_deadline(value: Any, prior: Any) -> None:
    text = str(value or "").strip()
    if not text or text == str(prior or ""):
        return
    if "T" not in text or text.endswith("Z"):
        raise DomainError(
            "Bid Due Date must include a local date and time without a timezone shift.",
            "invalid_bid_due_date",
        )
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DomainError("Bid Due Date is not a valid local date and time.", "invalid_bid_due_date") from exc
    if parsed.tzinfo is not None:
        raise DomainError("Bid Due Date must remain local and must not include a timezone.", "invalid_bid_due_date")


def _controlled_reference(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        normalize_code(str(row.get("normalized_code") or row.get("display_code") or "")): row
        for row in config.get("csi_references", [])
        if row.get("active", True)
    }


def validate_project_inputs(incoming: dict[str, Any], current: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Enforce current controlled inputs while preserving unchanged legacy values."""
    project = incoming.setdefault("project", {})
    prior_project = current.get("project", {})
    for field, status_field, allowed in (
        ("project_type", "project_type_status", PROJECT_TYPES),
        ("contract_type", "contract_type_status", CONTRACT_TYPES),
        ("wage_type", "wage_type_status", WAGE_TYPES),
    ):
        value = project.get(field)
        prior = prior_project.get(field)
        status = _controlled_status(value, allowed)
        if status == "legacy_unsupported" and str(value or "") != str(prior or ""):
            raise DomainError(
                f"{field.replace('_', ' ').title()} must use a current controlled value.",
                f"invalid_{field}",
                [{"allowed": list(allowed), "value": value}],
            )
        project[status_field] = status
    _validate_local_deadline(project.get("bid_due_date"), prior_project.get("bid_due_date"))

    references = _controlled_reference(config)
    prior_by_id = {row.get("id"): row for row in current.get("cost_codes", []) if row.get("id")}
    for row in incoming.setdefault("cost_codes", []):
        code = str(row.get("code") or "").strip()
        if not code:
            raise DomainError("Cost Code cannot be blank once its row is saved.", "invalid_cost_code")
        prior = prior_by_id.get(row.get("id"))
        unchanged_legacy = prior is not None and _base_code(prior.get("code")) == _base_code(code)
        authorized_custom = bool(
            (row.get("is_custom") or row.get("custom_status") == "authorized_custom")
            and prior is not None
            and prior.get("custom_status") == "authorized_custom"
        )
        reference = references.get(_base_code(code))
        if reference is None and not unchanged_legacy and not authorized_custom:
            raise DomainError(
                "Select a controlled Cost Code or use the protected Add Custom Code action.",
                "invalid_cost_code",
                [{"row_id": row.get("id"), "value": code}],
            )
        if reference is not None and not row.get("is_custom"):
            variant, _ = split_variant(code)
            display_code = reference.get("display_code") or code
            row["code"] = f"{variant}-{display_code}" if variant else display_code
            row["reference_id"] = reference.get("id")
            row["reference_configuration_id"] = config.get("id")
            row["controlled_status"] = "controlled"
            if not str(row.get("description") or "").strip():
                row["description"] = reference.get("description") or ""
        elif unchanged_legacy and reference is None and not authorized_custom:
            row.setdefault("controlled_status", "legacy_unsupported")

    project_codes = {_base_code(row.get("code")) for row in incoming.get("cost_codes", []) if row.get("code")}
    for collection in SOURCE_CODE_COLLECTIONS:
        prior_by_id = {
            row.get("id"): row for row in current.get(collection, []) if row.get("id")
        }
        for row in incoming.get(collection, []):
            code = row.get("code") or row.get("cost_code")
            if not str(code or "").strip() or _base_code(code) in project_codes:
                continue
            prior = prior_by_id.get(row.get("id"))
            unchanged_legacy = prior is not None and _base_code(
                prior.get("code") or prior.get("cost_code")
            ) == _base_code(code)
            if unchanged_legacy:
                row.setdefault("cost_code_status", "legacy_unsupported")
                continue
            raise DomainError(
                f"{collection.replace('_', ' ').title()} must use a Cost Code already present in this project.",
                "invalid_source_cost_code",
                [{"collection": collection, "row_id": row.get("id"), "value": code}],
            )

    incoming["schema_version"] = current.get("schema_version", incoming.get("schema_version"))
    return incoming


DEPENDENCY_COLLECTIONS = (
    "quotes", "takeoff_sections", "doors", "hardware_assignments", "equipment",
    "borrowed_lites", "labor_estimates", "travel_estimates", "alternates",
)


def cost_code_dependencies(document: dict[str, Any], cost_code_id: str) -> dict[str, Any]:
    code_row = next((row for row in document.get("cost_codes", []) if row.get("id") == cost_code_id), None)
    if code_row is None:
        raise DomainError("Cost Code was not found.", "not_found")
    target = _base_code(code_row.get("code"))
    records: list[dict[str, Any]] = []
    removed_door_ids = {
        row.get("id") for row in document.get("doors", []) if _row_code(row) == target and row.get("id")
    }
    for collection in DEPENDENCY_COLLECTIONS:
        for row in document.get(collection, []):
            matches = _row_code(row) == target
            if collection == "hardware_assignments" and row.get("door_id") in removed_door_ids:
                matches = True
            if matches:
                records.append({
                    "collection": collection,
                    "id": row.get("id"),
                    "label": row.get("description") or row.get("name") or row.get("mark") or row.get("vendor") or "",
                })
    return {
        "cost_code_id": cost_code_id,
        "code": code_row.get("code"),
        "description": code_row.get("description"),
        "has_dependencies": bool(records),
        "dependency_count": len(records),
        "dependencies": records,
    }


def remove_cost_code_cascade(document: dict[str, Any], cost_code_id: str) -> dict[str, Any]:
    report = cost_code_dependencies(document, cost_code_id)
    target = _base_code(report["code"])
    removed_ids = {item["id"] for item in report["dependencies"] if item["id"]}
    removed_door_ids = {
        row.get("id") for row in document.get("doors", []) if _row_code(row) == target and row.get("id")
    }
    document["cost_codes"] = [row for row in document.get("cost_codes", []) if row.get("id") != cost_code_id]
    for collection in DEPENDENCY_COLLECTIONS:
        retained = []
        for row in document.get(collection, []):
            matches = _row_code(row) == target
            if collection == "hardware_assignments" and row.get("door_id") in removed_door_ids:
                matches = True
            if not matches:
                retained.append(row)
        document[collection] = retained
    working = document.setdefault("working_estimate", {})
    for key in ("quote_selection_by_code", "borrowed_lite_source_by_code"):
        mapping = working.get(key)
        if isinstance(mapping, dict):
            working[key] = {code: value for code, value in mapping.items() if _base_code(code) != target}
    exclusions = working.get("labor_suggestion_exclusions")
    if isinstance(exclusions, list):
        working["labor_suggestion_exclusions"] = [
            value for value in exclusions
            if _base_code(value.get("code") if isinstance(value, dict) else value) != target
        ]
    overrides = working.get("component_markup_overrides")
    if isinstance(overrides, dict):
        working["component_markup_overrides"] = {
            key: value for key, value in overrides.items()
            if not any(identifier and identifier in str(key) for identifier in removed_ids)
            and not (
                str(key).startswith("borrowed_lite:")
                and _base_code(str(key).split(":", 1)[1]) == target
            )
        }
    report["removed_record_ids"] = sorted(identifier for identifier in removed_ids if identifier)
    return report


def new_custom_cost_code(command: dict[str, Any], actor: str) -> dict[str, Any]:
    return {
        "id": uid("ccd"),
        "code": str(command["code"]).strip(),
        "description": str(command.get("description") or "").strip(),
        "mwd_code": str(command.get("mwd_code") or "").strip(),
        "mwd_description": str(command.get("mwd_description") or "").strip(),
        "deduct": bool(command.get("deduct", False)),
        "status": "active",
        "is_custom": True,
        "custom_status": "authorized_custom",
        "custom_created_by": actor,
        "custom_created_at": now(),
        "reference_id": None,
        "controlled_status": "custom_exception",
    }
