"""Indexed historical Bid Cost Code sell-value dollars-per-square-foot evidence.

Historical observations are extracted only from frozen awarded snapshots or
immutable submitted estimate revisions.  The extractor never recalculates a
historical project with current rules or configuration.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Iterable

from .calculations import normalize_code, split_variant
from .persistence import ConflictError, JsonStore, PersistenceError


INDEX_SCHEMA = "murphywindow.historical-metric-index"
INDEX_VERSION = 2
MINIMUM_SAMPLE = 5
BID_COST_CODE_SELL_PER_SF_METRIC = "bid-cost-code-sell-value-per-frame-plus-borrowed-lite-sf.v1"
METRIC_DEFINITION = {
    "id": BID_COST_CODE_SELL_PER_SF_METRIC,
    "version": 1,
    "label": "Bid Cost Code sell value per square foot",
    "numerator": "Cost Code Value (selling value)",
    "denominator": "Matching Frame Takeoff plus Borrowed Lite square footage, counted once",
    "direction": "lower_is_more_aggressive",
}
KNOWN_SEED_TEST_PROJECT_ID = "prj_00000000000000000000000000004320"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def canonical_cost_code(value: Any) -> str:
    variant, base = split_variant(str(value or ""))
    normalized = normalize_code(base)
    if not normalized:
        return ""
    return f"{variant}:{normalized}" if variant else normalized


def _metric_id(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("id")
    text = str(value or "").strip()
    return text or None


def _parse_time(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except ValueError:
        return float("-inf")


def _revision_sort_key(item: tuple[int, dict[str, Any]]) -> tuple[int, float, int]:
    index, revision = item
    try:
        number = int(revision.get("revision_number", -1))
    except (TypeError, ValueError):
        number = -1
    return number, _parse_time(revision.get("created_at")), index


def _duplicate_source_id(document: dict[str, Any]) -> str | None:
    if not isinstance(document, dict):
        return None
    events = document.get("audit_events")
    if not isinstance(events, list):
        return None
    for event in events:
        if isinstance(event, dict) and event.get("operation") == "duplicate":
            prior = event.get("prior_value")
            if isinstance(prior, dict) and prior.get("source_project_id"):
                return str(prior["source_project_id"])
    return None


def is_synthetic_project(document: dict[str, Any], known_synthetic_ids: set[str] | None = None) -> tuple[bool, str | None]:
    project_value = document.get("project") if isinstance(document, dict) else None
    project = project_value if isinstance(project_value, dict) else {}
    events = document.get("audit_events") if isinstance(document, dict) else None
    events = events if isinstance(events, list) else []
    project_id = str(project.get("id") or "")
    if project_id == KNOWN_SEED_TEST_PROJECT_ID:
        return True, "known_seed_test_project"
    classification = re.sub(r"[\s-]+", "_", str(project.get("data_classification") or "").strip().casefold())
    if classification in {"synthetic", "synthetic_test", "test"}:
        return True, "synthetic_data_classification"
    generated = project.get("test_generation")
    if isinstance(generated, dict) and generated:
        return True, "test_generation_metadata"
    if any(isinstance(event, dict) and event.get("operation") == "generate_test_project" for event in events):
        return True, "generated_test_audit"
    source_id = _duplicate_source_id(document)
    if source_id and source_id in (known_synthetic_ids or {KNOWN_SEED_TEST_PROJECT_ID}):
        return True, "duplicate_of_synthetic_project"

    # Legacy test documents predate structured classification.  Require paired,
    # visibly synthetic markers rather than excluding on a broad word match.
    number = str(project.get("project_number") or "").strip().upper()
    visible = " ".join(str(project.get(field) or "") for field in (
        "name", "notes", "additional_information", "proposal_exclusions",
    )).upper()
    synthetic_words = re.search(r"(^|[^A-Z])(TEST(?:ING)?|TRAINING|SYNTHETIC|VERIFICATION|SANDBOX)([^A-Z]|$)", visible)
    if (number.startswith(("TEST-", "VERIFY-")) and synthetic_words) or (
        synthetic_words and re.search(r"(^|[^A-Z])(TEST PROJECT|TEST DATA ONLY|VERIFICATION PROJECT)([^A-Z]|$)", visible)
    ):
        return True, "visible_legacy_test_markers"
    return False, None


def select_frozen_state(document: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the awarded snapshot, otherwise latest immutable submission."""
    project_value = document.get("project") if isinstance(document, dict) else None
    project = project_value if isinstance(project_value, dict) else {}
    revisions = document.get("estimate_revisions") if isinstance(document, dict) else None
    revisions = revisions if isinstance(revisions, list) else []
    award = document.get("award")
    if award is not None:
        if not isinstance(award, dict) or award.get("immutable") is not True:
            return None, {"reason": "malformed_award", "detail": "Award is not an immutable object."}
        snapshot = award.get("awarded_bid_snapshot")
        valid = (
            isinstance(snapshot, dict)
            and snapshot.get("immutable") is True
            and snapshot.get("status") == "submitted"
            and snapshot.get("id")
            and snapshot.get("id") == award.get("revision_id")
        )
        if not valid:
            return None, {"reason": "malformed_award_snapshot", "detail": "Awarded snapshot is missing, mutable, or does not match the accepted revision."}
        snapshot_project = snapshot.get("project_snapshot")
        snapshot_project_id = snapshot_project.get("id") if isinstance(snapshot_project, dict) else None
        if not snapshot_project_id or snapshot_project_id != project.get("id"):
            return None, {"reason": "malformed_award_snapshot", "detail": "Awarded snapshot has missing or mismatched project identity."}
        stored_revision = next((
            revision for revision in revisions
            if isinstance(revision, dict)
            and revision.get("id") == snapshot.get("id")
            and revision.get("status") == "submitted"
            and revision.get("immutable") is True
        ), None)
        submitted_at = _submission_date(document, snapshot.get("id"))
        award_evidence_valid = (
            bool(award.get("id")) and bool(award.get("ntp_date"))
            and _parse_time(award.get("activated_at")) != float("-inf")
            and stored_revision == snapshot and submitted_at is not None
        )
        if not award_evidence_valid:
            return None, {"reason": "malformed_award_snapshot", "detail": "Awarded snapshot does not reconcile to stored immutable revision, submission, and activation evidence."}
        return {
            "kind": "awarded_snapshot", "revision": snapshot,
            "award_id": award.get("id"), "revision_id": snapshot.get("id"),
            "effective_date": award.get("activated_at") or snapshot.get("created_at"),
            "ntp_date": award.get("ntp_date"), "activated_at": award.get("activated_at"),
            "submitted_at": submitted_at,
        }, None

    candidates = [
        (index, revision) for index, revision in enumerate(revisions)
        if isinstance(revision, dict)
        and revision.get("status") == "submitted"
        and revision.get("immutable") is True
        and revision.get("id")
        and isinstance(revision.get("project_snapshot"), dict)
        and revision["project_snapshot"].get("id") == project.get("id")
        and _submission_date(document, revision.get("id")) is not None
    ]
    if not candidates:
        return None, {"reason": "no_reliable_state", "detail": "No awarded snapshot or immutable submitted revision exists."}
    _, revision = max(candidates, key=_revision_sort_key)
    submitted_at = _submission_date(document, revision.get("id"))
    return {
        "kind": "submitted_revision", "revision": revision,
        "award_id": None, "revision_id": revision.get("id"),
        "effective_date": submitted_at or revision.get("created_at"),
        "ntp_date": None, "activated_at": None, "submitted_at": submitted_at,
    }, None


