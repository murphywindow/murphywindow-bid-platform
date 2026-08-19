"""Idempotent migrations for active Murphy Window project documents.

Migrations enrich only the current working document.  Immutable estimate
revisions, submissions, proposal artifacts, and awarded snapshots are retained
exactly as stored so a schema upgrade cannot rewrite historical commercial
evidence.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Callable


CURRENT_SCHEMA_VERSION = "1.1.0"

PROJECT_TYPES = (
    "New Construction - Curtainwall",
    "New Construction - Exterior Storefront",
    "New Construction - Interior Storefront",
    "New Construction - Windows",
    "Addition/Renovation - Curtainwall",
    "Addition/Renovation - Exterior Storefront",
    "Addition/Renovation - Interior Storefront",
    "Addition/Renovation - Windows",
    "Repair - Curtainwall",
    "Repair - Exterior Storefront",
    "Repair - Interior Storefront",
    "Repair - Windows",
    "Replacement - Curtainwall",
    "Replacement - Exterior Storefront",
    "Replacement - Interior Storefront",
    "Replacement - Windows",
)
CONTRACT_TYPES = ("Bid to CM/GC", "Bid as GC")


class MigrationError(ValueError):
    pass


def _status(value: Any, allowed: tuple[str, ...]) -> str:
    if value is None or not str(value).strip():
        return "missing"
    return "current" if str(value) in allowed else "legacy_unsupported"


def _deadline_status(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return "missing"
    if len(text) == 10 and text[4:5] == "-" and text[7:8] == "-":
        return "legacy_date_only"
    if "T" in text and not text.endswith("Z") and "+" not in text[10:] and "-" not in text[10:]:
        return "local_datetime"
    return "legacy_unrecognized"


def _decimal_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return format(number, "f")


def _legacy_man_hours(row: dict[str, Any]) -> tuple[str | None, str]:
    override = _decimal_text(row.get("hours_override"))
    if override is not None:
        return override, "legacy_hours_override"
    try:
        quantity = Decimal(str(row["quantity"]))
        crew = Decimal(str(row["crew"]))
        productivity = Decimal(str(row["productivity"]))
        if crew <= 0 or productivity <= 0:
            return None, "unavailable"
        return format(quantity / crew / productivity, "f"), "legacy_productivity_calculation"
    except (KeyError, InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return None, "unavailable"


def _migrate_1_0_0_to_1_1_0(document: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(document)
    project = result.setdefault("project", {})

    project.setdefault("project_type_status", _status(project.get("project_type"), PROJECT_TYPES))
    project.setdefault("contract_type_status", _status(project.get("contract_type"), CONTRACT_TYPES))
    project.setdefault("bid_due_date_status", _deadline_status(project.get("bid_due_date")))

    if "wage_type" not in project:
        prevailing = project.get("prevailing_wage_required")
        project["wage_type"] = "PW" if prevailing is True else ("Non-PW" if prevailing is False else None)
    project.setdefault(
        "wage_type_status",
        "current" if project.get("wage_type") in {"PW", "Non-PW"}
        else ("missing" if not project.get("wage_type") else "legacy_unsupported"),
    )

    # Preserve the legacy freeform address intact. Structured fields remain
    # empty until a person selects a geocoder result or deliberately edits them.
    project.setdefault("address_street", "")
    project.setdefault("address_city", "")
    project.setdefault("address_state", "")
    project.setdefault("county", "")
    project.setdefault("address_match_metadata", None)
    project.setdefault(
        "address_structure_status",
        "legacy_unparsed" if str(project.get("address") or "").strip() else "missing",
    )

    for field in (
        "owner_organization_id", "architect_organization_id", "engineer_organization_id",
        "general_contractor_organization_id", "construction_manager_organization_id",
        "estimator_master_id", "plan_source_master_id",
    ):
        project.setdefault(field, None)

    for contact in result.setdefault("contacts", []):
        contact.setdefault("master_contact_id", None)
        contact.setdefault("master_record_revision", None)
        contact.setdefault("master_edit_scope", None)

    for code in result.setdefault("cost_codes", []):
        code.setdefault("custom_status", "legacy_unclassified")

    working_estimate = result.setdefault("working_estimate", {})
    legacy_selection_modes = working_estimate.get("quote_selection_modes")
    existing_selection = working_estimate.get("quote_selection_by_code")
    selection_by_code = deepcopy(existing_selection) if isinstance(existing_selection, dict) else {}
    if not selection_by_code and isinstance(legacy_selection_modes, dict):
        for code, legacy_entry in legacy_selection_modes.items():
            if isinstance(legacy_entry, dict):
                selection_by_code[code] = deepcopy(legacy_entry)
            else:
                selection_by_code[code] = {
                    "mode": str(legacy_entry or "automatic"),
                    "selected_quote_ids": [],
                    "source": "migrated_quote_selection_modes",
                }
    for code, entry in list(selection_by_code.items()):
        if isinstance(entry, str):
            selection_by_code[code] = {
                "mode": entry,
                "selected_quote_ids": [],
                "source": "migrated_quote_selection_modes",
            }
    working_estimate["quote_selection_by_code"] = selection_by_code
    used_by_code: dict[str, list[str]] = {}
    for quote in result.setdefault("quotes", []):
        quote.setdefault("credit_type", None)
        quote.setdefault("credit_value", None)
        if "surcharge_type" not in quote:
            legacy_surcharge = quote.get("surcharge_percent")
            quote["surcharge_type"] = "percentage" if legacy_surcharge not in (None, "") else None
            quote["surcharge_value"] = legacy_surcharge
        else:
            quote.setdefault("surcharge_value", None)
        quote.setdefault("square_feet", None)
        quote.setdefault("square_feet_source", "unassigned")
        code = str(quote.get("code") or "").strip()
        if code and quote.get("used") and quote.get("id"):
            used_by_code.setdefault(code, []).append(str(quote["id"]))
    for code, selected_ids in used_by_code.items():
        entry = selection_by_code.get(code)
        if entry is None:
            selection_by_code[code] = {
                "mode": "legacy_manual",
                "selected_quote_ids": selected_ids,
                "source": "migrated_quotes_used_flags",
            }
        elif isinstance(entry, dict) and str(entry.get("mode") or "").lower() != "automatic":
            entry.setdefault("selected_quote_ids", selected_ids)
            if not entry["selected_quote_ids"]:
                entry["selected_quote_ids"] = selected_ids

    for section in result.setdefault("takeoff_sections", []):
        for line in section.setdefault("lines", []):
            line.setdefault("missing_quantity_acknowledged", False)
            line.setdefault("missing_quantity_acknowledged_at", None)
            line.setdefault("missing_quantity_acknowledged_by", None)
        for override in section.setdefault("material_overrides", {}).values():
            if not isinstance(override, dict):
                continue
            if "rate" in override:
                override.setdefault("rate_override", override.get("rate"))
            else:
                override.setdefault("rate_override", None)
            if "factor" in override:
                override.setdefault("factor_override", override.get("factor"))
            else:
                override.setdefault("factor_override", None)
            override.setdefault("rate_override_reason", None)
            override.setdefault("override_source", "legacy_migration")

    for door in result.setdefault("doors", []):
        door.setdefault("missing_quantity_acknowledged", False)
        door.setdefault("missing_quantity_acknowledged_at", None)
        door.setdefault("missing_quantity_acknowledged_by", None)

    type_names = {"field": "Field", "shop": "Shop", "design": "Design"}
    for labor in result.setdefault("labor_estimates", []):
        labor.setdefault("labor_type", type_names.get(str(labor.get("category", "")).casefold()))
        if "man_hours" not in labor:
            labor["man_hours"], labor["man_hours_source"] = _legacy_man_hours(labor)
        else:
            labor.setdefault("man_hours_source", "existing")
        labor.setdefault("crew_size", labor.get("crew"))
        labor.setdefault("hours_per_worker_per_day", None)
        labor.setdefault("workdays_per_week", None)
        labor.setdefault("controlled_rate_snapshot", None)
        labor.setdefault("legacy_effective_rate", labor.get("rate"))
        labor.setdefault("rate_override", None)
        labor.setdefault("rate_override_reason", None)
        labor.setdefault("origin", "legacy")
        labor.setdefault("source_links", [])
        labor.setdefault("source_status", "unclassified")
        labor.setdefault("stale_acknowledged", False)

    working = result["working_estimate"]
    working.setdefault(
        "labor_suggestion_exclusions",
        deepcopy(working.get("labor_candidate_exclusions", [])),
    )
    working.setdefault("component_markup_overrides", {})
    working.setdefault("pending_controlled_values", [])

    result.setdefault("schema_migrations", []).append({
        "id": "project-1.0.0-to-1.1.0",
        "from_version": "1.0.0",
        "to_version": "1.1.0",
        "scope": "active_project_only",
    })
    result["schema_version"] = "1.1.0"
    result["interchange_version"] = "1.1.0"
    return result


Migration = Callable[[dict[str, Any]], dict[str, Any]]
MIGRATIONS: dict[str, tuple[str, Migration]] = {
    "1.0.0": ("1.1.0", _migrate_1_0_0_to_1_1_0),
}


def migrate_project_document(
    document: dict[str, Any], *, target_version: str = CURRENT_SCHEMA_VERSION
) -> dict[str, Any]:
    """Return a migrated deep copy, leaving the caller's document untouched.

    Calling this repeatedly is idempotent. Unknown or future versions fail
    closed instead of being guessed into the current schema.
    """
    if not isinstance(document, dict):
        raise MigrationError("Project document must be a JSON object.")
    result = deepcopy(document)
    version = str(result.get("schema_version") or "")
    if not version:
        raise MigrationError("Project document is missing schema_version.")
    visited: set[str] = set()
    while version != target_version:
        if version in visited:
            raise MigrationError(f"Project migration cycle detected at {version}.")
        visited.add(version)
        next_step = MIGRATIONS.get(version)
        if next_step is None:
            raise MigrationError(
                f"No supported project migration path from {version} to {target_version}."
            )
        next_version, migration = next_step
        result = migration(result)
        if result.get("schema_version") != next_version:
            raise MigrationError(
                f"Migration from {version} did not produce expected version {next_version}."
            )
        version = next_version
    return result


def project_migration_required(document: dict[str, Any]) -> bool:
    return str(document.get("schema_version") or "") != CURRENT_SCHEMA_VERSION
