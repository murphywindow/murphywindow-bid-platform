"""Idempotent migrations for active Murphy Window project documents.

Migrations enrich only the current working document.  Immutable estimate
revisions, submissions, proposal artifacts, and awarded snapshots are retained
exactly as stored so a schema upgrade cannot rewrite historical commercial
evidence.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Callable


CURRENT_SCHEMA_VERSION = "1.3.0"

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
    for field in ("owner_legal_name", "owner_address", "owner_website", "owner_phone", "owner_email"):
        project.setdefault(field, "")

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


def _migrate_1_1_0_to_1_2_0(document: dict[str, Any]) -> dict[str, Any]:
    """Move prefixed additive ALT rows into canonical delta additions.

    Immutable revisions and proposal snapshots are deliberately untouched.
    Legacy ALT rows were additive, so preserving them as ALT-only Added records
    retains their commercial meaning without keeping a second active engine.
    """
    result = deepcopy(document)
    legacy_metadata = {str(row.get("variant") or row.get("key") or "").upper(): row for row in result.get("alternates", []) if isinstance(row, dict)}
    alternates: dict[str, dict[str, Any]] = {}

    def alternate(key: str) -> dict[str, Any]:
        if key not in alternates:
            sequence = int(re.sub(r"\D", "", key) or len(alternates) + 1)
            prior = legacy_metadata.get(key, {})
            alternates[key] = {
                "id": prior.get("id") or f"alt_migrated_{key.lower()}", "sequence": sequence, "key": key,
                "name": prior.get("name") or f"Alternate {sequence}",
                "customer_description": prior.get("customer_description") or prior.get("description") or "",
                "created_at": prior.get("created_at"), "base_created_revision": result.get("project", {}).get("revision", 0),
                "changes": {}, "calculated": {}, "migration": {"source": "legacy_prefixed_variant", "preserved_as": "added_records"},
            }
        return alternates[key]

    section_by_code = {
        re.sub(r"[^A-Z0-9]", "", str(row.get("code") or "").upper()): row
        for row in result.get("takeoff_sections", [])
        if not re.match(r"^ALT[1-4][-:\s]+", str(row.get("code") or ""), re.IGNORECASE)
    }
    for collection in ("quotes", "takeoff_sections", "doors", "equipment", "borrowed_lites", "labor_estimates", "travel_estimates"):
        retained = []
        for row in result.get(collection, []):
            match = re.match(r"^(ALT[1-4])[-:\s]+(.+)$", str(row.get("code") or "").strip(), re.IGNORECASE)
            if not match:
                retained.append(row); continue
            key, base_code = match.group(1).upper(), match.group(2).strip()
            migrated = deepcopy(row); migrated["code"] = base_code
            if collection == "takeoff_sections":
                target = section_by_code.get(re.sub(r"[^A-Z0-9]", "", base_code.upper()))
                if target:
                    frame_bucket = alternate(key)["changes"].setdefault("frames", {"added": [], "removed": [], "overrides": {}})
                    for line in migrated.get("lines", []):
                        added = deepcopy(line); added["section_id"] = target.get("id"); frame_bucket["added"].append(added)
                    section_fields = {}
                    for field in ("material_overrides", "tie_back_qty", "backpan_lf"):
                        if migrated.get(field) != target.get(field):
                            value = deepcopy(migrated.get(field))
                            if field in {"tie_back_qty", "backpan_lf"}:
                                try:
                                    value = float(target.get(field) or 0) + float(migrated.get(field) or 0)
                                    if value.is_integer():
                                        value = int(value)
                                except (TypeError, ValueError):
                                    pass
                            section_fields[field] = {"base_value": deepcopy(target.get(field)), "value": value}
                    if section_fields:
                        section_bucket = alternate(key)["changes"].setdefault("takeoff_sections", {"added": [], "removed": [], "overrides": {}})
                        section_bucket["overrides"][str(target.get("id"))] = section_fields
                    continue
            bucket = alternate(key)["changes"].setdefault(collection, {"added": [], "removed": [], "overrides": {}})
            bucket["added"].append(migrated)
        result[collection] = retained
    inclusion = result.setdefault("working_estimate", {}).pop("alternate_inclusion", {})
    working = result.setdefault("working_estimate", {})
    for mapping_name in ("quote_selection_by_code", "borrowed_lite_source_by_code"):
        mapping = working.get(mapping_name, {})
        if isinstance(mapping, dict):
            working[mapping_name] = {key: value for key, value in mapping.items()
                                     if not re.match(r"^ALT[1-4][-:\s]+", str(key), re.IGNORECASE)}
    exclusions = working.get("labor_suggestion_exclusions", [])
    if isinstance(exclusions, list):
        working["labor_suggestion_exclusions"] = [value for value in exclusions
                                                   if not re.match(r"^ALT[1-4][-:\s]+", str(value), re.IGNORECASE)]
    for key, prior in legacy_metadata.items():
        if re.fullmatch(r"ALT[1-4]", key):
            target = alternate(key)
            target["selected_for_proposal"] = bool(prior.get("included", inclusion.get(key, False)))
    for key, enabled in inclusion.items():
        if enabled or key in alternates:
            alternate(str(key).upper())["selected_for_proposal"] = bool(enabled)
    result["alternates"] = sorted(alternates.values(), key=lambda row: row["sequence"])
    result.setdefault("schema_migrations", []).append({
        "id": "project-1.1.0-to-1.2.0", "from_version": "1.1.0", "to_version": "1.2.0",
        "scope": "active_project_only", "alternate_model": "base_plus_delta",
    })
    result["schema_version"] = "1.2.0"
    result["interchange_version"] = "1.2.0"
    return result


def _migrate_1_2_0_to_1_3_0(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize optional names and typed line-markup override authority."""
    result = deepcopy(document)
    for alternate in result.setdefault("alternates", []):
        sequence = int(alternate.get("sequence") or re.sub(r"\D", "", str(alternate.get("key") or "")) or 1)
        alternate["sequence"] = sequence
        name = str(alternate.get("name") or "").strip()
        alternate["name"] = "" if name == f"Alternate {sequence}" else name
    overrides = result.setdefault("working_estimate", {}).setdefault("component_markup_overrides", {})
    for source_key, entry in list(overrides.items()):
        if not isinstance(entry, dict):
            entry = {"rate": entry}
            overrides[source_key] = entry
        if entry.get("mode") in {"percentage", "amount"}:
            entry.setdefault("value", entry.get("rate") if entry["mode"] == "percentage" else entry.get("amount"))
        elif entry.get("rate", entry.get("rate_override")) not in (None, ""):
            rate = entry.get("rate", entry.get("rate_override"))
            entry["mode"] = "percentage"
            entry["value"] = str(rate)
            entry.setdefault("rate", str(rate))
    result.setdefault("schema_migrations", []).append({
        "id": "project-1.2.0-to-1.3.0", "from_version": "1.2.0", "to_version": "1.3.0",
        "scope": "active_project_only", "line_markup_authority": "percentage_or_amount",
    })
    result["schema_version"] = "1.3.0"
    result["interchange_version"] = "1.3.0"
    return result


Migration = Callable[[dict[str, Any]], dict[str, Any]]
MIGRATIONS: dict[str, tuple[str, Migration]] = {
    "1.0.0": ("1.1.0", _migrate_1_0_0_to_1_1_0),
    "1.1.0": ("1.2.0", _migrate_1_1_0_to_1_2_0),
    "1.2.0": ("1.3.0", _migrate_1_2_0_to_1_3_0),
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
    # Additive proposal-history containers do not rewrite legacy evidence.
    result.setdefault("proposal_history", [])
    result.setdefault("working_branch", None)
    return result


def project_migration_required(document: dict[str, Any]) -> bool:
    return str(document.get("schema_version") or "") != CURRENT_SCHEMA_VERSION