def _submission_date(document: dict[str, Any], revision_id: Any) -> str | None:
    submissions = document.get("submissions") if isinstance(document, dict) else None
    submissions = submissions if isinstance(submissions, list) else []
    matches = [
        row for row in submissions
        if isinstance(row, dict) and row.get("revision_id") == revision_id and row.get("immutable") is True
        and _parse_time(row.get("submitted_at")) != float("-inf")
    ]
    if not matches:
        return None
    matches.sort(key=lambda row: _parse_time(row.get("submitted_at")))
    return matches[-1].get("submitted_at")


def _cost_code_context(revision: dict[str, Any], code: Any) -> tuple[str, bool | None]:
    _, base = split_variant(str(code or ""))
    target = normalize_code(base)
    cost_codes = revision.get("cost_codes")
    for item in cost_codes if isinstance(cost_codes, list) else []:
        if not isinstance(item, dict):
            continue
        _, item_base = split_variant(str(item.get("code") or ""))
        if normalize_code(item_base) == target:
            deduct = item.get("deduct") if isinstance(item.get("deduct"), bool) else None
            return str(item.get("description") or base), deduct
    return str(base), None


def _source_areas(revision: dict[str, Any]) -> tuple[dict[str, Decimal], dict[str, list[str]], dict[str, dict[str, Decimal]]]:
    source = revision.get("source_snapshot")
    if not isinstance(source, dict):
        return {}, {"*": ["Frozen source snapshot is unavailable."]}, {}
    totals: dict[str, Decimal] = {}
    parts: dict[str, dict[str, Decimal]] = {}
    errors: dict[str, list[str]] = {}
    sections = source.get("takeoff_sections")
    borrowed_lites = source.get("borrowed_lites")
    if not isinstance(sections, list):
        errors.setdefault("*", []).append("Frozen Frame Takeoff collection is unavailable or malformed.")
        sections = []
    if not isinstance(borrowed_lites, list):
        errors.setdefault("*", []).append("Frozen Borrowed Lite collection is unavailable or malformed.")
        borrowed_lites = []

    for section in sections:
        if not isinstance(section, dict):
            continue
        key = canonical_cost_code(section.get("code"))
        if not key:
            continue
        section_totals = section.get("totals")
        square_feet = _decimal(section_totals.get("square_feet")) if isinstance(section_totals, dict) else None
        if square_feet is None or square_feet < 0:
            errors.setdefault(key, []).append(f"Frame section {section.get('id') or 'unknown'} has invalid frozen square footage.")
            continue
        totals[key] = totals.get(key, Decimal(0)) + square_feet
        parts.setdefault(key, {"frame": Decimal(0), "borrowed_lite": Decimal(0)})["frame"] += square_feet

    for row in borrowed_lites:
        if not isinstance(row, dict):
            continue
        key = canonical_cost_code(row.get("code"))
        if not key:
            continue
        raw_quantity = row.get("quantity")
        quantity = _decimal(raw_quantity)
        if raw_quantity in (None, "") or quantity == 0:
            continue
        if quantity is None or quantity < 0:
            errors.setdefault(key, []).append(f"Borrowed Lite {row.get('id') or 'unknown'} has invalid frozen quantity.")
            continue
        square_feet = _decimal(row.get("calculated_square_feet"))
        if square_feet is None or square_feet <= 0:
            errors.setdefault(key, []).append(f"Borrowed Lite {row.get('id') or 'unknown'} has invalid frozen square footage.")
            continue
        totals[key] = totals.get(key, Decimal(0)) + square_feet
        parts.setdefault(key, {"frame": Decimal(0), "borrowed_lite": Decimal(0)})["borrowed_lite"] += square_feet
    return totals, errors, parts


