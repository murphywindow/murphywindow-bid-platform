from __future__ import annotations

import io
import json
import logging
import os
import secrets
import time
import hashlib
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from .api_models import (
    AddSectionMaterialCommand, AlternateNameCommand, BidSourceEditCommand, CustomCostCodeCommand,
    MasterRecordCommand, RemoveCostCodeCommand, RemoveSectionMaterialCommand,
)
from .alternates import add_record as add_alternate_record, alternate_label, new_alternate, remove_record as remove_alternate_record, reset_override as reset_alternate_override, set_override as set_alternate_override
from .calculations import dollars_in_words, normalize_code, split_variant
from .custom_code_auth import verify_custom_code_credentials
from .master_data import (
    MasterDataRepository, build_search_index, search_master_data, seed_master_data,
    upsert_organization, upsert_person_organization_contact, upsert_text_entity,
)
from .migrations import MigrationError, migrate_project_document
from .persistence import ConflictError, JsonStore, PersistenceError
from .generator import generate_test_project
from .historical import HistoricalMetricIndex
from .mileage import MileageError, calculate_driving_mileage, search_addresses
from .project_commands import (
    add_section_material, cost_code_dependencies, new_custom_cost_code, remove_cost_code_cascade,
    remove_section_material,
    preserve_quote_square_feet_intent, refresh_labor_rate_selection,
    strip_ui_working_rows, validate_project_inputs,
)
from .schema import CONFIG_VERSION, INTERCHANGE_VERSION, SCHEMA_VERSION, default_configuration, duplicate_project, new_project, now, test_project, uid
from .numeric_precision import validate_decimal_precision
from .version import SOFTWARE_RELEASE_DATE, SOFTWARE_VERSION
from .services import (
    DomainError, ROLES, activate, audit, bump_bid_version, calculate_project, create_change_order,
    edit_bid_source, job_data, provisional_closeout, redact, reestimate_contract, require,
    save_sov, submit, update_change_order_status,
)
from .proposals import (
    branch_from_snapshot, compare_snapshots, create_proposal_snapshot,
    historical_document, void_proposal,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("MURPHY_BID_DATA_DIR", BASE_DIR / "data"))
STATIC_DIR = BASE_DIR / "app" / "static"
store = JsonStore(DATA_DIR)
logger = logging.getLogger(__name__)
_override_sessions: dict[str, dict[str, Any]] = {}
_override_lock = Lock()
_OVERRIDE_TTL_SECONDS = 8 * 60 * 60


def custom_code_secret_path() -> Path:
    return store.root / "secrets" / "custom-code.json"


def _valid_override_token(token: str | None, *, actor: str, project_id: str, page: str) -> bool:
    if not token:
        return False
    with _override_lock:
        session = _override_sessions.get(token)
        if not session or session["expires_at"] <= time.time():
            _override_sessions.pop(token, None)
            return False
        return bool(
            secrets.compare_digest(session["actor"], actor)
            and session["project_id"] == project_id and session["page"] == page
        )


def ensure_seed() -> None:
    path = store.configurations / f"{CONFIG_VERSION}.json"
    if not path.exists():
        store.save_configuration(default_configuration())
    test_id = "prj_00000000000000000000000000004320"
    if not store.project_path(test_id).exists():
        doc = test_project()
        calculate_project(doc, store.load_configuration(CONFIG_VERSION))
        store.save_project(doc, -1)
    else:
        # Update only the untouched generated sandbox to the current immutable
        # seed configuration. Any real user edit makes it ineligible.
        # Any user edit (bid sequence > 0 or file revision > 1) makes it ineligible.
        doc, _ = store.load_project(test_id)
        bid_sequence = int(doc["project"].get("bid_version", {}).get("sequence", 0))
        if doc["project"].get("configuration_id") != CONFIG_VERSION and bid_sequence == 0 and int(doc["project"].get("revision", 0)) == 1:
            prior_config = doc["project"].get("configuration_id")
            doc["project"]["configuration_id"] = CONFIG_VERSION
            doc.setdefault("configuration_lineage", []).append({"configuration_id": CONFIG_VERSION, "adopted_at": now(), "actor": "System seed migration"})
            calculate_project(doc, store.load_configuration(CONFIG_VERSION))
            bump_bid_version(doc, "seed_configuration_adopted")
            audit(doc, "System seed migration", "Systems Administrator", "project", test_id, "configuration_adopted",
                  {"configuration_id": prior_config}, {"configuration_id": CONFIG_VERSION}, "Untouched test project adopted the current seed configuration")
            store.save_project(doc, 1)


def master_repository() -> MasterDataRepository:
    """Bind the reusable directory to the current store (including test stores)."""
    return MasterDataRepository(store)


def historical_index() -> HistoricalMetricIndex:
    """Bind the rebuildable historical index to the current (including test) store."""
    return HistoricalMetricIndex(store)


def refresh_historical_index(document: dict) -> None:
    """Refresh derived evidence without making a completed commercial save fail."""
    try:
        historical_index().refresh_project(document)
    except Exception:
        logger.exception("Historical comparison index refresh failed for %s", document.get("project", {}).get("id"))


def _reusable_projection(document: dict | None) -> dict:
    if not document:
        return {}
    project = document.get("project", {})
    return {
        "project": {
            key: project.get(key)
            for key in (
                "estimator", "plan_source", "owner_name", "owner_legal_name", "owner_address",
                "owner_website", "owner_phone", "owner_email", "architect", "engineer",
                "general_contractor", "construction_manager",
            )
        },
        "contacts": document.get("contacts", []),
        "quote_vendors": [row.get("vendor") for row in document.get("quotes", [])],
    }


def index_reusable_history(document: dict, prior: dict | None = None) -> None:
    """Index changed reusable values without modifying any project snapshot."""
    if prior is not None and _reusable_projection(prior) == _reusable_projection(document):
        return
    repository = master_repository()
    current = repository.load_or_create()
    updated = seed_master_data([document], current)
    repository.save(updated, int(current.get("revision", 0)))


def apply_manual_quote_selection_changes(document: dict, changes: list[dict]) -> None:
    """A changed Used checkbox switches only its Cost Code group to manual mode."""
    changed_indexes: set[int] = set()
    for change in changes:
        parts = str(change.get("path") or "").split(".")
        if len(parts) == 3 and parts[0] == "quotes" and parts[2] == "used" and parts[1].isdigit():
            changed_indexes.add(int(parts[1]))
    quotes = document.get("quotes", [])
    selection = document.setdefault("working_estimate", {}).setdefault("quote_selection_by_code", {})
    for index in changed_indexes:
        if index >= len(quotes):
            continue
        code = str(quotes[index].get("code") or "").strip().upper()
        if not code:
            continue
        selected = [
            row.get("id") for row in quotes
            if str(row.get("code") or "").strip().upper() == code and row.get("used") and row.get("id")
        ]
        selection[code] = {"mode": "manual", "selected_quote_ids": selected, "source": "estimator_used_change"}


def preserve_quote_selection_across_group_changes(document: dict, prior_document: dict) -> None:
    """Move only deliberate Used provenance with a Quote's stable identity."""
    prior_quotes = {str(row.get("id")): row for row in prior_document.get("quotes", []) if row.get("id")}
    selection = document.setdefault("working_estimate", {}).setdefault("quote_selection_by_code", {})

    def entry_for(code: Any) -> tuple[str, dict | None]:
        target = normalize_code(split_variant(str(code or ""))[1])
        for key, value in selection.items():
            if normalize_code(split_variant(str(key or ""))[1]) == target:
                return key, value if isinstance(value, dict) else {"mode": value, "selected_quote_ids": []}
        return str(code or ""), None

    for quote in document.get("quotes", []):
        prior = prior_quotes.get(str(quote.get("id")))
        if not prior or normalize_code(str(prior.get("code") or "")) == normalize_code(str(quote.get("code") or "")):
            continue
        old_key, old_entry = entry_for(prior.get("code"))
        if not old_entry or str(old_entry.get("mode") or "").lower() not in {"manual", "legacy_manual"}:
            continue
        quote_id = str(quote.get("id"))
        selected = set(map(str, old_entry.get("selected_quote_ids", [])))
        was_selected = quote_id in selected
        selected.discard(quote_id)
        old_entry["selected_quote_ids"] = sorted(selected)
        old_entry.setdefault("source", "preserved_manual_group_provenance")
        selection[old_key] = old_entry
        if was_selected:
            new_key, new_entry = entry_for(quote.get("code"))
            new_entry = new_entry or {"mode": "manual", "selected_quote_ids": [], "source": "quote_group_change"}
            new_entry["mode"] = "manual"
            new_entry["selected_quote_ids"] = sorted(set(map(str, new_entry.get("selected_quote_ids", []))) | {quote_id})
            selection[new_key] = new_entry


def apply_line_acknowledgement_metadata(document: dict, changes: list[dict], actor: str) -> None:
    for change in changes:
        path = str(change.get("path") or "")
        parts = path.split(".")
        row = None
        acknowledgement = None
        if len(parts) == 5 and parts[0] == "takeoff_sections" and parts[2] == "lines" and parts[1].isdigit() and parts[3].isdigit() and parts[4] == "missing_quantity_acknowledged":
            sections = document.get("takeoff_sections", [])
            if int(parts[1]) < len(sections) and int(parts[3]) < len(sections[int(parts[1])].get("lines", [])):
                row = sections[int(parts[1])]["lines"][int(parts[3])]
                acknowledgement = "missing_quantity"
        elif len(parts) == 3 and parts[0] == "doors" and parts[1].isdigit() and parts[2] == "missing_quantity_acknowledged":
            rows = document.get("doors", [])
            if int(parts[1]) < len(rows):
                row, acknowledgement = rows[int(parts[1])], "missing_quantity"
        elif len(parts) == 3 and parts[0] == "labor_estimates" and parts[1].isdigit() and parts[2] == "stale_acknowledged":
            rows = document.get("labor_estimates", [])
            if int(parts[1]) < len(rows):
                row, acknowledgement = rows[int(parts[1])], "stale"
        if row is None:
            continue
        enabled = bool(change.get("new"))
        prefix = "missing_quantity" if acknowledgement == "missing_quantity" else "stale"
        row[f"{prefix}_acknowledged_at"] = now() if enabled else None
        row[f"{prefix}_acknowledged_by"] = actor if enabled else None


def datapoint_audit_identity(document: dict, path: str, project_id: str) -> tuple[str, str, str]:
    """Give commercially meaningful code changes specific audit identities."""
    parts = path.split(".")
    try:
        if len(parts) == 3 and parts[0] == "quotes" and parts[2] == "code":
            row = document.get("quotes", [])[int(parts[1])]
            return "quote", str(row.get("id") or project_id), "quote_grouping_code_change"
        if (len(parts) == 5 and parts[0] == "takeoff_sections" and
                parts[2] == "additional_materials" and parts[4] == "cost_code"):
            row = document.get("takeoff_sections", [])[int(parts[1])].get("additional_materials", [])[int(parts[3])]
            return "installation_material", str(row.get("id") or project_id), "installation_material_actual_cost_code_change"
    except (IndexError, TypeError, ValueError):
        pass
    return "project_datapoint", project_id, "data_point_change"


