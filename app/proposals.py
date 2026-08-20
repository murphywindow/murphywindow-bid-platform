"""Immutable commercial proposal snapshots, ancestry, branching, and comparison.

Canonicalization deliberately freezes the complete proposal-producing project
and configuration state. Operational lifecycle collections and volatile file/UI
metadata are excluded; array order remains significant because it can affect
presentation and commercial interpretation.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any

from .calculations import dollars_in_words
from .schema import now, uid
from .services import DomainError, audit, calculate_project, submission_blockers

PROPOSAL_SNAPSHOT_SCHEMA_VERSION = "1.0.0"
PROPOSAL_STATUSES = {"generated", "voided", "superseded"}

_NON_COMMERCIAL_ROOTS = {
    "estimate_revisions", "reviews", "submissions", "proposal_artifacts",
    "proposal_history", "award", "contract_allocations", "change_orders",
    "sov_lines", "closeout", "audit_events", "configuration_lineage",
    "working_branch", "schema_migrations", "bid_tabulations", "test_generation",
}
_VOLATILE_PROJECT_FIELDS = {
    "revision", "updated_at", "bid_version", "lifecycle_state", "archived",
}


def canonical_proposal_state(document: dict[str, Any], configuration: dict[str, Any]) -> dict[str, Any]:
    """Return the deterministic, complete commercial state used for identity.

    Timestamps that express commercial intent (selection/effective dates) remain.
    Only persistence counters, navigation/lifecycle state, and generated-history
    metadata are removed. The effective configuration is embedded so mutable
    external catalogs can never change a historical proposal.
    """
    state = {key: deepcopy(value) for key, value in document.items() if key not in _NON_COMMERCIAL_ROOTS}
    project = state.setdefault("project", {})
    for key in _VOLATILE_PROJECT_FIELDS:
        project.pop(key, None)
    state["effective_configuration"] = deepcopy(configuration)
    return state


def canonical_bytes(state: dict[str, Any]) -> bytes:
    return json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def proposal_fingerprint(document: dict[str, Any], configuration: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(canonical_proposal_state(document, configuration))).hexdigest()


def _number(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _summary(document: dict[str, Any]) -> dict[str, Any]:
    totals = document.get("working_estimate", {}).get("totals", {})
    value = _number(totals.get("selling_value"))
    cost = _number(totals.get("direct_cost"))
    square_feet = _number(totals.get("square_feet") or totals.get("total_square_feet"))
    margin_dollars = value - cost
    margin_percentage = margin_dollars / value if value else Decimal(0)
    config = document.get("effective_configuration", {})
    tax_id = document.get("project", {}).get("tax_rate_id")
    tax_record = next((row for row in config.get("tax_rates", []) if row.get("id") == tax_id), {})
    return {
        "bid_value": str(value), "direct_cost": str(cost),
        "margin_dollars": str(margin_dollars), "margin_percentage": str(margin_percentage),
        "total_square_feet": str(square_feet),
        "value_per_square_foot": str(value / square_feet) if square_feet else None,
        "tax": totals.get("tax"), "applicable_tax_rate": tax_record.get("rate"), "tax_rate_id": tax_id,
        "contingency": totals.get("contingency"), "bond": totals.get("bond"),
    }


def create_proposal_snapshot(document: dict[str, Any], configuration: dict[str, Any], actor: str,
                             role: str, proposal_name: str, *, artifact_id: str | None = None) -> dict[str, Any]:
    name = str(proposal_name or "").strip()
    if not name:
        raise DomainError("Proposal Name is required.", "proposal_name_required")
    calculate_project(document, configuration)
    blockers = submission_blockers(document)
    if blockers:
        raise DomainError("Proposal validation failed.", details=blockers)
    state = canonical_proposal_state(document, configuration)
    fingerprint = hashlib.sha256(canonical_bytes(state)).hexdigest()
    for existing in document.get("proposal_history", []):
        if existing.get("fingerprint") == fingerprint:
            raise DomainError(
                f"Current bid state is identical to {existing.get('number')} — {existing.get('name')}.",
                "duplicate_proposal", [{"proposal_id": existing.get("id"), "proposal_number": existing.get("number"), "proposal_name": existing.get("name")}],
            )
    history = document.setdefault("proposal_history", [])
    sequence = max([int(item.get("sequence", 0)) for item in history] or [0]) + 1
    proposal_id, created_at = uid("prp"), now()
    branch = document.get("working_branch") or {}
    parent_id = branch.get("source_proposal_id")
    parent = next((item for item in history if item.get("id") == parent_id), None)
    ancestors = [*(parent.get("ancestor_ids", []) if parent else []), parent_id] if parent_id else []
    artifact_id = artifact_id or uid("art")
    metadata = {
        "id": proposal_id, "sequence": sequence, "number": f"P{sequence}", "name": name,
        "generated_at": created_at, "generated_by": actor, "generator_role": role,
        "parent_proposal_id": parent_id, "branch_source": deepcopy(branch) if parent_id else None,
        "ancestor_ids": ancestors, "ancestry_status": "known" if parent_id else "root_or_unknown",
        "fingerprint": fingerprint, "artifact_id": artifact_id, "status": "generated",
        "void": None, "summary": _summary(state), "snapshot_schema_version": PROPOSAL_SNAPSHOT_SCHEMA_VERSION,
    }
    artifact = {
        "id": artifact_id, "proposal_id": proposal_id, "snapshot_fingerprint": fingerprint,
        "template_version": "proposal-2.0.0", "generated_at": created_at, "generated_by": actor,
        "project_name": state.get("project", {}).get("name"), "project_number": state.get("project", {}).get("project_number"),
        "project_address": state.get("project", {}).get("address", ""), "owner_name": state.get("project", {}).get("owner_name", ""),
        "general_contractor": state.get("project", {}).get("general_contractor", ""),
        "estimator": state.get("project", {}).get("estimator", ""),
        "attention": next((row.get("name") for row in state.get("contacts", []) if row.get("active", True)), ""),
        "attention_company": next((row.get("organization") for row in state.get("contacts", []) if row.get("active", True)), ""),
        "scope_codes": [{"code": row.get("code", ""), "description": row.get("description", "")}
                        for row in state.get("cost_codes", []) if row.get("code")],
        "proposal_name": name, "proposal_number": f"P{sequence}", "amount": metadata["summary"]["bid_value"],
        "written_amount": dollars_in_words(metadata["summary"]["bid_value"]),
        "bid_version": deepcopy(document.get("project", {}).get("bid_version")),
        "revision_id": proposal_id,
        "scope": state.get("project", {}).get("proposal_scope", ""), "inclusions": state.get("project", {}).get("proposal_inclusions", ""),
        "exclusions": state.get("project", {}).get("proposal_exclusions", ""),
        "additional_information": state.get("project", {}).get("additional_information", ""), "immutable": True,
        "alternates": [{"key": row.get("key"), "name": row.get("name"), "customer_description": row.get("customer_description"),
                        "scope_of_change": deepcopy(row.get("calculated", {}).get("scope_of_change", [])),
                        "classification": row.get("calculated", {}).get("classification"),
                        "selling_value_delta": row.get("calculated", {}).get("selling_value_delta")}
                       for row in state.get("alternates", [])],
    }
    artifact["sha256"] = hashlib.sha256(json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    snapshot = {"schema_version": PROPOSAL_SNAPSHOT_SCHEMA_VERSION, "metadata": deepcopy(metadata), "state": state, "artifact": artifact}
    history.append(deepcopy(metadata))
    document.setdefault("proposal_artifacts", []).append(deepcopy(artifact))
    audit(document, actor, role, "proposal_snapshot", proposal_id, "proposal_generate", None,
          {"name": name, "number": metadata["number"], "fingerprint": fingerprint, "parent_proposal_id": parent_id, "artifact_id": artifact_id},
          "Generated immutable proposal snapshot")
    document["working_branch"] = {
        "id": branch.get("id") or uid("brn"), "source_proposal_id": proposal_id,
        "source_proposal_number": metadata["number"], "source_proposal_name": name,
        "source_proposal_status": "generated", "created_at": branch.get("created_at") or created_at,
        "created_by": branch.get("created_by") or actor, "continued_after_generation_at": created_at,
        "inherited_configuration_id": configuration.get("id"), "configuration_refresh_status": "not_refreshed",
        "has_unpublished_changes": False,
    }
    return snapshot


def historical_document(snapshot: dict[str, Any], live_document: dict[str, Any]) -> dict[str, Any]:
    """Build a detached whole-workspace historical view without mutable references."""
    result = deepcopy(snapshot["state"])
    result.pop("effective_configuration", None)
    result["proposal_history"] = deepcopy(live_document.get("proposal_history", []))
    result["proposal_artifacts"] = deepcopy(live_document.get("proposal_artifacts", []))
    result["estimate_revisions"] = []
    result["submissions"] = []
    result["audit_events"] = []
    result["project"]["revision"] = live_document["project"]["revision"]
    result["project"]["historical_proposal"] = deepcopy(snapshot["metadata"])
    return result


def _apply_path(document: dict[str, Any], path: str, value: Any) -> None:
    parts = str(path).split(".")
    if not parts or parts[0] in _NON_COMMERCIAL_ROOTS or parts[0] == "effective_configuration":
        raise DomainError("Historical branch edit targets a protected field.", "immutable_snapshot")
    target: Any = document
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        index = int(parts[-1])
        if value is None and 0 <= index < len(target):
            target.pop(index)
        elif index == len(target):
            target.append(deepcopy(value))
        else:
            target[index] = deepcopy(value)
    else:
        target[parts[-1]] = deepcopy(value)


def branch_from_snapshot(live: dict[str, Any], snapshot: dict[str, Any], changes: list[dict[str, Any]],
                         actor: str, role: str, correlation_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not changes:
        raise DomainError("The first branch mutation is required.", "branch_mutation_required")
    source = deepcopy(snapshot["state"])
    config = source.pop("effective_configuration")
    # Preserve all current lifecycle/history evidence while replacing only live estimating state.
    result = deepcopy(live)
    for key, value in source.items():
        if key not in _NON_COMMERCIAL_ROOTS:
            result[key] = deepcopy(value)
    result["project"]["id"] = live["project"]["id"]
    result["project"]["revision"] = live["project"]["revision"]
    result["project"]["configuration_id"] = config.get("id")
    for field in ("bid_version", "lifecycle_state", "archived", "created_at", "updated_at"):
        if field in live.get("project", {}):
            result["project"][field] = deepcopy(live["project"][field])
    branch = {
        "id": uid("brn"), "source_proposal_id": snapshot["metadata"]["id"],
        "source_proposal_number": snapshot["metadata"]["number"], "source_proposal_name": snapshot["metadata"]["name"],
        "source_proposal_status": snapshot["metadata"].get("status"), "created_at": now(), "created_by": actor,
        "correlation_id": correlation_id, "first_edit": deepcopy(changes[0]),
        "inherited_configuration_id": config.get("id"), "configuration_refresh_status": "not_refreshed",
        "has_unpublished_changes": True,
    }
    result["working_branch"] = branch
    for change in changes:
        _apply_path(result, change.get("path", ""), change.get("new"))
    calculate_project(result, config)
    audit(result, actor, role, "working_branch", branch["id"], "branch_from_proposal", None,
          {"source_proposal_id": branch["source_proposal_id"], "first_edit": deepcopy(changes[0])},
          "First edit from immutable proposal", correlation_id)
    return result, config


def void_proposal(document: dict[str, Any], proposal_id: str, actor: str, role: str, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        raise DomainError("A void reason is required.", "void_reason_required")
    item = next((entry for entry in document.get("proposal_history", []) if entry.get("id") == proposal_id), None)
    if not item:
        raise DomainError("Proposal was not found.", "not_found")
    if item.get("status") == "voided":
        raise DomainError("Proposal is already voided.", "proposal_already_voided")
    item["status"] = "voided"
    item["void"] = {"reason": str(reason).strip(), "voided_at": now(), "voided_by": actor, "voided_by_role": role}
    audit(document, actor, role, "proposal_snapshot", proposal_id, "proposal_void", {"status": "generated"}, deepcopy(item["void"]), str(reason).strip())
    return item


def _delta(old: Any, new: Any, *, label: str, format: str) -> dict[str, Any]:
    return {"label": label, "old": old, "new": new, "delta": str(_number(new) - _number(old)), "format": format}


def _different(old: Any, new: Any) -> bool:
    if old in (None, "") and new in (None, ""):
        return False
    if isinstance(old, (int, float, Decimal)) or isinstance(new, (int, float, Decimal)):
        return _number(old) != _number(new)
    return old != new


_SUMMARY_FIELDS = {
    "bid_value": ("Proposal Amount", "money"), "direct_cost": ("Direct Cost", "money"),
    "margin_dollars": ("Margin Dollars", "money"), "margin_percentage": ("Margin Percentage", "percent"),
    "total_square_feet": ("Total SF", "number"), "value_per_square_foot": ("Value / SF", "money"),
    "tax": ("Tax", "money"), "applicable_tax_rate": ("Tax Rate", "percent"),
    "contingency": ("Contingency", "money"), "bond": ("Bond", "money"),
}
_COST_CODE_FIELDS = {
    "direct_cost": ("Direct Cost", "money"), "selling_value": ("Selling Value", "money"),
    "margin_dollars": ("Margin Dollars", "money"), "margin_percentage": ("Margin Percentage", "percent"),
    "total_square_feet": ("SF", "number"), "dollars_per_square_foot": ("Value / SF", "money"),
}


def compare_snapshots(left: dict[str, Any], right: dict[str, Any], *, show_unchanged: bool = False) -> dict[str, Any]:
    a, b = left["metadata"], right["metadata"]
    summary = {}
    for key, (label, format) in _SUMMARY_FIELDS.items():
        old, new = a.get("summary", {}).get(key), b.get("summary", {}).get(key)
        if show_unchanged or _different(old, new):
            summary[key] = _delta(old, new, label=label, format=format)
    left_lines = {str(row.get("code")): row for row in left["state"].get("working_estimate", {}).get("cost_code_summaries", [])}
    right_lines = {str(row.get("code")): row for row in right["state"].get("working_estimate", {}).get("cost_code_summaries", [])}
    cost_codes = []
    for code in sorted(set(left_lines) | set(right_lines)):
        old, new = left_lines.get(code), right_lines.get(code)
        status = "added" if old is None else "removed" if new is None else "changed" if old != new else "unchanged"
        if status == "unchanged" and not show_unchanged:
            continue
        fields = {}
        for key, (label, format) in _COST_CODE_FIELDS.items():
            before, after = (old or {}).get(key), (new or {}).get(key)
            if show_unchanged or _different(before, after):
                fields[key] = _delta(before, after, label=label, format=format)
        source_changes = _source_changes(left["state"], right["state"], code)
        if status == "changed" and not show_unchanged and not fields and not source_changes:
            continue
        cost_codes.append({"code": code, "description": (new or old or {}).get("description"), "status": status,
                           "fields": fields, "source_changes": source_changes})
    language = {}
    for field, label in (("proposal_scope", "Scope"), ("proposal_inclusions", "Inclusions"),
                         ("proposal_exclusions", "Exclusions"), ("additional_information", "Additional Information")):
        old, new = left["state"].get("project", {}).get(field), right["state"].get("project", {}).get(field)
        if old != new or show_unchanged:
            language[field] = {"label": label, "old": old, "new": new, "changed": old != new, **_text_diff(old, new)}
    alternate_changes = _alternate_changes(left["state"], right["state"])
    cost_code_value_delta = sum((_number(row.get("fields", {}).get("selling_value", {}).get("delta")) for row in cost_codes), Decimal(0))
    proposal_delta = _number(summary.get("bid_value", {}).get("delta"))
    top_level_delta = proposal_delta - cost_code_value_delta
    reconciliation = {"proposal_amount_delta": str(proposal_delta), "cost_code_value_delta": str(cost_code_value_delta),
                      "top_level_pricing_delta": str(top_level_delta), "reconciled": cost_code_value_delta + top_level_delta == proposal_delta}
    return {"left": deepcopy(a), "right": deepcopy(b), "header": f"{a['number']} — {a['name']} → {b['number']} — {b['name']}",
            "identical": a.get("fingerprint") == b.get("fingerprint"), "summary": summary, "cost_codes": cost_codes,
            "alternates": {"changed": bool(alternate_changes), "changes": alternate_changes},
            "proposal_language": language, "reconciliation": reconciliation}


def _text_diff(old: Any, new: Any) -> dict[str, Any]:
    split = lambda value: [part.strip() for part in re.split(r"(?<=[.!?])\s+|[\r\n]+", str(value or "")) if part.strip()]
    before, after = split(old), split(new)
    return {"added": [item for item in after if item not in before], "removed": [item for item in before if item not in after]}


def _alternate_changes(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    before = {str(row.get("key") or row.get("id")): row for row in left.get("alternates", [])}
    after = {str(row.get("key") or row.get("id")): row for row in right.get("alternates", [])}
    output = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        current = new or old or {}
        label = f"{key} — {current.get('name') or 'Alternate'}"
        if old is None or new is None:
            output.append({"key": key, "label": label, "status": "added" if old is None else "removed",
                           "scope_added": [text for group in (new or {}).get("calculated", {}).get("scope_of_change", []) for text in group.get("changes", [])],
                           "scope_removed": [text for group in (old or {}).get("calculated", {}).get("scope_of_change", []) for text in group.get("changes", [])],
                           "old": "Not present" if old is None else "; ".join(text for group in old.get("calculated", {}).get("scope_of_change", []) for text in group.get("changes", [])),
                           "new": "Removed" if new is None else "; ".join(text for group in new.get("calculated", {}).get("scope_of_change", []) for text in group.get("changes", [])), "format": "text"})
            continue
        old_scope = [text for group in old.get("calculated", {}).get("scope_of_change", []) for text in group.get("changes", [])]
        new_scope = [text for group in new.get("calculated", {}).get("scope_of_change", []) for text in group.get("changes", [])]
        changed = old.get("name") != new.get("name") or old.get("customer_description") != new.get("customer_description") or old_scope != new_scope or old.get("calculated", {}).get("selling_value_delta") != new.get("calculated", {}).get("selling_value_delta")
        if changed:
            output.append({"key": key, "label": label, "status": "changed",
                           "scope_added": [text for text in new_scope if text not in old_scope],
                           "scope_removed": [text for text in old_scope if text not in new_scope],
                           "old_selling_value_delta": old.get("calculated", {}).get("selling_value_delta"),
                           "new_selling_value_delta": new.get("calculated", {}).get("selling_value_delta"),
                           "old": "; ".join(old_scope) or "No differences", "new": "; ".join(new_scope) or "No differences", "format": "text"})
    return output


def _source_changes(left: dict[str, Any], right: dict[str, Any], code: str) -> list[dict[str, Any]]:
    output = []
    old_frames = _frame_records(left, code)
    new_frames = _frame_records(right, code)
    frame_entries = _compare_records(old_frames, new_frames, "Frame", (
        "mark", "quantity", "width_inches", "height_inches", "head_condition", "sill_condition", "jamb_condition", "notes"))
    if frame_entries:
        output.append({"category": "Frame Takeoff", "entries": frame_entries})
    collections = (("quotes", "Quote"), ("equipment", "Equipment"),
                   ("borrowed_lites", "Borrowed Lite"), ("labor_estimates", "Labor"), ("doors", "Door"))
    for collection, label in collections:
        old = [row for row in left.get(collection, []) if str(row.get("code")) == code]
        new = [row for row in right.get(collection, []) if str(row.get("code")) == code]
        if old != new:
            old_by_id = {str(row.get("id")): row for row in old}
            new_by_id = {str(row.get("id")): row for row in new}
            entries = []
            for row_id in sorted(set(old_by_id) | set(new_by_id)):
                before, after = old_by_id.get(row_id), new_by_id.get(row_id)
                if before is None:
                    entries.append({"id": row_id, "status": "added", "label": _record_label(label, after), "changes": []})
                    continue
                if after is None:
                    entries.append({"id": row_id, "status": "removed", "label": _record_label(label, before), "changes": []})
                    continue
                changes = []
                for field in _business_fields(label):
                    old_value, new_value = _nested_value(before, field), _nested_value(after, field)
                    if old_value != new_value:
                        changes.append({"field": field, "label": field.replace("_", " ").title(), "old": old_value,
                                        "new": new_value, "format": _field_format(field)})
                if changes:
                    entries.append({"id": row_id, "status": "changed", "label": _record_label(label, after), "changes": changes})
            if entries:
                output.append({"category": label, "entries": entries})
    old_materials = _installation_material_records(left, code)
    new_materials = _installation_material_records(right, code)
    material_entries = _compare_records(old_materials, new_materials, "Installation Material", (
        "name", "source", "manual_quantity", "factor", "unit", "controlled_rate_id",
        "project_rate", "cost_code", "notes"))
    if material_entries:
        output.append({"category": "Installation Materials", "entries": material_entries})
    old_lines = [row for row in left.get("working_estimate", {}).get("lines", []) if str(row.get("code")) == code]
    new_lines = [row for row in right.get("working_estimate", {}).get("lines", []) if str(row.get("code")) == code]
    if old_lines != new_lines:
        old_by_id = {str(row.get("id")): row for row in old_lines}
        new_by_id = {str(row.get("id")): row for row in new_lines}
        entries = []
        for row_id in sorted(set(old_by_id) | set(new_by_id)):
            before, after = old_by_id.get(row_id), new_by_id.get(row_id)
            changes = []
            for field in ("direct_cost", "markup_rate", "markup_override_rate", "markup_value", "selling_value", "area"):
                old_value, new_value = (before or {}).get(field), (after or {}).get(field)
                if old_value != new_value:
                    changes.append({"field": field, "label": field.replace("_", " ").title(), "old": old_value,
                                    "new": new_value, "format": _field_format(field), "consequence": True})
            if changes or before is None or after is None:
                entries.append({"id": row_id, "status": "added" if before is None else "removed" if after is None else "changed",
                                "label": str((after or before or {}).get("description") or "Bid component"), "changes": changes})
        if entries:
            output.append({"category": "Pricing consequences", "entries": entries})
    return output


def _frame_records(state: dict[str, Any], code: str) -> list[dict[str, Any]]:
    records = []
    for section in state.get("takeoff_sections", []):
        if str(section.get("code")) != code:
            continue
        for row in section.get("lines", []):
            records.append({**deepcopy(row), "section_name": section.get("name")})
    return records


def _installation_material_records(state: dict[str, Any], code: str) -> list[dict[str, Any]]:
    records = []
    for section in state.get("takeoff_sections", []):
        overrides = section.get("material_overrides", {})
        for material in section.get("additional_materials", []):
            if str(material.get("cost_code") or section.get("code")) != code:
                continue
            override = overrides.get(str(material.get("id")), {})
            records.append({**deepcopy(material), "section_name": section.get("name"),
                            "project_rate": override.get("rate_override")})
    return records


def _compare_records(old: list[dict[str, Any]], new: list[dict[str, Any]], category: str,
                     fields: tuple[str, ...]) -> list[dict[str, Any]]:
    old_by_id, new_by_id = {str(row.get("id")): row for row in old}, {str(row.get("id")): row for row in new}
    entries = []
    for row_id in sorted(set(old_by_id) | set(new_by_id)):
        before, after = old_by_id.get(row_id), new_by_id.get(row_id)
        if before is None or after is None:
            row = after or before
            entries.append({"id": row_id, "status": "added" if before is None else "removed",
                            "label": _record_label(category, row), "description": _record_description(category, row), "changes": []})
            continue
        changes = []
        for field in fields:
            old_value, new_value = _nested_value(before, field), _nested_value(after, field)
            if old_value != new_value:
                changes.append({"field": field, "label": field.replace("_", " ").title(), "old": old_value,
                                "new": new_value, "format": _field_format(field)})
        if changes:
            entries.append({"id": row_id, "status": "changed", "label": _record_label(category, after), "changes": changes})
    return entries


def _nested_value(row: dict[str, Any], field: str) -> Any:
    value: Any = row
    for part in field.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _record_label(category: str, row: dict[str, Any] | None) -> str:
    row = row or {}
    return str(row.get("vendor") or row.get("mark") or row.get("description") or row.get("name") or row.get("door_number") or category)


def _record_description(category: str, row: dict[str, Any] | None) -> str:
    row = row or {}
    if category == "Frame":
        return f'{row.get("width_inches") or 0}" × {row.get("height_inches") or 0}", Qty {row.get("quantity") or 0}'
    return str(row.get("description") or row.get("vendor") or row.get("mark") or "")


def _field_format(field: str) -> str:
    leaf = field.split(".")[-1]
    if leaf in {"price", "rate", "delivery", "direct_cost", "markup_value", "selling_value", "rate_override", "project_rate"}:
        return "money"
    if "markup" in leaf and "rate" in leaf:
        return "percent"
    if leaf in {"used", "taxable"}:
        return "boolean"
    if leaf in {"quantity", "leaf_quantity", "man_hours", "crew_size", "width_inches", "height_inches", "square_feet", "area", "tie_back_qty", "backpan_lf"}:
        return "number"
    return "text"


def _business_fields(category: str) -> tuple[str, ...]:
    return {
        "Quote": ("vendor", "price", "used", "credit_type", "credit_value", "surcharge_type", "surcharge_value", "square_feet", "notes"),
        "Frame": ("name", "tie_back_qty", "backpan_lf"),
        "Equipment": ("description", "quantity", "duration", "duration_unit", "rate", "delivery", "taxable", "notes"),
        "Borrowed Lite": ("mark", "quantity", "width_inches", "height_inches", "rate", "notes"),
        "Labor": ("description", "labor_type", "man_hours", "crew_size", "hours_per_worker_per_day", "workdays_per_week", "controlled_rate_snapshot.rate", "rate_override", "rate_override_reason", "notes"),
        "Door": ("door_number", "mark", "leaf_quantity", "width_inches", "height_inches", "hardware_group_id", "notes"),
    }.get(category, tuple())