def _line_values(revision: dict[str, Any]) -> tuple[dict[str, Decimal], dict[str, list[str]], set[str], set[str]]:
    estimate = revision.get("estimate")
    if not isinstance(estimate, dict) or not isinstance(estimate.get("lines"), list):
        return {}, {"*": ["Frozen estimate lines are unavailable."]}, set(), set()
    totals: dict[str, Decimal] = {}
    errors: dict[str, list[str]] = {}
    disabled: set[str] = set()
    seen: set[str] = set()
    for line in estimate.get("lines", []):
        if not isinstance(line, dict):
            continue
        key = canonical_cost_code(line.get("code"))
        if not key:
            continue
        seen.add(key)
        if line.get("included") is False:
            disabled.add(key)
            continue
        value = _decimal(line.get("selling_value"))
        if value is None:
            errors.setdefault(key, []).append(f"Estimate line {line.get('id') or 'unknown'} has invalid Value.")
            continue
        totals[key] = totals.get(key, Decimal(0)) + value
    return totals, errors, disabled, seen


def _observation(
    document: dict[str, Any], selected: dict[str, Any], revision: dict[str, Any],
    *, code: str, code_key: str, description: str, deduct: bool | None,
    selling_value: Decimal, square_feet: Decimal, area_parts: dict[str, Decimal], adapter: str,
    direct_cost: Decimal | None = None,
) -> dict[str, Any]:
    current_project = document.get("project") if isinstance(document, dict) else None
    current_project = current_project if isinstance(current_project, dict) else {}
    frozen_project = revision.get("project_snapshot") if isinstance(revision.get("project_snapshot"), dict) else current_project
    project_id = str(current_project.get("id") or frozen_project.get("id") or "")
    ratio = selling_value / square_feet
    margin_dollars = None if direct_cost is None else selling_value - direct_cost
    margin_percentage = None if margin_dollars is None or selling_value == 0 else margin_dollars / selling_value
    identity = json.dumps([project_id, selected.get("revision_id"), code_key, BID_COST_CODE_SELL_PER_SF_METRIC], separators=(",", ":"))
    return {
        "id": "hob_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
        "project_id": project_id,
        "project_name": frozen_project.get("name") or current_project.get("name") or project_id,
        "project_number": frozen_project.get("project_number") or current_project.get("project_number"),
        "project_type": frozen_project.get("project_type") or current_project.get("project_type"),
        "building_type": frozen_project.get("building_type") or current_project.get("building_type"),
        "contract_type": frozen_project.get("contract_type") or current_project.get("contract_type"),
        "wage_type": frozen_project.get("wage_type") or current_project.get("wage_type"),
        "data_classification": frozen_project.get("data_classification") or current_project.get("data_classification"),
        "code": str(code or "").strip().upper(), "code_key": code_key,
        "description": description, "deduct": deduct,
        "selling_value": _decimal_text(selling_value),
        "direct_cost": _decimal_text(direct_cost), "margin_dollars": _decimal_text(margin_dollars),
        "margin_percentage": _decimal_text(margin_percentage),
        "frame_square_feet": _decimal_text(area_parts.get("frame", Decimal(0))),
        "borrowed_lite_square_feet": _decimal_text(area_parts.get("borrowed_lite", Decimal(0))),
        "square_feet": _decimal_text(square_feet), "value_per_square_foot": _decimal_text(ratio),
        "metric_definition": BID_COST_CODE_SELL_PER_SF_METRIC,
        "source_kind": selected.get("kind"), "award_id": selected.get("award_id"),
        "revision_id": selected.get("revision_id"), "bid_version": deepcopy(revision.get("bid_version")),
        "configuration_id": revision.get("configuration_id"), "adapter": adapter,
        "effective_date": selected.get("effective_date"), "submitted_at": selected.get("submitted_at"),
        "ntp_date": selected.get("ntp_date"), "activated_at": selected.get("activated_at"),
        "bid_due_date": frozen_project.get("bid_due_date"),
    }