def rate_override_audit_context(document: dict, config: dict, path: str) -> dict | None:
    """Return controlled/override/effective values for a rate-override audit."""
    parts = path.split(".")
    if (
        len(parts) == 5 and parts[0] == "takeoff_sections" and parts[1].isdigit()
        and parts[2] == "material_overrides" and parts[4] in {"rate", "rate_override"}
    ):
        sections = document.get("takeoff_sections", [])
        if int(parts[1]) >= len(sections):
            return None
        rule_id = parts[3]
        rule = next((item for item in config.get("material_rules", []) if item.get("id") == rule_id), {})
        result = next((
            item for item in sections[int(parts[1])].get("material_results", [])
            if item.get("material_rule_id") == rule_id
        ), {})
        return {
            "controlled_rate": rule.get("rate"),
            "project_rate_override": result.get("rate_override"),
            "effective_rate": result.get("effective_rate"),
            "configuration_id": config.get("id"),
        }
    if len(parts) == 3 and parts[0] == "labor_estimates" and parts[1].isdigit() and parts[2] == "rate_override":
        rows = document.get("labor_estimates", [])
        if int(parts[1]) >= len(rows):
            return None
        row = rows[int(parts[1])]
        return {
            "controlled_rate": row.get("calculated_controlled_rate"),
            "project_rate_override": row.get("rate_override"),
            "effective_rate": row.get("calculated_effective_rate"),
            "configuration_id": config.get("id"),
        }
    return None


def ensure_master_history() -> None:
    documents = []
    for path in sorted(store.projects.glob("*.json")):
        try:
            document, _ = store.load_project(path.stem)
            documents.append(document)
        except PersistenceError:
            continue
    if documents:
        master_repository().seed_projects(documents)


ensure_seed()
ensure_master_history()
app = FastAPI(title="Murphy Window Bid Platform", version=SOFTWARE_VERSION, docs_url="/api/docs", redoc_url=None)


