"""Domain services: authorization, bid assembly, revisions, and lifecycle."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from typing import Any

from .calculations import (
    bond_amount, borrowed_lite_area, contingency, dec, dollars_in_words,
    equipment_extension, frame_quantities, installation_material, jsonable,
    labor_extension, labor_hours, map_cost_code, markup, normalize_code, project_abbreviation, quote_cost,
    quote_unit_cost, sequential_pco, sov_values, split_variant, taxed_cost,
)
from .schema import INTERCHANGE_VERSION, now, uid


ROLES = ("Estimator", "General Manager", "President", "Project Manager", "Support", "Systems Administrator")
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
    return variant is None or bool(doc["working_estimate"].get("alternate_inclusion", {}).get(variant))


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


def calculate_project(doc: dict, config: dict) -> dict:
    """Build normalized estimate lines and traceable totals from stored raw inputs."""
    ensure_ids(doc)
    doc["project"]["abbreviation"] = project_abbreviation(doc["project"].get("name"))
    taxable, tax_rate = _tax(doc, config)
    raw: list[dict] = []
    warnings: list[dict] = []

    references = {row.get("normalized_code"): row for row in config.get("csi_references", [])}
    for code in doc.get("cost_codes", []):
        _, base = split_variant(code.get("code", ""))
        reference = references.get(normalize_code(base)) if references else None
        if references and reference is None:
            warnings.append({"code": "invalid_cost_code", "entity_id": code.get("id"), "message": f"Cost code {code.get('code')!r} is not in owner reference {config.get('cost_code_reference', {}).get('reference_id')}. The entered value is preserved for correction."})
        elif reference and not code.get("description"):
            code["description"] = reference.get("description", "")
            code["reference_id"] = reference.get("id")
        mapped = map_cost_code(code.get("code", ""), config.get("cost_code_mappings", []))
        if mapped and not code.get("mwd_code"):
            code["mwd_code"] = mapped.get("mwd_code")
            code["mwd_description"] = mapped.get("description", "")

    # Frame rows and per-section installation material.
    frame_area_by_code: dict[str, Decimal] = {}
    for section in doc.get("takeoff_sections", []):
        code = section.get("code", "")
        totals = {"quantity": Decimal(0), "square_feet": Decimal(0), "perimeter_lf": Decimal(0), "caulking_lf": Decimal(0), "head_sill_qty": Decimal(0)}
        for row in section.get("lines", []):
            try:
                q = frame_quantities(row.get("quantity"), row.get("width_inches"), row.get("height_inches"), row.get("caulking_passes"))
                row["calculated"] = jsonable(q)
                if q["square_feet"] is not None:
                    totals["quantity"] += dec(row.get("quantity"), Decimal(0)) or Decimal(0)
                    for key in ("square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty"):
                        totals[key] += q[key] or Decimal(0)
            except ValueError as exc:
                warnings.append({"code": "invalid_frame_row", "entity_id": row["id"], "message": str(exc)})
        section["totals"] = jsonable(totals)
        frame_area_by_code[code] = frame_area_by_code.get(code, Decimal(0)) + totals["square_feet"]
        material_results = []
        for rule in config.get("material_rules", []):
            if rule["source"] in totals:
                # A missing selection list is the backward-compatible equivalent of
                # "all materials selected".  New rows write the list explicitly.
                source = Decimal(0)
                for row in section.get("lines", []):
                    selections = row.get("installation_material_ids")
                    if selections is None or rule["id"] in selections:
                        source += dec(row.get("calculated", {}).get(rule["source"]), Decimal(0)) or Decimal(0)
            else:
                # The workbook's Tie Back and Backpan inputs remain section-level
                # until their future line-level placement is confirmed.
                source = dec(section.get(rule["source"]), Decimal(0)) or Decimal(0)
            factor = section.get("material_overrides", {}).get(rule["id"], {}).get("factor", rule["factor"])
            rate = section.get("material_overrides", {}).get(rule["id"], {}).get("rate", rule["rate"])
            cost = installation_material(source, factor, rate)
            material_results.append({"material_rule_id": rule["id"], "source_quantity": jsonable(source), "factor": str(factor), "rate": str(rate), "pre_tax_cost": str(cost) if cost is not None else None})
            if cost is not None and code:
                raw.append({"code": code, "category": "installation_material", "description": f"{_cost_code(doc, code).get('description', code)} — {rule['name']}",
                            "cost": taxed_cost(cost, tax_rate, taxable=taxable and rule.get("taxable", True)), "area": totals["square_feet"],
                            "tax_treatment": "taxed" if taxable and rule.get("taxable", True) else "exempt", "markup_type": "base_product",
                            "lineage": [{"source_type": "frame_material", "source_id": section["id"], "material_rule_id": rule["id"], "source_quantity": jsonable(source), "factor": str(factor), "rate": str(rate), "pre_tax_cost": str(cost), "configuration_id": config["id"]}]})
        section["material_results"] = material_results
        pre_tax_material_cost = sum((dec(item["pre_tax_cost"], Decimal(0)) or Decimal(0) for item in material_results), Decimal(0))
        section["pre_tax_material_cost"] = money_string(pre_tax_material_cost)
        section["pre_tax_material_cost_per_sf"] = money_string(pre_tax_material_cost / totals["square_feet"]) if totals["square_feet"] else None

    # Borrowed-lite areas and internal costs.
    brl_area_by_code: dict[str, Decimal] = {}
    brl_cost_by_code: dict[str, Decimal] = {}
    for row in doc.get("borrowed_lites", []):
        try:
            area = borrowed_lite_area(row.get("quantity"), row.get("width_inches"), row.get("height_inches"))
        except ValueError as exc:
            warnings.append({"code": "invalid_borrowed_lite", "entity_id": row["id"], "message": str(exc)})
            area = None
        row["calculated_square_feet"] = jsonable(area)
        code = row.get("code", "")
        if area is not None:
            brl_area_by_code[code] = brl_area_by_code.get(code, Decimal(0)) + area
            if dec(row.get("rate")) is not None:
                brl_cost_by_code[code] = brl_cost_by_code.get(code, Decimal(0)) + area * (dec(row.get("rate")) or Decimal(0))

    # Quotes; one used quote per group.
    groups: dict[str, list[dict]] = {}
    for q in doc.get("quotes", []):
        code = q.get("code", "")
        total_area = frame_area_by_code.get(code, Decimal(0)) + brl_area_by_code.get(code, Decimal(0))
        cost = quote_cost(q.get("price"), q.get("surcharge_percent"))
        q["calculated_cost"] = jsonable(cost)
        q["calculated_square_feet"] = jsonable(total_area) if total_area else None
        q["calculated_unit_cost"] = jsonable(quote_unit_cost(cost, total_area))
        groups.setdefault(q.get("group_id") or code, []).append(q)
    for group_id, rows in groups.items():
        used = [q for q in rows if q.get("used")]
        if len(used) > 1:
            warnings.append({"code": "multiple_used_quotes", "entity_id": group_id, "message": "Only one quote may be selected in a comparison group."})
        if not used and any(dec(q.get("price")) is not None for q in rows):
            warnings.append({"code": "missing_used_quote", "entity_id": group_id, "message": "Select the quote used by this group."})
        for q in used[:1]:
            code, cost = q.get("code", ""), dec(q.get("calculated_cost"), Decimal(0)) or Decimal(0)
            if code:
                active_source = doc["working_estimate"].get("borrowed_lite_source_by_code", {}).get(code, "quote")
                if code in brl_cost_by_code and active_source == "internal":
                    continue
                raw.append({"code": code, "category": "base_product", "description": _cost_code(doc, code).get("description", code),
                            "cost": taxed_cost(cost, tax_rate, taxable=taxable, tax_included=bool(q.get("tax_included"))),
                            "area": frame_area_by_code.get(code, Decimal(0)) + brl_area_by_code.get(code, Decimal(0)),
                            "tax_treatment": "included" if q.get("tax_included") else ("taxed" if taxable else "exempt"), "markup_type": "base_product",
                            "lineage": [{"source_type": "quote", "source_id": q["id"], "entered_price": q.get("price"), "surcharge_percent": q.get("surcharge_percent", 0), "tax_included": bool(q.get("tax_included")), "configuration_id": config["id"]}]})

    for code, cost in brl_cost_by_code.items():
        source = doc["working_estimate"].get("borrowed_lite_source_by_code", {}).get(code, "quote")
        if source == "internal":
            raw.append({"code": code, "category": "borrowed_lite", "description": f"{_cost_code(doc, code).get('description', code)} — Internal borrowed-lite calculation",
                        "cost": taxed_cost(cost, tax_rate, taxable=taxable), "area": brl_area_by_code.get(code, Decimal(0)), "tax_treatment": "taxed" if taxable else "exempt", "markup_type": "base_product",
                        "lineage": [{"source_type": "borrowed_lite", "source_ids": [r["id"] for r in doc["borrowed_lites"] if r.get("code") == code], "source_choice": "internal", "configuration_id": config["id"]}]})

    for row in doc.get("equipment", []):
        cost = equipment_extension(row.get("quantity"), row.get("duration"), row.get("rate"), row.get("delivery"))
        row["calculated_cost"] = jsonable(cost)
        code = row.get("code", "11 00 00")
        if cost is not None:
            raw.append({"code": code, "category": "equipment", "description": row.get("description") or "Equipment", "cost": taxed_cost(cost, tax_rate, taxable=taxable), "area": Decimal(0),
                        "tax_treatment": "taxed" if taxable else "exempt", "markup_type": "base_product", "lineage": [{"source_type": "equipment", "source_id": row["id"], "rate_version": row.get("rate_version", config["id"]), "configuration_id": config["id"]}]})

    for row in doc.get("labor_estimates", []):
        hours = labor_hours(row.get("quantity"), row.get("crew"), row.get("productivity"), row.get("hours_override"))
        cost = labor_extension(hours, row.get("rate"))
        row["calculated_hours"], row["calculated_cost"] = jsonable(hours), jsonable(cost)
        code, category = row.get("code", ""), row.get("category", "field")
        if cost is not None and code:
            markup_type = "LAS" if category == "shop" else "LAF"
            raw.append({"code": code, "category": category + "_labor", "description": row.get("description") or ("Shop labor" if category == "shop" else "Field labor"), "cost": cost,
                        "area": Decimal(0), "tax_treatment": "not_applicable", "markup_type": markup_type,
                        "lineage": [{"source_type": "labor", "source_id": row["id"], "quantity": row.get("quantity"), "crew": row.get("crew"), "productivity": row.get("productivity"), "calculated_hours": jsonable(hours), "override": row.get("hours_override"), "override_reason": row.get("override_reason"), "rate": row.get("rate"), "rate_version": row.get("rate_version", config["id"]), "configuration_id": config["id"]}]})

    lines: list[dict] = []
    for item in raw:
        sign = _sign(doc, item["code"])
        signed_cost = item["cost"] * sign
        default_rate = config.get("markup_defaults", {}).get(item["markup_type"], {}).get("rate", "0")
        chosen_rate = doc["working_estimate"].get("markup_overrides", {}).get(item["markup_type"], default_rate)
        if "".join(c for c in item["code"] if c.isalnum()) == "012116":
            chosen_rate = "0"
        m = markup(signed_cost, chosen_rate)
        lines.append({"id": _stable_line_id(item), **item, "direct_cost": money_string(signed_cost), "cost": None, "included": _active(doc, item["code"]), "deduct_sign": int(sign), "markup_rate": str(chosen_rate),
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
    area_total = sum((dec(x.get("area"), Decimal(0)) or Decimal(0) for x in lines if x.get("included", True) and x.get("category") == "base_product"), Decimal(0))
    totals = {"direct_cost": money_string(direct_total), "markup_profit": money_string(markup_total), "selling_value": money_string(selling_total),
              "margin_percentage": str(Decimal(0) if selling_total == 0 else markup_total / selling_total), "square_feet": str(area_total),
              "price_per_square_foot": None if area_total == 0 else money_string(selling_total / area_total), "reconciliation": "ok",
              "contingency": money_string(cont), "bond": money_string(bond["amount"])}
    doc["working_estimate"]["lines"] = jsonable(lines)
    doc["working_estimate"]["totals"] = totals
    doc["working_estimate"]["validation"] = warnings
    return doc


def money_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _special_line(code: str, description: str, amount: Decimal, config_id: str, category: str, extra: dict | None = None) -> dict:
    lineage = {"source_type": category, "configuration_id": config_id}
    lineage.update(extra or {})
    return {"id": "est_" + hashlib.sha256(f"{code}:{category}".encode()).hexdigest()[:24], "code": code, "category": category, "description": description, "direct_cost": money_string(amount), "included": True, "deduct_sign": 1,
            "markup_type": "special", "markup_rate": "0", "markup_value": "0.00", "selling_value": money_string(amount), "area": "0", "tax_treatment": "not_applicable", "configuration_id": config_id, "lineage": [lineage]}


def make_revision(doc: dict, actor: str, role: str, status: str, reason: str) -> dict:
    snapshot = {
        "id": uid("rev"), "revision_number": len(doc.get("estimate_revisions", [])) + 1, "configuration_id": doc["project"]["configuration_id"],
        "status": status, "bid_version": deepcopy(doc["project"].get("bid_version")), "created_by": actor, "creator_role": role, "created_at": now(), "reason": reason,
        "project_snapshot": deepcopy(doc["project"]), "cost_codes": deepcopy(doc["cost_codes"]), "source_snapshot": {
            key: deepcopy(doc[key]) for key in ("quotes", "takeoff_sections", "doors", "hardware_assignments", "equipment", "borrowed_lites", "labor_estimates", "travel_estimates")
        },
        "estimate": deepcopy(doc["working_estimate"]), "immutable": status == "submitted"
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
            "exclusions": revision["project_snapshot"].get("proposal_exclusions", ""), "addenda": revision["project_snapshot"].get("addenda_count", 0)}
    artifact = {"id": uid("art"), "template_version": "proposal-1.0.0", "revision_id": revision["id"], "generated_at": now(), "generated_by": actor,
                **body, "sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(), "immutable": True}
    doc.setdefault("proposal_artifacts", []).append(artifact)
    return artifact


def submit(doc: dict, config: dict, actor: str, role: str, payload: dict) -> dict:
    require(role, "submit")
    calculate_project(doc, config)
    blocking = [v for v in doc["working_estimate"].get("validation", []) if v["code"] in {"multiple_used_quotes"}]
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