def _frozen_fingerprint(project_id: str, selected: dict[str, Any]) -> str:
    payload = json.dumps({
        "project_id": project_id, "kind": selected.get("kind"),
        "award_id": selected.get("award_id"), "revision_id": selected.get("revision_id"),
        "effective_date": selected.get("effective_date"), "submitted_at": selected.get("submitted_at"),
        "ntp_date": selected.get("ntp_date"), "activated_at": selected.get("activated_at"),
        "revision": selected.get("revision"),
    }, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_state(document: dict[str, Any], selected: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    revision = selected["revision"]
    areas, area_errors, area_parts = _source_areas(revision)
    line_values, line_errors, disabled, line_codes = _line_values(revision)
    estimate = revision.get("estimate") if isinstance(revision.get("estimate"), dict) else {}
    summaries = estimate.get("cost_code_summaries")
    observations: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    if "cost_code_summaries" in estimate and (
        not isinstance(summaries, list) or any(not isinstance(summary, dict) for summary in summaries)
    ):
        keys = sorted(set(areas) | set(line_values)) or ["*"]
        return [], [
            {
                "code_key": key, "code": key, "reason": "malformed_cost_code_summaries",
                "detail": "Frozen Cost Code summaries are not a valid object collection; the legacy adapter is not used.",
            }
            for key in keys
        ]
    if isinstance(summaries, list) and not summaries:
        keys = sorted(set(areas) | set(line_values))
        return [], [
            {
                "code_key": key, "code": key, "reason": "missing_cost_code_summary",
                "detail": "Frozen state declares Cost Code summaries but has no summary for stored estimate/source evidence.",
            }
            for key in keys
        ]
    if isinstance(summaries, list):
        seen_keys: set[str] = set()
        for summary in summaries:
            code, key = summary.get("code"), canonical_cost_code(summary.get("code"))
            if not key or summary.get("included") is False:
                continue
            if key in seen_keys:
                exclusions.append({"code_key": key, "code": code, "reason": "duplicate_cost_code_summary", "detail": "Frozen state has duplicate normalized Cost Code summaries."})
                observations = [item for item in observations if item["code_key"] != key]
                continue
            seen_keys.add(key)
            raw_definition = summary.get("metric_definition")
            if raw_definition in (None, ""):
                raw_definition = summary.get("metric_definition_id")
            definition = _metric_id(raw_definition)
            if raw_definition not in (None, "") and definition is None:
                exclusions.append({"code_key": key, "code": code, "reason": "incompatible_metric", "detail": "Metric definition is malformed or has no identifier."})
                continue
            if definition and definition != BID_COST_CODE_SELL_PER_SF_METRIC:
                exclusions.append({"code_key": key, "code": code, "reason": "incompatible_metric", "detail": f"Metric definition {definition} is not compatible."})
                continue
            value = _decimal(summary.get("selling_value", summary.get("value")))
            square_feet = _decimal(summary.get("total_square_feet", summary.get("square_feet")))
            errors = [*area_errors.get("*", []), *area_errors.get(key, []), *line_errors.get("*", []), *line_errors.get(key, [])]
            if value is None:
                errors.append("Frozen Cost Code Value is missing or invalid.")
            if square_feet is None or square_feet <= 0:
                errors.append("Frozen Cost Code Square Footage is missing or zero.")
            if key not in areas:
                errors.append("Frozen summary has no matching Frame or Borrowed Lite source area.")
            elif square_feet is not None and abs(areas[key] - square_feet) > Decimal("0.0001"):
                errors.append("Frozen summary Square Footage does not reconcile to Frame plus Borrowed Lite sources.")
            if key not in line_codes:
                errors.append("Frozen summary has no matching estimate lines.")
            elif key not in line_values:
                errors.append("Frozen summary has no valid included estimate-line Value.")
            elif value is not None and abs(line_values[key] - value) > Decimal("0.01"):
                errors.append("Frozen summary Value does not reconcile to estimate lines.")
            if errors:
                exclusions.append({"code_key": key, "code": code, "reason": "invalid_metric_data", "detail": " ".join(dict.fromkeys(errors))})
                continue
            description, deduct = _cost_code_context(revision, code)
            observations.append(_observation(
                document, selected, revision, code=str(code or ""), code_key=key,
                description=str(summary.get("description") or description), deduct=deduct,
                selling_value=value, square_feet=square_feet,
                area_parts=area_parts[key],
                adapter="tagged_summary_v1" if definition else "verified_untagged_summary_v1",
                direct_cost=_decimal(summary.get("direct_cost", summary.get("cost"))),
            ))
        return observations, exclusions

    # Schema 1.0 revisions have frozen lines and source calculations but no
    # derived Cost Code summary.  Build the same numerator and denominator from
    # those stored results without recalculating dimensions or commercial rules.
    estimate_lines = estimate.get("lines")
    estimate_lines = estimate_lines if isinstance(estimate_lines, list) else []
    for key in sorted(set(areas) | set(line_values)):
        if key in disabled:
            continue
        code = next((line.get("code") for line in estimate_lines if isinstance(line, dict) and canonical_cost_code(line.get("code")) == key), key)
        errors = [*area_errors.get("*", []), *area_errors.get(key, []), *line_errors.get("*", []), *line_errors.get(key, [])]
        value, square_feet = line_values.get(key), areas.get(key)
        if value is None:
            errors.append("Legacy frozen state has no valid included Value lines for this Cost Code.")
        if square_feet is None or square_feet <= 0:
            errors.append("Legacy frozen state has missing or zero Frame-plus-Borrowed-Lite Square Footage.")
        if errors:
            exclusions.append({"code_key": key, "code": code, "reason": "invalid_metric_data", "detail": " ".join(dict.fromkeys(errors))})
            continue
        description, deduct = _cost_code_context(revision, code)
        observations.append(_observation(
            document, selected, revision, code=str(code or ""), code_key=key,
            description=description, deduct=deduct, selling_value=value,
            square_feet=square_feet, area_parts=area_parts.get(key, {}),
            adapter="legacy_frozen_lines_and_sources_v1",
        ))
    return observations, exclusions


def extract_project_observations(document: dict[str, Any], known_synthetic_ids: set[str] | None = None) -> dict[str, Any]:
    project_value = document.get("project") if isinstance(document, dict) else None
    project = project_value if isinstance(project_value, dict) else {}
    project_id = str(project.get("id") or "")
    synthetic, synthetic_reason = is_synthetic_project(document, known_synthetic_ids)
    base = {
        "project_id": project_id, "project_name": project.get("name") or project_id,
        "project_number": project.get("project_number"), "synthetic": synthetic,
        "data_classification": project.get("data_classification"),
        "fingerprint": None, "selected_state": None, "observations": [],
        "exclusions": [], "project_exclusion": None,
    }
    if synthetic:
        base["project_exclusion"] = {"reason": "synthetic_project", "detail": synthetic_reason}
        return base
    selected, error = select_frozen_state(document)
    if error:
        base["project_exclusion"] = error
        return base
    base["fingerprint"] = _frozen_fingerprint(project_id, selected)
    base["selected_state"] = {
        key: deepcopy(selected.get(key)) for key in (
            "kind", "award_id", "revision_id", "effective_date", "submitted_at", "ntp_date", "activated_at",
        )
    }
    base["observations"], base["exclusions"] = _extract_state(document, selected)
    return base


def _malformed_project_record(document: Any, detail: str, project_id: str | None = None) -> dict[str, Any]:
    project_value = document.get("project") if isinstance(document, dict) else None
    project = project_value if isinstance(project_value, dict) else {}
    identifier = str(project_id or project.get("id") or "unknown")
    return {
        "project_id": identifier, "project_name": project.get("name") or identifier,
        "project_number": project.get("project_number"), "synthetic": False,
        "fingerprint": None, "selected_state": None, "observations": [], "exclusions": [],
        "project_exclusion": {"reason": "malformed_project", "detail": detail},
    }


def linear_percentile(values: Iterable[Decimal], probability: Decimal | str | float) -> Decimal | None:
    ordered = sorted(values)
    if not ordered:
        return None
    p = Decimal(str(probability))
    if p <= 0:
        return ordered[0]
    if p >= 1:
        return ordered[-1]
    position = Decimal(len(ordered) - 1) * p
    lower = int(position.to_integral_value(rounding="ROUND_FLOOR"))
    upper = int(position.to_integral_value(rounding="ROUND_CEILING"))
    if lower == upper:
        return ordered[lower]
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def midrank_percentile(values: Iterable[Decimal], current: Decimal) -> Decimal | None:
    ordered = list(values)
    if not ordered:
        return None
    below = sum(1 for value in ordered if value < current)
    equal = sum(1 for value in ordered if value == current)
    return Decimal(100) * (Decimal(below) + Decimal(equal) / Decimal(2)) / Decimal(len(ordered))


def _date_range(observations: list[dict[str, Any]]) -> dict[str, str] | None:
    dated = sorted(
        (item.get("effective_date") for item in observations if _parse_time(item.get("effective_date")) != float("-inf")),
        key=_parse_time,
    )
    return {"start": dated[0], "end": dated[-1]} if dated else None


def _category(current: Decimal, q1: Decimal, q3: Decimal) -> tuple[str, str]:
    if q1 == q3 == current:
        return "Normal", "Current $/SF equals the common historical value."
    if current <= q1:
        return "Aggressive", "Current $/SF is at or below the historical Q1 value threshold."
    if current >= q3:
        return "Conservative", "Current $/SF is at or above the historical Q3 value threshold."
    return "Normal", "Current $/SF is between the historical Q1 and Q3 value thresholds."


def compare_values(current: Decimal | None, observations: list[dict[str, Any]], *, minimum_sample: int = MINIMUM_SAMPLE) -> dict[str, Any]:
    values = [value for item in observations if (value := _decimal(item.get("value_per_square_foot"))) is not None]
    sample_size = len(values)
    median = linear_percentile(values, Decimal("0.5"))
    q1 = linear_percentile(values, Decimal("0.25"))
    q3 = linear_percentile(values, Decimal("0.75"))
    minimum = min(values) if values else None
    maximum = max(values) if values else None
    result = {
        "status": "unavailable", "category": None, "readout": "Unavailable",
        "sample_size": sample_size, "current_value": _decimal_text(current),
        "median": _decimal_text(median), "q1": _decimal_text(q1), "q3": _decimal_text(q3),
        "minimum": _decimal_text(minimum), "maximum": _decimal_text(maximum),
        "percentile": None, "date_range": _date_range(observations),
        "difference_from_median": None, "category_definition": "Current Cost Code Value and positive Square Footage are required.",
        "warnings": [],
    }
    if current is None:
        result["warnings"].append("Current Cost Code Value per Square Foot is unavailable.")
        return result
    if median is not None:
        difference = current - median
        result["difference_from_median"] = {
            "amount": _decimal_text(difference),
            "percent": None if median == 0 else _decimal_text(difference / abs(median) * Decimal(100)),
        }
        rank = midrank_percentile(values, current)
        result["percentile"] = None if rank is None else float(rank)
    if sample_size == 0:
        result.update({
            "status": "insufficient_history", "readout": "Insufficient history · 0 comparable bids",
            "category_definition": "No qualifying historical projects are available for this Cost Code.",
        })
        return result
    if sample_size < minimum_sample:
        result.update({
            "status": "limited_history", "readout": f"Limited history · {sample_size} comparable {'bid' if sample_size == 1 else 'bids'}",
            "category_definition": f"At least {minimum_sample} comparable projects are required for a definitive category.",
        })
        return result
    category, definition = _category(current, q1, q3)
    result.update({
        "status": "classified", "category": category,
        "readout": f"{category} · {sample_size} comparable bids",
        "category_definition": definition,
    })
    return result


def _current_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    current_project = document.get("project") if isinstance(document, dict) else None
    current_project = current_project if isinstance(current_project, dict) else {}
    working = document.get("working_estimate") if isinstance(document, dict) else None
    summaries = working.get("cost_code_summaries") if isinstance(working, dict) else None
    summaries = summaries if isinstance(summaries, list) else []
    cost_codes = document.get("cost_codes") if isinstance(document, dict) else None
    cost_codes = cost_codes if isinstance(cost_codes, list) else []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        code, key = str(summary.get("code") or ""), canonical_cost_code(summary.get("code"))
        if not key:
            continue
        definition = _metric_id(summary.get("metric_definition") or summary.get("metric_definition_id"))
        warnings: list[str] = []
        selling = _decimal(summary.get("selling_value", summary.get("value")))
        area = _decimal(summary.get("total_square_feet", summary.get("square_feet")))
        if summary.get("included") is False:
            warnings.append("This Cost Code or alternate is not included in the current Bid.")
        if definition and definition != BID_COST_CODE_SELL_PER_SF_METRIC:
            warnings.append(f"Current metric definition {definition} is incompatible.")
        if selling is None:
            warnings.append("Current Cost Code Value is missing or invalid.")
        if area is None or area <= 0:
            warnings.append("Current Cost Code Square Footage is missing or zero.")
        _, base = split_variant(code)
        deduct = None
        for item in cost_codes:
            if not isinstance(item, dict):
                continue
            if normalize_code(split_variant(str(item.get("code") or ""))[1]) == normalize_code(base):
                deduct = item.get("deduct") if isinstance(item.get("deduct"), bool) else None
                break
        current = None if warnings else selling / area
        output.append({
            "code": code.strip().upper(), "code_key": key,
            "description": summary.get("description") or code, "deduct": deduct,
            "project_type": current_project.get("project_type"),
            "selling_value": _decimal_text(selling), "square_feet": _decimal_text(area),
            "current": current, "warnings": warnings,
        })
    return output


class HistoricalMetricIndex:
    """Derived, rebuildable JSON index over immutable project evidence."""

    def __init__(self, store: JsonStore, name: str = "bid-cost-code-sell-per-sf-v1"):
        self.store = store
        self.name = name

    def _empty(self) -> dict[str, Any]:
        return {
            "schema": INDEX_SCHEMA, "version": INDEX_VERSION, "revision": 0,
            "metric_definition": deepcopy(METRIC_DEFINITION), "minimum_sample": MINIMUM_SAMPLE,
            "generated_at": _now(), "projects": {}, "observations_by_code": {},
        }

    def load_or_rebuild(self) -> dict[str, Any]:
        for _ in range(5):
            expected_revision = 0
            try:
                index = self.store.load_historical_index(self.name)
                try:
                    expected_revision = int(index.get("revision", 0))
                except (TypeError, ValueError):
                    expected_revision = 0
                valid = (
                    index.get("schema") == INDEX_SCHEMA
                    and int(index.get("version", 0)) == INDEX_VERSION
                    and _metric_id(index.get("metric_definition")) == BID_COST_CODE_SELL_PER_SF_METRIC
                    and isinstance(index.get("projects"), dict)
                    and isinstance(index.get("observations_by_code"), dict)
                )
                if valid:
                    return index
            except (PersistenceError, TypeError, ValueError):
                pass
            try:
                return self.rebuild(expected_revision=expected_revision)
            except ConflictError:
                continue
        raise PersistenceError("Historical index could not be rebuilt after concurrent refreshes.")

    def rebuild(self, *, expected_revision: int | None = None) -> dict[str, Any]:
        if expected_revision is None:
            try:
                expected_revision = int(self.store.load_historical_index(self.name).get("revision", 0))
            except (PersistenceError, TypeError, ValueError):
                expected_revision = 0
        documents: list[dict[str, Any]] = []
        malformed: list[tuple[str, str]] = []
        sources = [
            *(('project', path) for path in sorted(self.store.projects.glob("*.json"))),
            *(('historical_reference', path) for path in sorted(self.store.historical_reference.glob("*.json"))),
        ]
        seen_project_ids: set[str] = set()
        for source_kind, path in sources:
            try:
                if source_kind == "historical_reference":
                    document = self.store._migrate_project(self.store._read(path))
                else:
                    document, _ = self.store.load_project(path.stem)
                project = document.get("project") if isinstance(document, dict) else None
                if not isinstance(project, dict) or project.get("id") != path.stem:
                    raise PersistenceError("Project identifier does not match its file name.")
                if path.stem in seen_project_ids:
                    raise PersistenceError("Project identifier is duplicated across live and historical-reference evidence.")
                seen_project_ids.add(path.stem)
                documents.append(document)
            except (PersistenceError, AttributeError, KeyError, TypeError, ValueError) as exc:
                malformed.append((path.stem, str(exc)))

        known = {KNOWN_SEED_TEST_PROJECT_ID}
        changed = True
        while changed:
            changed = False
            for document in documents:
                project_id = str(document.get("project", {}).get("id") or "")
                synthetic, _ = is_synthetic_project(document, known)
                if synthetic and project_id not in known:
                    known.add(project_id); changed = True

        index = self._empty()
        for document in documents:
            try:
                record = extract_project_observations(document, known)
            except (ArithmeticError, AttributeError, KeyError, TypeError, ValueError) as exc:
                record = _malformed_project_record(document, str(exc))
            index["projects"][record["project_id"]] = record
        for project_id, detail in malformed:
            index["projects"][project_id] = _malformed_project_record({}, detail, project_id)
        self._reindex(index)
        return self.store.save_historical_index(index, self.name, expected_revision)

    def refresh_project(self, document: dict[str, Any]) -> dict[str, Any]:
        for _ in range(5):
            index = self.load_or_rebuild()
            known = {
                project_id for project_id, record in index.get("projects", {}).items()
                if record.get("synthetic")
            } | {KNOWN_SEED_TEST_PROJECT_ID}
            project_value = document.get("project") if isinstance(document, dict) else None
            project = project_value if isinstance(project_value, dict) else {}
            project_id = str(project.get("id") or "")
            prior = index.get("projects", {}).get(project_id)
            if prior is not None:
                prior_key = (
                    prior.get("synthetic"), prior.get("fingerprint"),
                    (prior.get("project_exclusion") or {}).get("reason"),
                    (prior.get("project_exclusion") or {}).get("detail"),
                )
                synthetic, synthetic_reason = is_synthetic_project(document, known)
                if synthetic:
                    candidate_key = (True, None, "synthetic_project", synthetic_reason)
                else:
                    selected, selection_error = select_frozen_state(document)
                    candidate_key = (
                        False,
                        None if selected is None else _frozen_fingerprint(project_id, selected),
                        None if selection_error is None else selection_error.get("reason"),
                        None if selection_error is None else selection_error.get("detail"),
                    )
                if prior_key == candidate_key:
                    return index
            try:
                record = extract_project_observations(document, known)
            except (ArithmeticError, AttributeError, KeyError, TypeError, ValueError) as exc:
                record = _malformed_project_record(document, str(exc), project_id)
            synthetic_membership_changed = (
                (prior is not None and bool(prior.get("synthetic")) != bool(record.get("synthetic")))
                or (prior is None and bool(record.get("synthetic")))
            )
            if synthetic_membership_changed:
                try:
                    return self.rebuild(expected_revision=int(index.get("revision", 0)))
                except ConflictError:
                    continue
            index.setdefault("projects", {})[record["project_id"]] = record
            index["generated_at"] = _now()
            self._reindex(index)
            try:
                return self.store.save_historical_index(index, self.name, int(index.get("revision", 0)))
            except ConflictError:
                continue
        raise PersistenceError("Historical index could not refresh after concurrent writes.")

    @staticmethod
    def _reindex(index: dict[str, Any]) -> None:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for project in index.get("projects", {}).values():
            for observation in project.get("observations", []):
                grouped.setdefault(observation["code_key"], []).append(deepcopy(observation))
        for observations in grouped.values():
            observations.sort(key=lambda item: (_parse_time(item.get("effective_date")), item.get("project_id", "")))
        index["observations_by_code"] = dict(sorted(grouped.items()))

    @staticmethod
    def _compatible(observation: dict[str, Any], current: dict[str, Any], current_project_id: str) -> bool:
        if observation.get("project_id") == current_project_id:
            return False
        if observation.get("metric_definition") != BID_COST_CODE_SELL_PER_SF_METRIC:
            return False
        current_deduct, historical_deduct = current.get("deduct"), observation.get("deduct")
        project_type_matches = not current.get("project_type") or not observation.get("project_type") or current.get("project_type") == observation.get("project_type")
        return (
            isinstance(current_deduct, bool)
            and isinstance(historical_deduct, bool)
            and current_deduct == historical_deduct
            and project_type_matches
        )

    def comparisons(self, document: dict[str, Any]) -> dict[str, Any]:
        index = self.load_or_rebuild()
        project_id = str(document.get("project", {}).get("id") or "")
        comparisons = []
        for current in _current_rows(document):
            observations = [
                item for item in index.get("observations_by_code", {}).get(current["code_key"], [])
                if self._compatible(item, current, project_id)
            ]
            comparison = {
                "code": current["code"], "description": current["description"],
                **compare_values(current["current"], observations),
                "current_selling_value": current["selling_value"],
                "current_square_feet": current["square_feet"],
            }
            comparison["reference_sample_size"] = sum(item.get("data_classification") == "historical_reference_fixture" for item in observations)
            comparison["warnings"] = [*current["warnings"], *comparison["warnings"]]
            if comparison["reference_sample_size"]:
                comparison["warnings"].append(f'{comparison["reference_sample_size"]} controlled historical-reference bids are included for feature testing.')
            comparisons.append(comparison)
        return {
            "project_revision": document.get("project", {}).get("revision"),
            "metric_definition": deepcopy(METRIC_DEFINITION),
            "minimum_sample": MINIMUM_SAMPLE, "comparable_project_type": document.get("project", {}).get("project_type"),
            "comparisons": comparisons,
        }

    def detail(self, document: dict[str, Any], code: str) -> dict[str, Any]:
        index = self.load_or_rebuild()
        project_id = str(document.get("project", {}).get("id") or "")
        key = canonical_cost_code(code)
        if not key:
            raise ValueError("Cost Code must contain letters or numbers.")
        current = next((row for row in _current_rows(document) if row["code_key"] == key), None)
        if current is None:
            raise ValueError("Cost Code is not present in the current Bid.")
        observations = [
            item for item in index.get("observations_by_code", {}).get(key, [])
            if self._compatible(item, current, project_id)
        ]
        comparison = {
            "code": current["code"], "description": current["description"],
            **compare_values(current["current"], observations),
            "current_selling_value": current["selling_value"], "current_square_feet": current["square_feet"],
        }
        comparison["reference_sample_size"] = sum(item.get("data_classification") == "historical_reference_fixture" for item in observations)
        comparison["warnings"] = [*current["warnings"], *comparison["warnings"]]
        if comparison["reference_sample_size"]:
            comparison["warnings"].append(f'{comparison["reference_sample_size"]} controlled historical-reference bids are included for feature testing.')
        diagnostics: list[dict[str, Any]] = []
        for candidate_id, project in index.get("projects", {}).items():
            if candidate_id == project_id:
                reason, detail = "current_project", "Current project is excluded from its own comparison."
            elif project.get("project_exclusion"):
                reason, detail = project["project_exclusion"].get("reason"), project["project_exclusion"].get("detail")
            else:
                code_exclusions = [item for item in project.get("exclusions", []) if item.get("code_key") == key]
                if code_exclusions:
                    reason, detail = code_exclusions[0].get("reason"), code_exclusions[0].get("detail")
                else:
                    candidate = next((item for item in project.get("observations", []) if item.get("code_key") == key), None)
                    if candidate and not self._compatible(candidate, current, project_id):
                        reason, detail = "incompatible_context", "Metric definition or deduct context differs from the current Cost Code."
                    elif candidate:
                        continue
                    else:
                        reason, detail = "code_not_present", "Selected historical state does not contain this Cost Code metric."
            diagnostics.append({
                "project_id": candidate_id, "project_name": project.get("project_name") or candidate_id,
                "reason": reason, "detail": detail,
            })
        counts: dict[str, int] = {}
        for item in diagnostics:
            counts[item["reason"]] = counts.get(item["reason"], 0) + 1
        return {
            "project_revision": document.get("project", {}).get("revision"),
            "metric_definition": deepcopy(METRIC_DEFINITION), "minimum_sample": MINIMUM_SAMPLE,
            "comparable_project_type": document.get("project", {}).get("project_type"),
            "comparison": comparison, "observations": deepcopy(observations),
            "provenance": {
                "selection_rule": "awarded_snapshot_else_latest_immutable_submitted_revision",
                "historical_calculation": "frozen_values_only_no_recalculation",
                "metric_definition_id": BID_COST_CODE_SELL_PER_SF_METRIC,
                "index_schema": index.get("schema"), "index_version": index.get("version"),
                "index_revision": index.get("revision"), "index_generated_at": index.get("generated_at"),
            },
            "rules": [
                "Use one observation per project and Cost Code: awarded snapshot first, otherwise latest immutable submitted revision.",
                "Exclude the current project, synthetic/test projects, working-only data, incompatible metrics, malformed values, and zero or missing Square Footage.",
                "When both records identify a Project Type, compare only the same Project Type.",
                "Controlled historical-reference fixtures are visibly classified and may be used for feature testing; replace them with completed company bids for production benchmarking.",
                "Value is frozen Cost Code selling value; Square Footage is matching Frame Takeoff plus Borrowed Lite area counted once.",
                f"Require at least {MINIMUM_SAMPLE} comparable projects before assigning Aggressive, Normal, or Conservative.",
                "Quartiles use linear interpolation at (n - 1) × p; current percentile uses midrank ties.",
            ],
            "exclusion_diagnostics": {"counts": dict(sorted(counts.items())), "projects": diagnostics},
        }