@app.middleware("http")
async def prevent_stale_frontend(request: Request, call_next):
    """The local UI is developed in place; browsers must not reuse old shells/assets."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith(("/projects/", "/assets/", "/api/")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def identity(x_actor: str = Header("Local User"), x_role: str = Header("Estimator")) -> tuple[str, str]:
    if x_role not in ROLES:
        raise HTTPException(400, detail={"code": "invalid_role", "message": f"Unknown local role: {x_role}"})
    return x_actor.strip() or "Local User", x_role


def fail(exc: Exception) -> None:
    if isinstance(exc, DomainError):
        status = (
            403 if exc.code in {"forbidden", "custom_code_authorization_failed", "invalid_override_credentials", "override_required"}
            else 404 if exc.code == "not_found"
            else 409 if exc.code in {"duplicate_activation", "duplicate_proposal", "proposal_already_voided", "immutable_snapshot"}
            else 422
        )
        raise HTTPException(status, detail={"code": exc.code, "message": str(exc), "details": exc.details}) from exc
    if isinstance(exc, ConflictError):
        raise HTTPException(409, detail={"code": "concurrent_edit", "message": str(exc)}) from exc
    if isinstance(exc, PersistenceError):
        raise HTTPException(500, detail={"code": "persistence_error", "message": str(exc)}) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(422, detail={"code": "validation_error", "message": str(exc)}) from exc
    raise exc


def load(project_id: str) -> tuple[dict, dict]:
    doc, _ = store.load_project(project_id)
    config = store.load_configuration(doc["project"]["configuration_id"])
    return doc, config


def _commercial_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _commercial_impacts(before: dict, after: dict) -> list[dict[str, Any]]:
    """List exact dollar and square-foot changes without applying display rounding."""
    impacts: list[dict[str, Any]] = []

    def add(scope: str, label: str, value_type: str, prior: Any, current: Any) -> None:
        old, new = _commercial_decimal(prior), _commercial_decimal(current)
        if old == new:
            return
        impacts.append({
            "scope": scope, "label": label, "value_type": value_type,
            "before": None if old is None else format(old, "f"),
            "after": None if new is None else format(new, "f"),
            "delta": None if old is None or new is None else format(new - old, "f"),
        })

    before_estimate, after_estimate = before.get("working_estimate", {}), after.get("working_estimate", {})
    before_totals, after_totals = before_estimate.get("totals", {}), after_estimate.get("totals", {})
    for key, label, value_type in (
        ("direct_cost", "Direct Cost", "currency"),
        ("markup_profit", "Margin Dollars", "currency"),
        ("selling_value", "Selling Value", "currency"),
        ("contingency", "Contingency", "currency"),
        ("bond", "Bond", "currency"),
        ("square_feet", "Total ft²", "square_footage"),
        ("price_per_square_foot", "Value/ft²", "currency_per_unit"),
    ):
        add("Bid total", label, value_type, before_totals.get(key), after_totals.get(key))

    def summaries(document: dict) -> dict[str, dict]:
        return {str(row.get("code") or row.get("id") or "Unassigned"): row for row in document.get("working_estimate", {}).get("cost_code_summaries", [])}

    before_summaries, after_summaries = summaries(before), summaries(after)
    for code in sorted(set(before_summaries) | set(after_summaries)):
        old, new = before_summaries.get(code, {}), after_summaries.get(code, {})
        for keys, label, value_type in (
            (("direct_cost", "cost"), "Direct Cost", "currency"),
            (("margin_dollars",), "Margin Dollars", "currency"),
            (("selling_value", "value"), "Selling Value", "currency"),
            (("total_square_feet", "square_feet"), "Total ft²", "square_footage"),
            (("dollars_per_square_foot",), "Value/ft²", "currency_per_unit"),
        ):
            prior = next((old.get(key) for key in keys if old.get(key) is not None), None)
            current = next((new.get(key) for key in keys if new.get(key) is not None), None)
            add(f"Cost Code {code}", label, value_type, prior, current)

    before_alternates = {str(row.get("id")): row for row in before.get("alternates", [])}
    after_alternates = {str(row.get("id")): row for row in after.get("alternates", [])}
    for alternate_id in sorted(set(before_alternates) | set(after_alternates)):
        old_row, new_row = before_alternates.get(alternate_id, {}), after_alternates.get(alternate_id, {})
        old, new = old_row.get("calculated", {}), new_row.get("calculated", {})
        scope = f"{new_row.get('key') or old_row.get('key') or 'Alternate'} — {new_row.get('name') or old_row.get('name') or 'Alternate'}"
        add(scope, "Direct Cost Delta", "currency", old.get("direct_cost_delta"), new.get("direct_cost_delta"))
        add(scope, "Selling Value Delta", "currency", old.get("selling_value_delta"), new.get("selling_value_delta"))

    return impacts


def _configuration_candidate(source: dict, supplied: Any) -> dict:
    candidate = deepcopy(supplied if isinstance(supplied, dict) else source)
    settings = candidate.setdefault("application_settings", {})
    settings["decimal_precision"] = validate_decimal_precision(settings.get("decimal_precision"))
    if "csi_references" not in candidate:
        candidate["csi_references"] = deepcopy(source.get("csi_references", []))
        candidate["cost_code_reference"] = deepcopy(source.get("cost_code_reference"))
    return candidate


def save_command(doc: dict, expected_revision: int, actor: str, role: str, operation: str) -> dict:
    audit(doc, actor, role, "project", doc["project"]["id"], operation, None, {"lifecycle_state": doc["project"]["lifecycle_state"]}, operation.replace("_", " ").title())
    return store.save_project(doc, expected_revision)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "data_directory": str(DATA_DIR),
        "software_version": SOFTWARE_VERSION,
        "software_release_date": SOFTWARE_RELEASE_DATE,
        "schema_version": SCHEMA_VERSION,
    }


@app.get("/api/roles")
def roles() -> dict:
    return {"roles": ROLES}


def _master_result(directory: dict, result: dict) -> dict:
    entity_kind, record_id = result.get("entity_kind"), result.get("id")
    collection = {
        "organization": "organizations",
        "contact": "person_organization_contacts",
        "text": "text_entities",
    }.get(entity_kind)
    record = next((item for item in directory.get(collection or "", []) if item.get("id") == record_id), {})
    enriched = {**deepcopy(record), **result}
    if entity_kind == "contact":
        organization = next((
            item for item in directory.get("organizations", [])
            if item.get("id") == record.get("organization_id")
        ), None)
        enriched["organization"] = organization.get("display_name", "") if organization else ""
        enriched["organization_name"] = enriched["organization"]
        enriched["role"] = (record.get("roles") or [""])[0]
    return enriched


@app.get("/api/master-data/search")
def master_data_search(q: str, kind: str = "organizations", limit: int = 10,
                       actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    try:
        directory = master_repository().load_or_create()
        kind_map = {
            "organizations": ("organization", None),
            "organization": ("organization", None),
            "owners": ("organization", None),
            "owner": ("organization", None),
            "contacts": ("contact", None),
            "contact": ("contact", None),
            "estimators": ("text", "estimator"),
            "estimator": ("text", "estimator"),
            "plan_sources": ("text", "plan_source"),
            "plan_source": ("text", "plan_source"),
            "contact_roles": ("text", "contact_role"),
            "contact_role": ("text", "contact_role"),
        }
        entity_kind, text_kind = kind_map.get(kind, (None, None))
        if entity_kind is None:
            raise DomainError("Unknown reusable master-data kind.", "invalid_master_data_kind")
        raw = search_master_data(directory, q, entity_kinds=[entity_kind], limit=100 if text_kind or kind in {"owners", "owner"} else limit)
        results = [_master_result(directory, item) for item in raw["results"]]
        if kind in {"owners", "owner"}:
            results = [item for item in results if "owner" in {
                str(value).strip().lower() for value in item.get("classifications", [])
            }][:max(1, min(limit, 100))]
        if text_kind:
            results = [item for item in results if item.get("kind") == text_kind][:max(1, min(limit, 100))]
        return {**raw, "results": results, "kind": kind}
    except Exception as exc:
        fail(exc)


@app.post("/api/master-data/{kind}")
def save_master_record(kind: str, command: MasterRecordCommand,
                       actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        repository = master_repository()
        directory = repository.load_or_create()
        expected = int(directory.get("revision", 0) if command.expected_revision is None else command.expected_revision)
        record = command.model_dump(exclude_none=True)
        record.pop("expected_revision", None)
        record.pop("update_scope", None)
        if kind in {"organizations", "organization"}:
            if record.get("phone") and not record.get("primary_phone"):
                record["primary_phone"] = record["phone"]
            target = next((item for item in directory.get("organizations", []) if item.get("id") == record.get("id")), None)
            if target is not None:
                for field in ("display_name", "legal_name", "aliases", "classifications", "address", "website", "primary_phone", "email", "notes"):
                    if field in record:
                        target[field] = deepcopy(record[field])
            saved_record = upsert_organization(directory, record)
            entity_kind = "organization"
        elif kind in {"contacts", "contact"}:
            if record.get("organization") and not record.get("organization_id"):
                organization = upsert_organization(directory, {"display_name": record["organization"]})
                record["organization_id"] = organization["id"]
            if record.get("display_name") and not record.get("name"):
                record["name"] = record["display_name"]
            if record.get("role"):
                record["roles"] = list(dict.fromkeys([*record.get("roles", []), record["role"]]))
            target = next((item for item in directory.get("person_organization_contacts", []) if item.get("id") == record.get("id")), None)
            if target is not None:
                for field in ("name", "organization_id", "aliases", "roles", "position", "email", "office_phone", "mobile_phone", "notes"):
                    if field in record:
                        target[field] = deepcopy(record[field])
            saved_record = upsert_person_organization_contact(directory, record)
            entity_kind = "contact"
        else:
            text_kinds = {
                "estimators": "estimator", "estimator": "estimator",
                "plan_sources": "plan_source", "plan_source": "plan_source",
                "contact_roles": "contact_role", "contact_role": "contact_role",
            }
            text_kind = text_kinds.get(kind)
            if text_kind is None:
                raise DomainError("Unknown reusable master-data kind.", "invalid_master_data_kind")
            record["kind"] = text_kind
            saved_record = upsert_text_entity(directory, record)
            entity_kind = "text"
        build_search_index(directory)
        saved_directory = repository.save(directory, expected)
        response_record = _master_result(saved_directory, {"id": saved_record["id"], "entity_kind": entity_kind})
        return {"record": response_record, "revision": saved_directory["revision"], "updated_by": actor}
    except Exception as exc:
        fail(exc)


@app.get("/api/address-search")
def address_search(q: str, limit: int = 5, request_id: str | None = None,
                   actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    try:
        if len(str(q or "").strip()) < 3:
            return {"query": q, "results": [], "provider": None, "attribution": None, "cache_hit": False, "request_id": request_id}
        return search_addresses(q, limit=limit, request_id=request_id)
    except MileageError as exc:
        fail(DomainError(str(exc), "address_lookup_failed"))
    except Exception as exc:
        fail(exc)


@app.get("/api/projects")
def projects(actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    return {"projects": store.list_projects()}


@app.post("/api/projects")
def create_project(payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        doc = new_project(payload.get("name", "Untitled Project"), actor, role)
        config = store.load_configuration(CONFIG_VERSION)
        calculate_project(doc, config)
        saved = store.save_project(doc, -1)
        index_reusable_history(saved)
        refresh_historical_index(saved)
        return {"project": redact(saved, role)}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/generate-test")
def generate_project_for_testing(payload: dict = Body(default={}), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    """Create a persisted, curated synthetic draft. An optional seed makes its content reproducible."""
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        config = store.load_configuration(CONFIG_VERSION)
        doc = generate_test_project(config, actor, role, payload.get("seed"))
        calculate_project(doc, config)
        saved = store.save_project(doc, -1)
        index_reusable_history(saved)
        refresh_historical_index(saved)
        generated = saved["project"].get("test_generation", {})
        alternate_added = lambda collection: sum(len(alt.get("changes", {}).get(collection, {}).get("added", []))
                                                 for alt in saved.get("alternates", []))
        alternate_section_frames = sum(len(section.get("lines", [])) for alt in saved.get("alternates", [])
                                       for section in alt.get("changes", {}).get("takeoff_sections", {}).get("added", []))
        return {
            "project": redact(saved, role),
            "generation": {
                **generated,
                "counts": {
                    "contacts": len(saved.get("contacts", [])), "cost_codes": len(saved.get("cost_codes", [])),
                    "quotes": len(saved.get("quotes", [])) + alternate_added("quotes"),
                    "frame_sections": len(saved.get("takeoff_sections", [])) + alternate_added("takeoff_sections"),
                    "frame_rows": sum(len(section.get("lines", [])) for section in saved.get("takeoff_sections", [])) +
                                  alternate_section_frames + alternate_added("frames"),
                    "doors": len(saved.get("doors", [])), "equipment": len(saved.get("equipment", [])),
                    "borrowed_lites": len(saved.get("borrowed_lites", [])), "labor_lines": len(saved.get("labor_estimates", [])),
                },
            },
        }
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, recover: bool = False, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, recovered_from = store.load_project(project_id, recover=recover)
        if recovered_from:
            audit(doc, actor, role, "project", project_id, "recovery_preview", None, {"backup": recovered_from}, "Primary JSON was invalid")
        configuration = store.load_configuration(doc["project"]["configuration_id"])
        calculate_project(doc, configuration)
        return {"project": redact(doc, role), "recovered_from": recovered_from, "backups": store.backup_names(project_id)}
    except Exception as exc:
        fail(exc)


def _historical_current_project(project_id: str) -> dict:
    """Load and authoritatively recalculate only the current project."""
    document, _ = store.load_project(project_id)
    configuration = store.load_configuration(document["project"]["configuration_id"])
    return calculate_project(deepcopy(document), configuration)


def _historical_scenario_project(project_id: str, alternate_id: str | None = None) -> dict:
    """Return the selected scenario using the same calculated historical engine.

    Alternate calculations remain authoritative in ``calculate_project``.  This
    adapter only presents that effective estimate as the current comparison
    state; it does not duplicate percentile or classification logic.
    """
    document = _historical_current_project(project_id)
    if not alternate_id:
        return document
    alternate = next((row for row in document.get("alternates", []) if str(row.get("id")) == str(alternate_id)), None)
    if not alternate:
        raise DomainError("Alternate was not found.", "not_found")
    effective = alternate.get("calculated", {}).get("effective_estimate")
    if not isinstance(effective, dict):
        raise DomainError("Alternate effective estimate is unavailable.", "alternate_not_calculated")
    document["working_estimate"] = deepcopy(effective)
    return document


@app.get("/api/projects/{project_id}/historical/bid-cost-codes")
def bid_cost_code_history(project_id: str, alternate_id: str | None = None,
                          actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    try:
        document = _historical_scenario_project(project_id, alternate_id)
        result = historical_index().comparisons(document)
        result["alternate_id"] = alternate_id
        return result
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/historical/bid-cost-code")
def bid_cost_code_history_detail(project_id: str, code: str, alternate_id: str | None = None,
                                 actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    try:
        if not str(code or "").strip():
            raise DomainError("Cost Code is required.", "missing_cost_code")
        document = _historical_scenario_project(project_id, alternate_id)
        result = historical_index().detail(document, code)
        result["alternate_id"] = alternate_id
        return result
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/alternates")
def create_alternate(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        document, configuration = load(project_id)
        expected = int(payload.get("expected_revision", document["project"]["revision"]))
        alternate = new_alternate(document, payload.get("name"))
        document.setdefault("alternates", []).append(alternate)
        calculate_project(document, configuration)
        audit(document, actor, role, "alternate", alternate["id"], "alternate_create", None, deepcopy(alternate), "Created Base-plus-delta alternate")
        saved = store.save_project(document, expected)
        return {"project": redact(saved, role), "alternate": deepcopy(next(row for row in saved["alternates"] if row["id"] == alternate["id"]))}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/frame-sections/{section_id}/materials")
def create_frame_section_material(project_id: str, section_id: str, payload: AddSectionMaterialCommand,
                                  actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        document, configuration = load(project_id)
        material = add_section_material(document, section_id, payload.model_dump(), configuration)
        calculate_project(document, configuration)
        audit(document, actor, role, "frame_installation_material", material["id"], "material_add", None,
              deepcopy(material), "Added project-specific Frame Spec Section Installation Material")
        saved = store.save_project(document, payload.expected_revision)
        return {"project": redact(saved, role), "material": deepcopy(material)}
    except Exception as exc:
        fail(exc)


@app.delete("/api/projects/{project_id}/frame-sections/{section_id}/materials/{material_id}")
def delete_frame_section_material(project_id: str, section_id: str, material_id: str,
                                  payload: RemoveSectionMaterialCommand = Body(...),
                                  actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        document, configuration = load(project_id)
        result = remove_section_material(document, section_id, material_id,
                                         confirm_dependencies=payload.confirm_dependencies,
                                         controlled_materials=configuration.get("material_rules", []))
        calculate_project(document, configuration)
        audit(document, actor, role, "frame_installation_material", material_id, "material_remove",
              result["material"], None, payload.reason)
        saved = store.save_project(document, payload.expected_revision)
        return {"project": redact(saved, role), "removed": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/alternates/{alternate_id}/change")
def change_alternate(project_id: str, alternate_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        document, configuration = load(project_id)
        expected = int(payload.get("expected_revision", document["project"]["revision"]))
        alternate = next((row for row in document.get("alternates", []) if row.get("id") == alternate_id), None)
        if not alternate:
            raise DomainError("Alternate was not found.", "not_found")
        operation, collection = payload.get("operation"), str(payload.get("collection") or "")
        if operation == "add":
            add_alternate_record(alternate, collection, payload.get("record") or {})
        elif operation == "remove":
            remove_alternate_record(alternate, collection, str(payload.get("record_id") or ""))
        elif operation == "override":
            record_id, field = str(payload.get("record_id") or ""), str(payload.get("field") or "")
            base_record = next((row for row in document.get(collection, []) if str(row.get("id")) == record_id), None)
            if collection == "frames":
                base_record = next((line for section in document.get("takeoff_sections", []) for line in section.get("lines", []) if str(line.get("id")) == record_id), None)
            if not base_record or not field:
                raise DomainError("The Base record or override field was not found.", "not_found")
            current: Any = base_record
            for part in field.split("."):
                current = current.get(part) if isinstance(current, dict) else None
            set_alternate_override(alternate, collection, record_id, field, current, payload.get("value"))
        elif operation == "reset":
            reset_alternate_override(alternate, collection, str(payload.get("record_id") or ""), str(payload.get("field") or ""))
        else:
            raise DomainError("Alternate operation must be add, remove, override, or reset.", "invalid_alternate_operation")
        if "name" in payload:
            alternate["name"] = str(payload.get("name") or "").strip() or alternate["name"]
        if "customer_description" in payload:
            alternate["customer_description"] = str(payload.get("customer_description") or "")
        calculate_project(document, configuration)
        audit(document, actor, role, "alternate", alternate_id, f"alternate_{operation}", None,
              {"collection": collection, "record_id": payload.get("record_id"), "field": payload.get("field")}, "Updated Base-plus-delta alternate")
        saved = store.save_project(document, expected)
        return {"project": redact(saved, role), "alternate": deepcopy(next(row for row in saved["alternates"] if row["id"] == alternate_id))}
    except Exception as exc:
        fail(exc)


@app.patch("/api/projects/{project_id}/alternates/{alternate_id}/name")
def rename_alternate(project_id: str, alternate_id: str, command: AlternateNameCommand,
                     actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        document, configuration = load(project_id)
        alternate = next((row for row in document.get("alternates", []) if str(row.get("id")) == alternate_id), None)
        if not alternate:
            raise DomainError("Alternate was not found.", "not_found")
        prior = str(alternate.get("name") or "")
        current = str(command.name or "").strip()
        alternate["name"] = current
        calculate_project(document, configuration)
        operation = "alternate_name_cleared" if prior and not current else (
            "alternate_name_set" if not prior and current else "alternate_name_changed"
        )
        correlation = uid("cor")
        audit(document, actor, role, "alternate", alternate_id, operation,
              {"name": prior}, {"name": current}, command.reason, correlation)
        bump_bid_version(document, "alternate_name_change")
        saved = store.save_project(document, command.expected_revision)
        return {"project": redact(saved, role), "alternate": deepcopy(next(
            row for row in saved["alternates"] if str(row.get("id")) == alternate_id
        )), "correlation_id": correlation}
    except Exception as exc:
        fail(exc)


@app.post("/api/session-overrides")
def create_session_override(payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "configuration")
        project_id, page = str(payload.get("project_id") or ""), str(payload.get("page") or "")
        if page != "project" or not store.project_path(project_id).exists():
            raise DomainError("This page does not support a session override.", "invalid_override_scope")
        if not verify_custom_code_credentials(
            str(payload.get("username") or ""), str(payload.get("password") or ""),
            secret_file=custom_code_secret_path(),
        ):
            raise DomainError("The Administrator override credential was not accepted.", "invalid_override_credentials")
        token = secrets.token_urlsafe(32)
        with _override_lock:
            _override_sessions[token] = {
                "actor": actor, "project_id": project_id, "page": page,
                "expires_at": time.time() + _OVERRIDE_TTL_SECONDS,
            }
        return {"token": token, "page": page, "expires_in_seconds": _OVERRIDE_TTL_SECONDS}
    except Exception as exc:
        fail(exc)


@app.delete("/api/session-overrides")
def revoke_session_override(x_override_token: str | None = Header(default=None),
                            actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    with _override_lock:
        if x_override_token:
            _override_sessions.pop(x_override_token, None)
    return {"revoked": True}


@app.put("/api/projects/{project_id}")
def save_project(project_id: str, payload: dict = Body(...), x_override_token: str | None = Header(default=None),
                 actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        incoming = strip_ui_working_rows(deepcopy(payload["project"]))
        if incoming.get("project", {}).get("id") != project_id:
            raise DomainError("Project identifier does not match route.")
        expected = int(payload.get("expected_revision", incoming["project"].get("revision", 0)))
        current, config = load(project_id)
        override_active = role == "Systems Administrator" and _valid_override_token(
            x_override_token, actor=actor, project_id=project_id, page="project"
        )
        require(role, "edit_estimate")
        if incoming["project"].get("miles_from_rogers") != current["project"].get("miles_from_rogers") and not override_active:
            raise DomainError("Drive miles are calculated from the selected address and are locked.", "calculated_field_locked")
        # Client editing never receives authority to mutate immutable/lifecycle collections.
        if incoming.get("project", {}).get("historical_proposal"):
            raise DomainError("Historical proposal snapshots cannot be saved directly. Begin a working branch first.", "immutable_snapshot")
        protected = ("estimate_revisions", "reviews", "submissions", "proposal_artifacts", "proposal_history", "working_branch", "award", "contract_allocations", "change_orders", "sov_lines", "closeout", "audit_events", "configuration_lineage")
        for key in protected:
            incoming[key] = deepcopy(current.get(key))
        incoming["project"]["configuration_id"] = current["project"]["configuration_id"]
        incoming["project"]["bid_version"] = deepcopy(current["project"].get("bid_version"))
        incoming["schema_version"] = current.get("schema_version", SCHEMA_VERSION)
        incoming["interchange_version"] = current.get("interchange_version", INTERCHANGE_VERSION)
        preserve_quote_square_feet_intent(incoming, current)
        refresh_labor_rate_selection(incoming, current)
        incoming_ids = {row.get("id") for row in incoming.get("cost_codes", [])}
        for row in current.get("cost_codes", []):
            if row.get("id") not in incoming_ids:
                report = cost_code_dependencies(current, row["id"])
                if report["has_dependencies"]:
                    raise DomainError(
                        "Cost Code has dependent detail. Use the dependency preview and confirmed cascade command.",
                        "cost_code_dependencies",
                        [report],
                    )
        validate_project_inputs(incoming, current, config)
        prior_digest = {"name": current["project"].get("name"), "working_total": current.get("working_estimate", {}).get("totals", {}).get("selling_value")}
        changes = payload.get("changes") or []
        if len(changes) > 10000:
            raise DomainError("A single save cannot record more than 10,000 datapoint changes.")
        apply_manual_quote_selection_changes(incoming, changes)
        preserve_quote_selection_across_group_changes(incoming, current)
        if changes and incoming.get("working_branch"):
            incoming["working_branch"]["has_unpublished_changes"] = True
        apply_line_acknowledgement_metadata(incoming, changes, actor)
        calculate_project(incoming, config)
        count = len(changes) or max(1, int(payload.get("data_point_changes", 1)))
        bump_bid_version(incoming, "data_point_change", amount=count)
        correlation = payload.get("correlation_id") or uid("cor")
        if changes:
            for change in changes:
                path = str(change.get("path", "unknown"))[:500]
                prior_value = {"path": path, "value": change.get("prior")}
                new_value = {"path": path, "value": change.get("new")}
                rate_context = rate_override_audit_context(incoming, config, path)
                if rate_context is not None:
                    new_value["rate_context"] = rate_context
                entity_type, entity_id, operation = datapoint_audit_identity(incoming, path, project_id)
                audit(incoming, actor, role, entity_type, entity_id, operation,
                      prior_value, new_value,
                      str(change.get("reason") or "Datapoint modified")[:1000], correlation)
        else:
            audit(incoming, actor, role, "project", project_id, "edit_save", prior_digest,
                  {"name": incoming["project"].get("name"), "working_total": incoming["working_estimate"]["totals"].get("selling_value"), "data_point_changes": count},
                  payload.get("reason", "Project inputs changed"), correlation)
        saved = store.save_project(incoming, expected)
        index_reusable_history(saved, current)
        refresh_historical_index(saved)
        return {"project": redact(saved, role), "saved_at": saved["project"]["updated_at"]}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/cost-codes/custom")
def create_custom_cost_code(project_id: str, command: CustomCostCodeCommand,
                            actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        if not verify_custom_code_credentials(
            command.username,
            command.password.get_secret_value(),
            secret_file=custom_code_secret_path(),
        ):
            raise DomainError(
                "The dedicated Add Custom Code credential was not accepted.",
                "custom_code_authorization_failed",
            )
        doc, config = load(project_id)
        expected = command.expected_revision
        _, requested_base = split_variant(command.code)
        normalized = normalize_code(requested_base)
        if not normalized:
            raise DomainError("Custom Cost Code cannot be blank.", "invalid_cost_code")
        existing = {
            normalize_code(split_variant(row.get("code", ""))[1])
            for row in doc.get("cost_codes", [])
        }
        controlled = {
            normalize_code(row.get("normalized_code") or row.get("display_code") or "")
            for row in config.get("csi_references", [])
        }
        if normalized in existing:
            raise DomainError("That Cost Code is already present in this project.", "duplicate_cost_code")
        if normalized in controlled:
            raise DomainError("That is a controlled Cost Code; select it from the reference search instead.", "controlled_cost_code_exists")
        record_data = command.model_dump(exclude={"password", "username", "expected_revision"})
        record = new_custom_cost_code(record_data, actor)
        doc.setdefault("cost_codes", []).append(record)
        calculate_project(doc, config)
        bump_bid_version(doc, "custom_cost_code_created")
        correlation = uid("cor")
        audit(
            doc, actor, role, "cost_code", record["id"], "custom_cost_code_created",
            None,
            {"id": record["id"], "code": record["code"], "description": record["description"], "custom_status": record["custom_status"]},
            command.reason,
            correlation,
        )
        saved = store.save_project(doc, expected)
        return {"project": redact(saved, role), "cost_code": record, "correlation_id": correlation}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/cost-codes/{cost_code_id}/remove")
def remove_cost_code(project_id: str, cost_code_id: str, command: RemoveCostCodeCommand,
                     actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        doc, config = load(project_id)
        report = cost_code_dependencies(doc, cost_code_id)
        if report["has_dependencies"] and not command.confirm_cascade:
            return {
                "project": redact(doc, role),
                "removed": False,
                "requires_confirmation": True,
                "dependency_report": report,
            }
        report = remove_cost_code_cascade(doc, cost_code_id)
        calculate_project(doc, config)
        bump_bid_version(doc, "cost_code_cascade_removed")
        correlation = uid("cor")
        audit(
            doc, actor, role, "cost_code", cost_code_id, "cost_code_cascade_removed",
            {"code": report["code"], "dependencies": report["dependencies"]},
            {"removed_cost_code_id": cost_code_id, "removed_record_ids": report["removed_record_ids"]},
            command.reason,
            correlation,
        )
        saved = store.save_project(doc, command.expected_revision)
        return {
            "project": redact(saved, role),
            "removed": True,
            "requires_confirmation": False,
            "dependency_report": report,
            "correlation_id": correlation,
        }
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/bid-source-edit")
def update_bid_source(project_id: str, command: BidSourceEditCommand,
                      actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, config = load(project_id)
        prior = deepcopy(doc)
        payload = command.model_dump(exclude={"expected_revision"})
        source = edit_bid_source(doc, config, actor, role, payload)
        saved = store.save_project(doc, command.expected_revision)
        index_reusable_history(saved, prior)
        return {"project": redact(saved, role), "source": source}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/mileage")
def calculate_project_mileage(project_id: str, payload: dict = Body(default={}), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        doc, _ = load(project_id)
        expected = int(payload.get("expected_revision", doc["project"].get("revision", 0)))
        address = str(payload.get("address") or doc["project"].get("address") or "").strip()
        zip_code = str(payload.get("zip") or doc["project"].get("zip") or "").strip()
        query = address if not zip_code or zip_code in address else f"{address}, {zip_code}"
        prior_result = doc["project"].get("mileage_calculation")
        if prior_result and prior_result.get("input_address", "").lower() == query.lower() and not payload.get("force"):
            return {"project": redact(doc, role), "mileage": prior_result, "cached": True}
        latest_config = store.load_configuration(CONFIG_VERSION)
        settings = latest_config.get("application_settings", {}).get("mileage", {})
        match = doc["project"].get("address_match_metadata") or {}
        selected_destination = None
        if (
            str(match.get("label") or "").strip().casefold() == address.casefold()
            and match.get("latitude") is not None and match.get("longitude") is not None
        ):
            selected_destination = {
                "matched_address": address,
                "latitude": str(match["latitude"]), "longitude": str(match["longitude"]),
                "provider": str(match.get("provider") or "selected address provider"),
                "attribution": match.get("attribution"),
            }
        result = (
            calculate_driving_mileage(query, settings, destination=selected_destination)
            if selected_destination else calculate_driving_mileage(query, settings)
        )
        prior = {"miles_from_rogers": doc["project"].get("miles_from_rogers"), "mileage_calculation": prior_result}
        doc["project"]["miles_from_rogers"] = result["miles"]
        doc["project"]["mileage_calculation"] = {**result, "settings_configuration_id": latest_config["id"]}
        bump_bid_version(doc, "mileage_calculated")
        audit(doc, actor, role, "project_datapoint", project_id, "mileage_calculated", prior,
              {"miles_from_rogers": result["miles"], "mileage_calculation": doc["project"]["mileage_calculation"]},
              "Driving mileage calculated from job address to configured Rogers origin")
        saved = store.save_project(doc, expected)
        return {"project": redact(saved, role), "mileage": result, "cached": False}
    except MileageError as exc:
        fail(DomainError(str(exc), "mileage_lookup_failed"))
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/duplicate")
def duplicate(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        source, config = load(project_id)
        doc = duplicate_project(source, payload.get("name") or f"{source['project']['name']} Copy", actor, role)
        calculate_project(doc, config)
        saved = store.save_project(doc, -1)
        index_reusable_history(saved)
        refresh_historical_index(saved)
        return {"project": redact(saved, role)}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/archive")
def archive(project_id: str, payload: dict = Body(default={}), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "archive")
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        prior = doc["project"].get("archived", False)
        doc["project"]["archived"] = bool(payload.get("archived", True))
        bump_bid_version(doc, "archive_change")
        audit(doc, actor, role, "project", project_id, "archive" if doc["project"]["archived"] else "unarchive", prior, doc["project"]["archived"], payload.get("reason", "Archive Project"))
        return {"project": redact(store.save_project(doc, expected), role)}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/import")
def import_project(payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        doc = payload.get("project_document")
        if not isinstance(doc, dict) or "project" not in doc:
            raise DomainError("Import must be a versioned Murphy Window project JSON document.")
        try:
            doc = migrate_project_document(doc)
        except MigrationError as exc:
            raise DomainError(str(exc), "unsupported_schema_version") from exc
        doc = strip_ui_working_rows(doc)
        if payload.get("as_duplicate", True):
            doc = duplicate_project(doc, payload.get("name") or f"{doc['project'].get('name', 'Imported')} Import", actor, role)
        config = store.load_configuration(doc["project"].get("configuration_id", CONFIG_VERSION))
        calculate_project(doc, config)
        audit(doc, actor, role, "project", doc["project"]["id"], "import", None, {"source": payload.get("source", "JSON upload")}, "Project JSON import")
        saved = store.save_project(doc, -1)
        index_reusable_history(saved)
        refresh_historical_index(saved)
        return {"project": redact(saved, role)}
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/export")
def export_project(project_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> Response:
    actor, role = actor_role
    try:
        require(role, "export")
        doc, _ = load(project_id)
        content = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        return Response(content, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{project_id}.json"'})
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/job-data")
def export_job_data(project_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "export")
        doc, _ = load(project_id)
        return job_data(redact(doc, role))
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/backup")
def backup(project_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        path = store.manual_backup(project_id)
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        bump_bid_version(doc, "manual_backup")
        audit(doc, actor, role, "project", project_id, "backup", None, {"backup": path.name}, "Manual backup")
        store.save_project(doc, expected)
        return {"backup": path.name}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/recover")
def recover(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        recovered = store.restore_backup(project_id, payload["backup"])
        expected = recovered["project"]["revision"]
        bump_bid_version(recovered, "recovery")
        audit(recovered, actor, role, "project", project_id, "recover", None, {"backup": payload["backup"]}, payload.get("reason", "Recover valid backup"))
        recovered = store.save_project(recovered, expected)
        refresh_historical_index(recovered)
        return {"project": redact(recovered, role)}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/reviews")
def add_review(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "review")
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        review = {"id": uid("revw"), "revision_id": payload.get("revision_id"), "reviewer": actor, "reviewer_role": role, "decision": payload.get("decision", "reviewed"), "comment": payload.get("comment", ""), "timestamp": now(), "evidence_status": "pending_policy"}
        doc["reviews"].append(review)
        bump_bid_version(doc, "review_recorded")
        audit(doc, actor, role, "review", review["id"], "review", None, review, payload.get("comment", "Bid review"))
        return {"project": redact(store.save_project(doc, expected), role), "review": review}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/submit")
def submit_project(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, config = load(project_id)
        expected = doc["project"]["revision"]
        result = submit(doc, config, actor, role, payload)
        saved = store.save_project(doc, expected)
        refresh_historical_index(saved)
        return {"project": redact(saved, role), "submission": result}
    except Exception as exc:
        fail(exc)


def _proposal_index(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in sorted(document.get("proposal_history", []), key=lambda row: int(row.get("sequence", 0)), reverse=True)]


def _render_bid_review_pdf(document: dict[str, Any], configuration: dict[str, Any], alternate_id: str | None = None) -> bytes:
    """Render a dense, single-sheet estimator review of the effective bid state."""
    calculate_project(document, configuration)
    alternate = next((row for row in document.get("alternates", []) if str(row.get("id")) == str(alternate_id)), None)
    if alternate_id and not alternate:
        raise DomainError("The requested Alternate does not exist.", "not_found")
    estimate = alternate.get("calculated", {}).get("effective_estimate", {}) if alternate else document.get("working_estimate", {})
    frame_sections = alternate.get("calculated", {}).get("effective_takeoff_sections", []) if alternate else document.get("takeoff_sections", [])
    totals, project = estimate.get("totals", {}), document.get("project", {})

    def plain(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        return str(value).replace("\u2014", "-").replace("\u2013", "-").replace("\u2011", "-")

    def currency(value: Any) -> str:
        try:
            return f"${float(value or 0):,.2f}"
        except (TypeError, ValueError):
            return plain(value)

    def numeric(value: Any, digits: int = 2) -> str:
        if value in (None, ""):
            return ""
        try:
            return f"{float(value):,.{digits}f}"
        except (TypeError, ValueError):
            return plain(value)

    def percentage(value: Any) -> str:
        try:
            return f"{float(value or 0) * 100:,.2f}%"
        except (TypeError, ValueError):
            return plain(value)

    def markup_percentage(row: dict[str, Any]) -> str:
        direct = float(row.get("direct_cost", row.get("cost", 0)) or 0)
        selling = float(row.get("selling_value", row.get("value", 0)) or 0)
        return percentage((selling - direct) / direct) if direct else ""

    frame_count = sum(len(section.get("lines", [])) for section in frame_sections)
    material_count = sum(len(section.get("material_results", [])) for section in frame_sections)
    line_count = len(estimate.get("lines", []))
    input_count = sum(len(document.get(key, [])) for key in ("cost_codes", "quotes", "doors", "equipment", "borrowed_lites", "labor_estimates", "travel_estimates"))
    estimated_rows = 34 + frame_count + material_count + line_count + input_count + len(estimate.get("cost_code_summaries", [])) + len(estimate.get("validation", []))
    if estimated_rows < 120:
        sheet_inches = 4 + estimated_rows * .11
    elif estimated_rows < 700:
        sheet_inches = 6 + estimated_rows * .16
    else:
        sheet_inches = 8 + estimated_rows * .18
    page_height = max(11 * inch, min(190 * inch, sheet_inches * inch))
    page_width = max(36 * inch, min(198 * inch, page_height * 1.25))
    pagesize = (page_width, page_height)
    stream = io.BytesIO()
    pdf = SimpleDocTemplate(stream, pagesize=pagesize, leftMargin=.35 * inch, rightMargin=.35 * inch,
                            topMargin=.35 * inch, bottomMargin=.35 * inch,
                            title=f"Bid Review - {project.get('name', '')}", author="Murphy Window")
    usable = page_width - pdf.leftMargin - pdf.rightMargin
    dark, accent, muted, rule, wash = (colors.HexColor(value) for value in ("#1F3430", "#2D6756", "#66736F", "#BCC8C4", "#EEF3F1"))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("BidReviewTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=19, textColor=dark, alignment=0)
    meta_style = ParagraphStyle("BidReviewMeta", parent=styles["BodyText"], fontName="Helvetica", fontSize=6.2, leading=7.4, textColor=muted)
    body_style = ParagraphStyle("BidReviewBody", parent=meta_style, textColor=dark)
    body_right = ParagraphStyle("BidReviewBodyRight", parent=body_style, alignment=2)
    header_style = ParagraphStyle("BidReviewHeader", parent=body_style, fontName="Helvetica-Bold", fontSize=6, leading=7, textColor=colors.white)
    section_style = ParagraphStyle("BidReviewSection", parent=body_style, fontName="Helvetica-Bold", fontSize=8, leading=9, textColor=accent, spaceBefore=3, spaceAfter=2)

    def paragraph(value: Any, style: ParagraphStyle = body_style) -> Paragraph:
        return Paragraph(escape(plain(value)).replace("\n", "<br/>"), style)

    def table(title: str, headings: list[str], rows: list[list[Any]], widths: list[float] | None = None) -> list[Any]:
        if not rows:
            return []
        normalized = [[paragraph(value, header_style) for value in headings]] + [
            [paragraph(value, body_right if index >= max(2, len(headings) - 5) else body_style) for index, value in enumerate(row)]
            for row in rows
        ]
        column_widths = [usable * value for value in widths] if widths else [usable / len(headings)] * len(headings)
        grid = Table(normalized, colWidths=column_widths, repeatRows=1, hAlign="LEFT")
        grid.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), accent), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), .25, rule), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.2), ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, wash]),
        ]))
        return [paragraph(title, section_style), grid, Spacer(1, 3)]

    story: list[Any] = []
    scenario = alternate_label(alternate) if alternate else "Base"
    story.append(Table([
        [paragraph("MURPHY WINDOW - BID REVIEW", title_style), paragraph(f"{scenario}\nGenerated {now()}\nBid version {project.get('bid_version', {}).get('display', '')}", meta_style)],
        [paragraph(f"{project.get('name', '')} | {project.get('project_number', '')} | {project.get('address', '')}", body_style),
         paragraph(f"Configuration {configuration.get('id', '')} v{configuration.get('version', '')}", meta_style)],
    ], colWidths=[usable * .72, usable * .28], style=TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, -1), (-1, -1), .8, accent), ("BOTTOMPADDING", (0, -1), (-1, -1), 5)])))
    story.extend(table("Commercial Summary", ["Direct Cost", "Markup", "Selling Value", "Margin", "Total ft2", "$/ft2", "Tax", "Contingency", "Bond"], [[
        currency(totals.get("direct_cost")), currency(totals.get("markup_profit")), currency(totals.get("selling_value")),
        percentage(totals.get("margin_percentage")), numeric(totals.get("square_feet")), currency(totals.get("price_per_square_foot")),
        currency(totals.get("tax")), currency(totals.get("contingency")), currency(totals.get("bond")),
    ]], [.12, .11, .13, .09, .10, .10, .11, .12, .12]))
    markup = estimate.get("markup_overrides", {})
    settings = configuration.get("application_settings", {})
    story.extend(table("Effective Pricing Configuration", ["Configuration", "Base Product", "Installation Material", "Labor", "Tax Rate", "Tax Status", "Contingency", "Bond", "Wage", "Precision"], [[
        f"{configuration.get('id', '')} / v{configuration.get('version', '')}", percentage(markup.get("base_product")),
        percentage(markup.get("installation_material", markup.get("base_product"))), percentage(markup.get("labor", markup.get("LAF"))),
        percentage(estimate.get("tax_rate")), project.get("tax_status", ""), plain(estimate.get("contingency_override") if estimate.get("contingency_override") is not None else estimate.get("contingency_enabled")),
        plain(estimate.get("bond_override") if estimate.get("bond_override") is not None else estimate.get("bond_enabled")), project.get("wage_type", ""),
        json.dumps(settings.get("decimal_precision", {}), sort_keys=True, separators=(",", ":")),
    ]], [.12, .09, .11, .08, .08, .09, .10, .09, .08, .16]))

    if alternate:
        calculated = alternate.get("calculated", {})
        story.extend(table("Alternate Delta", ["Alternate", "Classification", "Direct Cost Delta", "Selling Value Delta", "Scope of Change"], [[
            alternate_label(alternate), calculated.get("classification", ""), currency(calculated.get("direct_cost_delta")), currency(calculated.get("selling_value_delta")),
            "; ".join(f"{group.get('area', '')}: {', '.join(group.get('changes', []))}" for group in calculated.get("scope_of_change", [])),
        ]], [.11, .10, .13, .13, .53]))

    summaries = estimate.get("cost_code_summaries", [])
    story.extend(table("Cost Code Summary", ["Code", "Description", "Direct Cost", "Markup %", "Markup $", "Selling Value", "ft2", "$/ft2"], [[
        row.get("code", ""), row.get("description", ""), currency(row.get("direct_cost", row.get("cost"))),
        markup_percentage(row),
        currency(float(row.get("selling_value", row.get("value", 0)) or 0) - float(row.get("direct_cost", row.get("cost", 0)) or 0)),
        currency(row.get("selling_value", row.get("value"))), numeric(row.get("total_square_feet", row.get("square_feet"))), currency(row.get("dollars_per_square_foot")),
    ] for row in summaries if any((row.get("direct_cost", row.get("cost")), row.get("selling_value", row.get("value")), row.get("total_square_feet", row.get("square_feet"))))], [.10, .28, .11, .09, .10, .12, .09, .11]))

    story.extend(table("Bid Source Lineage", ["Code", "Actual Code", "Category", "Description", "Source", "Direct Cost", "Markup %", "Selling Value"], [[
        row.get("code", ""), row.get("actual_cost_code", ""), row.get("category", ""), row.get("description", ""),
        row.get("source_key", row.get("id", "")), currency(row.get("direct_cost")), percentage(row.get("markup_rate")), currency(row.get("selling_value")),
    ] for row in estimate.get("lines", [])], [.08, .08, .10, .28, .17, .10, .09, .10]))

    story.extend(table("Scope and Cost Codes", ["Code", "Description", "Actual / MWD Code", "MWD Description", "Deduct", "Status"], [[
        row.get("code", ""), row.get("description", ""), row.get("mwd_code", ""), row.get("mwd_description", ""), plain(row.get("deduct")), row.get("status", ""),
    ] for row in document.get("cost_codes", [])], [.13, .30, .14, .27, .07, .09]))
    story.extend(table("Quotes", ["Code", "Vendor", "Date", "Price", "ft2", "Credit", "Surcharge", "Tax Included", "Used", "Notes"], [[
        row.get("code", ""), row.get("vendor", ""), row.get("date", ""), currency(row.get("price")), numeric(row.get("square_feet")),
        f"{row.get('credit_type', '')} {numeric(row.get('credit_value'))}", f"{row.get('surcharge_type', '')} {numeric(row.get('surcharge_value'))}",
        plain(row.get("tax_included")), plain(row.get("used")), row.get("notes", ""),
    ] for row in document.get("quotes", [])], [.08, .13, .08, .09, .07, .10, .10, .09, .07, .19]))

    frame_rows, material_rows = [], []
    for section in frame_sections:
        for row in section.get("lines", []):
            calculated = row.get("calculated", {})
            frame_rows.append([section.get("code", ""), row.get("mark", ""), numeric(row.get("quantity")), numeric(row.get("width_inches")), numeric(row.get("height_inches")),
                               numeric(calculated.get("square_feet")), numeric(calculated.get("perimeter_lf")), numeric(row.get("caulking_passes")), numeric(calculated.get("caulking_lf")),
                               row.get("head", ""), row.get("sill", ""), row.get("jamb", ""), row.get("type", ""), row.get("material", ""), row.get("finish", ""), row.get("notes", "")])
        overrides = section.get("material_overrides", {})
        for result in section.get("material_results", []):
            override = overrides.get(str(result.get("material_rule_id")), overrides.get(result.get("material_rule_id"), {}))
            material_rows.append([section.get("code", ""), result.get("name", ""), result.get("source", ""), result.get("operator", ""), numeric(result.get("operand")),
                                  numeric(result.get("calculated_quantity")), result.get("unit", ""), currency(result.get("effective_rate")), currency(result.get("pre_tax_cost")),
                                  "Yes" if override else "No"])
    story.extend(table("Frame Takeoff", ["Code", "Mark", "Qty", "Width", "Height", "ft2", "Perim.", "Passes", "Caulk LF", "Head", "Sill", "Jamb", "Type", "Material", "Finish", "Notes"], frame_rows,
                       [.055, .045, .04, .045, .045, .045, .05, .045, .05, .07, .06, .07, .07, .09, .075, .105]))
    story.extend(table("Frame Installation Materials", ["Code", "Material", "Basis", "Operator", "Factor", "Quantity", "Unit", "Unit Rate", "Extended Cost", "Override"], material_rows,
                       [.08, .20, .10, .07, .07, .09, .08, .10, .12, .09]))

    record_specs = [
        ("Doors and Hardware", "doors", ["code", "door_number", "description", "leaf_quantity", "width", "height", "hardware_set", "notes"]),
        ("Equipment", "equipment", ["code", "description", "quantity", "duration", "duration_unit", "delivery_direction", "rate", "delivery", "notes"]),
        ("Borrowed Lites", "borrowed_lites", ["code", "mark", "description", "quantity", "width_inches", "height_inches", "rate", "notes"]),
        ("Labor", "labor_estimates", ["code", "labor_type", "description", "man_hours", "crew_size", "rate_override", "override_reason", "notes"]),
        ("Travel", "travel_estimates", ["code", "description", "enabled", "quantity", "rate", "notes"]),
    ]
    for section_title, key, fields in record_specs:
        story.extend(table(section_title, [field.replace("_", " ").title() for field in fields], [[plain(row.get(field)) for field in fields] for row in document.get(key, [])]))
    story.extend(table("Validation", ["Severity", "Code", "Entity", "Message", "Acknowledged"], [[
        "Blocking" if row.get("blocking") else "Advisory", row.get("code", ""), f"{row.get('entity_type', '')} {row.get('entity_id', '')}", row.get("message", ""), plain(row.get("acknowledged")),
    ] for row in estimate.get("validation", [])], [.08, .12, .18, .54, .08]))

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(rule)
        canvas.line(pdf.leftMargin, .22 * inch, page_width - pdf.rightMargin, .22 * inch)
        canvas.setFont("Helvetica", 5.5)
        canvas.setFillColor(muted)
        canvas.drawString(pdf.leftMargin, .10 * inch, f"{project.get('project_number', '')} | {scenario} | Configuration {configuration.get('id', '')}")
        canvas.drawRightString(page_width - pdf.rightMargin, .10 * inch, f"Single-sheet estimator review | Page {doc.page}")
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


def _render_frozen_proposal_pdf(artifact: dict[str, Any]) -> bytes:
    """Render once from the frozen artifact body; committed bytes are authoritative."""
    stream = io.BytesIO()
    dark, accent, rule, wash = (colors.HexColor(value) for value in ("#333333", "#2D6756", "#B9C2BF", "#F3F5F4"))

    def clean(value: Any) -> str:
        return escape(str(value or "").replace("\u2014", "-").replace("\u2013", "-").replace("\u2011", "-"))

    def para(value: Any, style: ParagraphStyle) -> Paragraph:
        return Paragraph(clean(value).replace("\n", "<br/>"), style)

    styles = getSampleStyleSheet()
    body = ParagraphStyle("ProposalBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12,
                          textColor=colors.HexColor("#202624"), spaceAfter=3)
    small = ParagraphStyle("ProposalSmall", parent=body, fontSize=7.4, leading=9, textColor=colors.HexColor("#5C6461"))
    label = ParagraphStyle("ProposalLabel", parent=small, fontName="Helvetica-Bold", fontSize=7, leading=8,
                           textColor=colors.HexColor("#454B49"), uppercase=True)
    section_text = ParagraphStyle("ProposalSectionText", parent=body, fontName="Helvetica-Bold", fontSize=9,
                                  leading=11, textColor=colors.white, alignment=1)
    document_title = ParagraphStyle("ProposalDocumentTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                                    fontSize=22, leading=24, textColor=dark, alignment=2)
    brand_mark = ParagraphStyle("ProposalBrandMark", parent=body, fontName="Helvetica-Bold", fontSize=25,
                                leading=26, textColor=dark)
    brand_sub = ParagraphStyle("ProposalBrandSub", parent=small, fontName="Helvetica-Bold", fontSize=7.2,
                               leading=8, textColor=dark)
    amount_words = ParagraphStyle("ProposalAmountWords", parent=body, fontName="Helvetica-Bold", fontSize=9.2,
                                  leading=12, textColor=dark)
    alt_heading = ParagraphStyle("ProposalAlternateHeading", parent=body, fontName="Helvetica-Bold", fontSize=9.3,
                                 leading=11, textColor=accent)

    pdf = SimpleDocTemplate(stream, pagesize=LETTER, leftMargin=.58*inch, rightMargin=.58*inch,
                            topMargin=.48*inch, bottomMargin=.58*inch,
                            title=f"Proposal - {artifact.get('project_name') or ''}", author="Murphy Window & Door Commercial")
    width = LETTER[0] - pdf.leftMargin - pdf.rightMargin

    def section_bar(title: str) -> Table:
        table = Table([[para(title, section_text)]], colWidths=[width], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), dark), ("BOX", (0, 0), (-1, -1), .65, dark),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return table

    def grid(rows: list[list[Any]], widths: list[float], *, labels: tuple[int, ...] = ()) -> Table:
        converted = [[cell if isinstance(cell, Paragraph) else para(cell, label if column in labels else body)
                      for column, cell in enumerate(row)] for row in rows]
        table = Table(converted, colWidths=widths, hAlign="LEFT")
        commands = [("GRID", (0, 0), (-1, -1), .5, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        for column in labels:
            commands.append(("BACKGROUND", (column, 0), (column, -1), wash))
        table.setStyle(TableStyle(commands))
        return table

    generated = str(artifact.get("generated_at") or "")[:10] or "Current preview"
    identity = Table([
        [[Paragraph("MWD", brand_mark), Paragraph("MURPHY WINDOW &amp; DOOR", brand_sub)],
         para("Commercial", ParagraphStyle("ProposalDivision", parent=small, fontSize=8, textColor=accent)),
         para("PROPOSAL", document_title)],
    ], colWidths=[2.2*inch, 1.35*inch, width-3.55*inch], hAlign="LEFT")
    identity.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                                  ("LINEBELOW", (0, 0), (-1, -1), 1.2, dark), ("BOTTOMPADDING", (0, 0), (-1, -1), 14)]))
    company = grid([
        ["COMPANY", "Murphy Window & Door Commercial", "DATE", generated],
        ["ADDRESS", "12536 314th Ave NW, Princeton, MN 55371", "VALIDITY", "30 days from proposal date"],
        ["CONTACT", "estimating@murphywindow.com", "PROPOSAL", f"{artifact.get('proposal_number') or 'PREVIEW'} - {artifact.get('proposal_name') or 'Current Working Bid'}"],
        ["ESTIMATOR", artifact.get("estimator") or artifact.get("generated_by") or "Estimating Department", "PROJECT NO.", artifact.get("project_number") or "Not assigned"],
    ], [.75*inch, 3.18*inch, .72*inch, width-4.65*inch], labels=(0, 2))
    project = grid([
        ["ATTENTION", artifact.get("attention") or "Estimating Department", "PROJECT ADDRESS", artifact.get("project_address") or "Not provided"],
        ["COMPANY", artifact.get("attention_company") or artifact.get("general_contractor") or artifact.get("owner_name") or "Not provided",
         "PROJECT NAME", artifact.get("project_name") or "Untitled project"],
    ], [.78*inch, 2.42*inch, 1.12*inch, width-4.32*inch], labels=(0, 2))
    story: list[Any] = [identity, Spacer(1, 6), company, Spacer(1, 7), section_bar("Project Information"), project]

    scope_codes = artifact.get("scope_codes") or []
    if scope_codes:
        cells = [Paragraph(f"<b>{clean(row.get('code'))}</b>  {clean(row.get('description'))}", body) for row in scope_codes]
        pairs = [cells[index:index + 2] for index in range(0, len(cells), 2)]
        if len(pairs[-1]) == 1:
            pairs[-1].append("")
        scope_table = Table(pairs, colWidths=[width / 2, width / 2])
        scope_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .5, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                         ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.extend([Spacer(1, 7), section_bar("Scope of Work"), scope_table])

    proposal_sections = [("Scope", "scope"), ("Inclusions", "inclusions"), ("Exclusions", "exclusions"),
                         ("Additional Information", "additional_information")]
    for title, key in proposal_sections:
        value = artifact.get(key)
        if value:
            story.extend([Spacer(1, 5), section_bar(title), grid([[value]], [width])])

    statement = ("Murphy Window & Door Commercial proposes to complete the scope of work stated above for the sum of "
                 f"{str(artifact.get('written_amount') or '').upper()} (${float(artifact.get('amount') or 0):,.2f}).")
    story.extend([Spacer(1, 7), section_bar("Company Proposal"), grid([[para(statement, amount_words)]], [width])])

    alternates = artifact.get("alternates") or []
    if alternates:
        alt_rows = []
        for alternate in alternates:
            delta = float(alternate.get("selling_value_delta") or 0)
            classification = "ADD" if delta > 0 else "DEDUCT" if delta < 0 else "NO CHANGE"
            title = alternate.get("label") or alternate_label(alternate)
            descriptions = []
            if alternate.get("customer_description"):
                descriptions.append(str(alternate["customer_description"]))
            for group in alternate.get("scope_of_change", []):
                descriptions.append(f"{group.get('area')}: " + "; ".join(group.get("changes", [])))
            alt_rows.append([para(title, alt_heading), Paragraph("<br/>".join(clean(item) for item in descriptions) or "No scope difference.", small),
                             Paragraph(f"{clean(classification)}<br/><b>${abs(delta):,.2f}</b>", ParagraphStyle("ProposalAltAmount", parent=body, alignment=2))])
        alt_table = Table([[para("Alternates", section_text), "", ""], *alt_rows],
                          colWidths=[1.72*inch, width-3.05*inch, 1.33*inch], repeatRows=1)
        alt_table.setStyle(TableStyle([("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), dark),
                                       ("GRID", (0, 0), (-1, -1), .5, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                       ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                                       ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, 0), (-1, 0), 4)]))
        story.extend([Spacer(1, 7), alt_table])

    story.extend([
        Spacer(1, 7), section_bar("General Contractor Acceptance"),
        grid([["As an authorized representative of the recipient contractor, I accept this proposal at the amount specified, without alteration."]], [width]),
        Spacer(1, 10),
        Table([[para("Signature:", small), "", para("Date:", small), ""],
               ["", "", "", ""]], colWidths=[.82*inch, 2.55*inch, .48*inch, width-3.85*inch],
              style=TableStyle([("LINEBELOW", (1, 0), (1, 0), .75, dark), ("LINEBELOW", (3, 0), (3, 0), .75, dark),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])),
    ])

    trace = f"{artifact.get('proposal_number') or 'PREVIEW'} | Artifact {artifact.get('id') or 'current-working-preview'} | Snapshot {artifact.get('snapshot_fingerprint') or 'NOT CREATED'}"
    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(rule)
        canvas.line(pdf.leftMargin, .38*inch, LETTER[0] - pdf.rightMargin, .38*inch)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#68706D"))
        canvas.drawString(pdf.leftMargin, .22*inch, clean(trace).replace("&amp;", "&")[:120])
        canvas.drawRightString(LETTER[0] - pdf.rightMargin, .22*inch, f"Page {document.page}")
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


@app.get("/api/projects/{project_id}/proposals")
def list_proposals(project_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    try:
        document, _ = store.load_project(project_id)
        return {"proposals": _proposal_index(document), "working_branch": deepcopy(document.get("working_branch"))}
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/proposal-preview.pdf")
def preview_working_proposal(project_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> Response:
    """Render the current calculated state without creating history or committing an artifact."""
    try:
        document, configuration = load(project_id)
        calculate_project(document, configuration)
        project, totals = document.get("project", {}), document.get("working_estimate", {}).get("totals", {})
        amount = totals.get("selling_value") or 0
        artifact = {
            "id": "current-working-preview", "proposal_number": "PREVIEW", "proposal_name": "Current Working Bid",
            "generated_at": now(), "generated_by": actor_role[0],
            "project_name": project.get("name"), "project_number": project.get("project_number"),
            "project_address": project.get("address"), "owner_name": project.get("owner_name"),
            "general_contractor": project.get("general_contractor", ""), "estimator": project.get("estimator", ""),
            "attention": next((row.get("name") for row in document.get("contacts", []) if row.get("active", True)), ""),
            "attention_company": next((row.get("organization") for row in document.get("contacts", []) if row.get("active", True)), ""),
            "scope_codes": [{"code": row.get("code", ""), "description": row.get("description", "")}
                            for row in document.get("cost_codes", []) if row.get("code")],
            "amount": amount, "written_amount": dollars_in_words(amount), "scope": project.get("proposal_scope", ""),
            "inclusions": project.get("proposal_inclusions", ""), "exclusions": project.get("proposal_exclusions", ""),
            "additional_information": project.get("additional_information", ""), "snapshot_fingerprint": "NOT CREATED",
            "alternates": [{"key": row.get("key"), "sequence": row.get("sequence"), "name": row.get("name"),
                            "label": alternate_label(row), "customer_description": row.get("customer_description"),
                            "scope_of_change": row.get("calculated", {}).get("scope_of_change", []),
                            "classification": row.get("calculated", {}).get("classification"),
                            "selling_value_delta": row.get("calculated", {}).get("selling_value_delta")}
                           for row in document.get("alternates", [])],
        }
        return Response(_render_frozen_proposal_pdf(artifact), media_type="application/pdf", headers={
            "Content-Disposition": 'inline; filename="proposal-current-working-preview.pdf"',
            "X-Proposal-Preview": "current-working", "Cache-Control": "no-store",
        })
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/bid-review.pdf")
def bid_review_pdf(project_id: str, alternate_id: str | None = None, download: bool = False,
                   actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> Response:
    """Export the current Base or Alternate as one dense estimator-review sheet."""
    try:
        document, configuration = load(project_id)
        content = _render_bid_review_pdf(deepcopy(document), configuration, alternate_id)
        scenario = "base" if not alternate_id else f"alternate-{alternate_id}"
        disposition = "attachment" if download else "inline"
        return Response(content, media_type="application/pdf", headers={
            "Content-Disposition": f'{disposition}; filename="bid-review-{scenario}.pdf"',
            "Cache-Control": "no-store", "X-Bid-Review": scenario,
        })
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/proposals")
def generate_proposal(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    snapshot = None
    try:
        require(role, "submit")
        document, configuration = load(project_id)
        expected = int(payload.get("expected_revision", document["project"]["revision"]))
        if expected != int(document["project"]["revision"]):
            raise ConflictError(f"Concurrent edit detected: expected revision {expected}, current revision {document['project']['revision']}.")
        snapshot = create_proposal_snapshot(document, configuration, actor, role, payload.get("proposal_name", ""))
        proposal_id = snapshot["metadata"]["id"]
        artifact_id = snapshot["artifact"]["id"]
        artifact_bytes = _render_frozen_proposal_pdf(snapshot["artifact"])
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        snapshot["artifact"]["sha256"] = artifact_hash
        next(item for item in document["proposal_artifacts"] if item["id"] == artifact_id)["sha256"] = artifact_hash
        store.save_proposal_artifact(project_id, artifact_id, artifact_bytes)
        try:
            store.save_proposal_snapshot(project_id, snapshot)
            saved = store.save_project(document, expected, force_snapshot=True)
        except Exception:
            store.discard_unindexed_proposal(project_id, proposal_id)
            store.discard_unindexed_artifact(project_id, artifact_id)
            raise
        refresh_historical_index(saved)
        return {"project": redact(saved, role), "proposal": deepcopy(snapshot["metadata"]), "artifact": deepcopy(snapshot["artifact"])}
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/proposals/{proposal_id}")
def read_proposal(project_id: str, proposal_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    try:
        live, _ = store.load_project(project_id)
        snapshot = store.load_proposal_snapshot(project_id, proposal_id)
        indexed = next((item for item in live.get("proposal_history", []) if item.get("id") == proposal_id), None)
        if not indexed:
            raise DomainError("Proposal was not found in this project.", "not_found")
        # Status/void metadata lives in the index; the frozen commercial payload and
        # originally generated metadata remain append-only in the snapshot file.
        view_snapshot = deepcopy(snapshot)
        view_snapshot["metadata"].update({"status": indexed.get("status"), "void": deepcopy(indexed.get("void"))})
        return {"proposal": deepcopy(view_snapshot["metadata"]), "project": historical_document(view_snapshot, live),
                "configuration": deepcopy(snapshot["state"]["effective_configuration"]), "artifact": deepcopy(snapshot["artifact"])}
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/proposals/{proposal_id}/ancestry")
def proposal_ancestry(project_id: str, proposal_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    try:
        document, _ = store.load_project(project_id)
        index = {item.get("id"): item for item in document.get("proposal_history", [])}
        item = index.get(proposal_id)
        if not item:
            raise DomainError("Proposal was not found.", "not_found")
        return {"proposal": deepcopy(item), "ancestors": [deepcopy(index[item_id]) for item_id in item.get("ancestor_ids", []) if item_id in index]}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/proposals/{proposal_id}/branch")
def begin_proposal_branch(project_id: str, proposal_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        live, _ = store.load_project(project_id)
        expected = int(payload.get("expected_revision", live["project"]["revision"]))
        if expected != int(live["project"]["revision"]):
            raise ConflictError(f"Concurrent edit detected: expected revision {expected}, current revision {live['project']['revision']}.")
        snapshot = store.load_proposal_snapshot(project_id, proposal_id)
        indexed = next((item for item in live.get("proposal_history", []) if item.get("id") == proposal_id), None)
        if not indexed:
            raise DomainError("Proposal was not found in this project.", "not_found")
        snapshot["metadata"]["status"] = indexed.get("status", snapshot["metadata"].get("status"))
        snapshot["metadata"]["void"] = deepcopy(indexed.get("void"))
        correlation = str(payload.get("correlation_id") or uid("cor"))
        result, inherited_configuration = branch_from_snapshot(live, snapshot, payload.get("changes") or [], actor, role, correlation)
        historical_prior = deepcopy(snapshot["state"])
        historical_prior.pop("effective_configuration", None)
        validate_project_inputs(result, historical_prior, inherited_configuration)
        saved = store.save_project(result, expected, force_snapshot=True)
        refresh_historical_index(saved)
        return {"project": redact(saved, role), "working_branch": deepcopy(saved.get("working_branch"))}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/proposals/{proposal_id}/void")
def void_generated_proposal(project_id: str, proposal_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "submit")
        document, _ = store.load_project(project_id)
        expected = int(payload.get("expected_revision", document["project"]["revision"]))
        item = void_proposal(document, proposal_id, actor, role, payload.get("reason", ""))
        saved = store.save_project(document, expected, force_snapshot=True)
        return {"project": redact(saved, role), "proposal": deepcopy(item)}
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/proposals/compare/{left_id}/{right_id}")
def compare_proposals(project_id: str, left_id: str, right_id: str, show_unchanged: bool = False,
                      actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        document, _ = store.load_project(project_id)
        known = {item.get("id") for item in document.get("proposal_history", [])}
        if left_id not in known or right_id not in known:
            raise DomainError("Both proposals must belong to this project.", "not_found")
        left = store.load_proposal_snapshot(project_id, left_id)
        right = store.load_proposal_snapshot(project_id, right_id)
        result = compare_snapshots(left, right, show_unchanged=show_unchanged)
        # Comparison is read-only; follow existing conventions and do not advance
        # the live project revision merely to log a view operation.
        logger.info("proposal comparison project=%s left=%s right=%s actor=%s role=%s", project_id, left_id, right_id, actor, role)
        return {"comparison": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/activate")
def activate_project(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = activate(doc, actor, role, payload)
        saved = store.save_project(doc, expected)
        refresh_historical_index(saved)
        return {"project": redact(saved, role), "award": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/contract/reestimate")
def contract_reestimate(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = reestimate_contract(doc, actor, role, payload)
        return {"project": redact(store.save_project(doc, expected), role), "allocation": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/change-orders")
def change_order(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, config = load(project_id)
        expected = doc["project"]["revision"]
        result = create_change_order(doc, config, actor, role, payload)
        saved = store.save_project(doc, expected)
        return {"project": redact(saved, role), "change_order": redact({"change_orders": [result]}, role)["change_orders"][0]}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/change-orders/{order_id}/status")
def change_order_status(project_id: str, order_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = update_change_order_status(doc, actor, role, order_id, payload)
        saved = store.save_project(doc, expected)
        return {"project": redact(saved, role), "change_order": redact({"change_orders": [result]}, role)["change_orders"][0]}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/sov")
def sov(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = save_sov(doc, actor, role, payload)
        return {"project": redact(store.save_project(doc, expected), role), "sov": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/closeout")
def closeout(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = provisional_closeout(doc, actor, role, payload)
        return {"project": redact(store.save_project(doc, expected), role), "closeout": result}
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/proposal/{artifact_id}.pdf")
def proposal_pdf(project_id: str, artifact_id: str, download: bool = False, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> Response:
    try:
        doc, _ = load(project_id)
        artifact = next((a for a in doc["proposal_artifacts"] if a["id"] == artifact_id), None)
        if not artifact:
            raise DomainError("Proposal artifact not found.")
        committed_path = store.proposal_artifact_path(project_id, artifact_id)
        if committed_path.exists():
            content = committed_path.read_bytes()
            if artifact.get("sha256") and hashlib.sha256(content).hexdigest() != artifact["sha256"]:
                raise PersistenceError("Stored proposal artifact failed its immutable SHA-256 verification.")
            disposition = "attachment" if download else "inline"
            version = artifact.get("proposal_number") or (artifact.get("bid_version") or {}).get("display", "bid").replace(".", "-")
            project_label = artifact.get("project_number") or doc["project"].get("abbreviation") or project_id
            safe_label = "".join(c for c in str(project_label) if c.isalnum() or c in "_-") or "project"
            return Response(content, media_type="application/pdf", headers={
                "Content-Disposition": f'{disposition}; filename="proposal-{safe_label}-{version}.pdf"',
                "X-Proposal-Artifact": artifact["id"], "X-Proposal-Snapshot": str(artifact.get("proposal_id") or ""),
            })
        stream = io.BytesIO()
        pdf = SimpleDocTemplate(stream, pagesize=LETTER, leftMargin=.65*inch, rightMargin=.65*inch, topMargin=.55*inch, bottomMargin=.65*inch,
                                title=f"Proposal - {artifact['project_name']}", author="Murphy Window & Sunroom")
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="Brand", parent=styles["Title"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=18, leading=22, spaceAfter=0))
        styles.add(ParagraphStyle(name="ProposalTitle", parent=styles["Heading1"], textColor=colors.HexColor("#164A3D"), fontName="Helvetica-Bold", fontSize=20, leading=24, spaceBefore=14, spaceAfter=12))
        styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=colors.HexColor("#164A3D"), fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=12, spaceAfter=5))
        styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=colors.HexColor("#293B36")))
        styles.add(ParagraphStyle(name="Amount", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.white, alignment=2))
        styles.add(ParagraphStyle(name="AmountWords", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.white, alignment=2))
        story = []
        brand = Table([[Paragraph("MURPHY WINDOW &amp; SUNROOM", styles["Brand"]), Paragraph("BID PROPOSAL", ParagraphStyle("BrandRight", parent=styles["Brand"], fontSize=10, alignment=2))]], colWidths=[4.5*inch, 2.05*inch])
        brand.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#164A3D")),("BOX",(0,0),(-1,-1),0,colors.HexColor("#164A3D")),("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story += [brand, Paragraph(escape(artifact["project_name"]), styles["ProposalTitle"])]
        info = [
            ["PROJECT NUMBER", artifact.get("project_number") or "Not assigned", "BID VERSION", (artifact.get("bid_version") or {}).get("display", artifact.get("proposal_number", "Not versioned"))],
            ["PROJECT ADDRESS", artifact.get("project_address") or "Not provided", "BID DUE", artifact.get("bid_due_date") or "Not provided"],
            ["OWNER", artifact.get("owner_name") or "Not provided", "ADDENDA", str(artifact.get("addenda", 0))],
        ]
        info_rows = [[Paragraph(f"<b>{escape(str(a))}</b><br/><font color='#66766F'>{escape(str(b))}</font>", styles["BodySmall"]), Paragraph(f"<b>{escape(str(c))}</b><br/><font color='#66766F'>{escape(str(d))}</font>", styles["BodySmall"])] for a,b,c,d in info]
        info_table = Table(info_rows, colWidths=[3.275*inch,3.275*inch])
        info_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F1F5F3")),("INNERGRID",(0,0),(-1,-1),.4,colors.HexColor("#D6E0DC")),("BOX",(0,0),(-1,-1),.6,colors.HexColor("#CAD7D2")),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [info_table, Spacer(1, 12)]
        amount_table = Table([[Paragraph("BASE BID", ParagraphStyle("AmountLabel", parent=styles["BodyText"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=9)), Paragraph(f"${float(artifact['amount']):,.2f}", styles["Amount"])], [Paragraph("", styles["BodySmall"]), Paragraph(escape(artifact["written_amount"]), styles["AmountWords"])]], colWidths=[1.25*inch,5.3*inch])
        amount_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#276D5A")),("SPAN",(0,0),(0,1)),("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),("TOPPADDING",(0,0),(-1,0),10),("BOTTOMPADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story += [amount_table]
        for key, title in (("scope","Scope of Work"),("inclusions","Inclusions"),("exclusions","Exclusions")):
            story.append(KeepTogether([Paragraph(title, styles["Section"]), Paragraph(escape(artifact.get(key) or "None stated."), styles["BodySmall"])]))
        story += [Spacer(1, 18), Paragraph("Artifact verification", styles["Section"]),
                  Paragraph(f"Immutable artifact: {escape(artifact['id'])}<br/>Source revision: {escape(artifact['revision_id'])}<br/>SHA-256: {escape(artifact['sha256'])}", ParagraphStyle("Verification", parent=styles["BodySmall"], fontSize=7, leading=10, textColor=colors.HexColor("#75837E"), wordWrap="CJK"))]
        def footer(canvas, document):
            canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#D6E0DC")); canvas.line(document.leftMargin, .42*inch, LETTER[0]-document.rightMargin, .42*inch)
            canvas.setFont("Helvetica", 7); canvas.setFillColor(colors.HexColor("#66766F")); canvas.drawString(document.leftMargin, .25*inch, f"{(artifact.get('bid_version') or {}).get('display',artifact.get('proposal_number','BID'))} - Immutable proposal {artifact['id']}")
            canvas.drawRightString(LETTER[0]-document.rightMargin, .25*inch, f"Page {document.page}"); canvas.restoreState()
        pdf.build(story, onFirstPage=footer, onLaterPages=footer)
        version = (artifact.get("bid_version") or {}).get("display", artifact.get("proposal_number", "bid")).replace(".", "-")
        project_label = artifact.get("project_number") or doc["project"].get("abbreviation") or project_id
        safe_label = "".join(c for c in str(project_label) if c.isalnum() or c in "_-") or project_id
        disposition = "attachment" if download else "inline"
        return Response(stream.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="proposal-{safe_label}-{version}.pdf"', "X-Proposal-Artifact": artifact["id"]})
    except Exception as exc:
        fail(exc)


@app.get("/api/configurations")
def configurations(actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    _, role = actor_role
    values = store.list_configurations()
    if role not in {"General Manager", "President", "Project Manager", "Systems Administrator"}:
        for value in values:
            value["pco"] = {"status": value.get("pco", {}).get("status", "pending"), "restricted": True}
    return {"configurations": values}


@app.post("/api/projects/{project_id}/commercial-impact")
def preview_commercial_impact(project_id: str, payload: dict = Body(...),
                              actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        current, current_configuration = load(project_id)
        expected = int(payload.get("expected_revision", current["project"].get("revision", 0)))
        if expected != int(current["project"].get("revision", 0)):
            raise ConflictError(
                f"Concurrent edit detected: expected revision {expected}, current revision {current['project'].get('revision', 0)}."
            )
        candidate_project = strip_ui_working_rows(deepcopy(payload.get("project", current)))
        if candidate_project.get("project", {}).get("id") != project_id:
            raise DomainError("Project identifier does not match route.")
        supplied_configuration = payload.get("configuration")
        if supplied_configuration is not None:
            require(role, "configuration")
            candidate_configuration = _configuration_candidate(current_configuration, supplied_configuration)
        else:
            require(role, "edit_estimate")
            candidate_configuration = current_configuration
            validate_project_inputs(candidate_project, current, current_configuration)
        baseline = calculate_project(deepcopy(current), current_configuration)
        projected = calculate_project(candidate_project, candidate_configuration)
        impacts = _commercial_impacts(baseline, projected)
        return {
            "project_id": project_id, "project_revision": current["project"].get("revision"),
            "requires_confirmation": bool(impacts), "impacts": impacts,
            "projected_totals": deepcopy(projected.get("working_estimate", {}).get("totals", {})),
            "previewed_by": actor,
        }
    except Exception as exc:
        fail(exc)


@app.post("/api/configurations")
def create_configuration(payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "configuration")
        source = store.load_configuration(payload.get("source_id", CONFIG_VERSION))
        config = _configuration_candidate(source, payload.get("configuration", source))
        project_id = payload.get("project_id")
        apply_to_project = bool(payload.get("apply_to_project") and project_id)
        current_project = current_configuration = projected_project = None
        impacts: list[dict[str, Any]] = []
        expected_revision: int | None = None
        if apply_to_project:
            current_project, current_configuration = load(str(project_id))
            expected_revision = int(payload.get("expected_project_revision", current_project["project"].get("revision", 0)))
            if expected_revision != int(current_project["project"].get("revision", 0)):
                raise ConflictError(
                    f"Concurrent edit detected: expected revision {expected_revision}, current revision {current_project['project'].get('revision', 0)}."
                )
            baseline = calculate_project(deepcopy(current_project), current_configuration)
            projected_project = calculate_project(deepcopy(current_project), config)
            impacts = _commercial_impacts(baseline, projected_project)
            if impacts and not payload.get("confirmed_commercial_impact"):
                raise DomainError(
                    "Configuration changes dollar or square-foot values and requires confirmation.",
                    "commercial_impact_confirmation_required", impacts,
                )
        config["id"] = uid("cfg")
        config["version"] = max((int(c.get("version", 0)) for c in store.list_configurations()), default=0) + 1
        config["created_at"] = now(); config["created_by"] = actor; config["status"] = "active" if apply_to_project else "draft"
        config.setdefault("audit_events", []).append({"id": uid("aud"), "timestamp": now(), "actor": actor, "role": role, "operation": "configuration_create", "reason": payload.get("reason", "New effective-dated configuration")})
        store.save_configuration(config)
        saved_project = None
        if apply_to_project and projected_project is not None and current_project is not None and expected_revision is not None:
            prior_configuration_id = current_project["project"].get("configuration_id")
            projected_project["project"]["configuration_id"] = config["id"]
            projected_project.setdefault("configuration_lineage", []).append({
                "configuration_id": config["id"], "adopted_at": now(), "actor": actor,
                "source_configuration_id": prior_configuration_id,
            })
            calculate_project(projected_project, config)
            audit(
                projected_project, actor, role, "project", str(project_id), "configuration_autosaved_and_adopted",
                {"configuration_id": prior_configuration_id},
                {"configuration_id": config["id"], "commercial_impacts": impacts},
                payload.get("reason", "Administration configuration autosave"),
            )
            saved_project = store.save_project(projected_project, expected_revision)
        return {"configuration": config, "project": None if saved_project is None else redact(saved_project, role), "impacts": impacts}
    except Exception as exc:
        fail(exc)


app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
