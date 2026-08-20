"""Reusable JSON master-data directory and indexed historical search."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any, Iterable

from .persistence import JsonStore


DIRECTORY_SCHEMA_VERSION = "1.0.0"
STANDARD_CONTACT_ROLES = {"Owner", "Architect", "Vendor", "Engineer", "GC", "CM"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_search_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _stable_id(prefix: str, *parts: Any) -> str:
    basis = "|".join(normalize_search_text(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:24]}"


def new_master_directory() -> dict[str, Any]:
    return {
        "schema_version": DIRECTORY_SCHEMA_VERSION,
        "revision": 0,
        "created_at": _now(),
        "updated_at": None,
        "organizations": [],
        "person_organization_contacts": [],
        "text_entities": [],
        "seeded_project_ids": [],
        "seeded_project_fingerprints": {},
        "index": {"exact": {}, "prefix": {}, "trigram": {}, "record_keys": {}},
    }


def _unique_text(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = normalize_search_text(text)
        if text and key and key not in seen:
            output.append(text)
            seen.add(key)
    return output


def _merge_sources(existing: list[dict], additions: Iterable[dict] | None) -> list[dict]:
    output = deepcopy(existing)
    seen = {json.dumps(item, sort_keys=True, default=str) for item in output}
    for item in additions or []:
        if not isinstance(item, dict):
            continue
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            output.append(deepcopy(item))
            seen.add(key)
    return output


def _find_by_normalized_name(records: list[dict], display_name: str) -> dict | None:
    target = normalize_search_text(display_name)
    for record in records:
        values = [record.get("display_name") or record.get("name"), *record.get("aliases", [])]
        if target and any(normalize_search_text(value) == target for value in values):
            return record
    return None


def upsert_organization(
    directory: dict[str, Any], record: dict[str, Any], *, rebuild_index: bool = True
) -> dict[str, Any]:
    """Insert or merge an organization while preserving canonical capitalization."""
    display_name = str(record.get("display_name") or record.get("official_name") or "").strip()
    if not display_name:
        raise ValueError("Organization display_name is required.")
    organizations = directory.setdefault("organizations", [])
    existing = None
    if record.get("id"):
        existing = next((item for item in organizations if item.get("id") == record["id"]), None)
    existing = existing or _find_by_normalized_name(organizations, display_name)
    if existing is None:
        existing = {
            "id": record.get("id") or _stable_id("org", display_name),
            "display_name": display_name,
            "legal_name": record.get("legal_name") or "",
            "aliases": [],
            "classifications": [],
            "address": record.get("address") or "",
            "website": record.get("website") or "",
            "primary_phone": record.get("primary_phone") or record.get("phone") or "",
            "email": record.get("email") or "",
            "notes": record.get("notes") or "",
            "sources": [],
            "created_at": record.get("created_at") or _now(),
            "updated_at": record.get("updated_at") or _now(),
        }
        organizations.append(existing)
    for field in ("legal_name", "address", "website", "primary_phone", "email", "notes"):
        if not existing.get(field) and record.get(field):
            existing[field] = record[field]
    aliases = [*existing.get("aliases", []), *record.get("aliases", [])]
    if normalize_search_text(display_name) != normalize_search_text(existing.get("display_name")):
        aliases.append(display_name)
    existing["aliases"] = _unique_text(aliases)
    existing["classifications"] = _unique_text([
        *existing.get("classifications", []), *record.get("classifications", [])
    ])
    existing["sources"] = _merge_sources(existing.get("sources", []), record.get("sources"))
    existing["updated_at"] = _now()
    if rebuild_index:
        build_search_index(directory)
    return existing


def upsert_person_organization_contact(
    directory: dict[str, Any], record: dict[str, Any], *, rebuild_index: bool = True
) -> dict[str, Any]:
    """Insert or merge one person-at-one-organization relationship."""
    name = str(record.get("name") or record.get("display_name") or "").strip()
    if not name:
        raise ValueError("Contact name is required.")
    organization_id = record.get("organization_id")
    contacts = directory.setdefault("person_organization_contacts", [])
    existing = None
    if record.get("id"):
        existing = next((item for item in contacts if item.get("id") == record["id"]), None)
    if existing is None:
        target = normalize_search_text(name)
        existing = next((
            item for item in contacts
            if item.get("organization_id") == organization_id
            and target in {
                normalize_search_text(item.get("name")),
                *(normalize_search_text(alias) for alias in item.get("aliases", [])),
            }
        ), None)
    if existing is None:
        existing = {
            "id": record.get("id") or _stable_id("person_org", organization_id or "none", name),
            "name": name,
            "organization_id": organization_id,
            "aliases": [],
            "roles": [],
            "position": record.get("position") or "",
            "email": record.get("email") or "",
            "office_phone": record.get("office_phone") or record.get("phone") or "",
            "mobile_phone": record.get("mobile_phone") or "",
            "notes": record.get("notes") or "",
            "sources": [],
            "created_at": record.get("created_at") or _now(),
            "updated_at": record.get("updated_at") or _now(),
        }
        contacts.append(existing)
    for field in ("position", "email", "office_phone", "mobile_phone", "notes"):
        if not existing.get(field) and record.get(field):
            existing[field] = record[field]
    aliases = [*existing.get("aliases", []), *record.get("aliases", [])]
    if normalize_search_text(name) != normalize_search_text(existing.get("name")):
        aliases.append(name)
    existing["aliases"] = _unique_text(aliases)
    existing["roles"] = _unique_text([*existing.get("roles", []), *record.get("roles", [])])
    existing["sources"] = _merge_sources(existing.get("sources", []), record.get("sources"))
    existing["updated_at"] = _now()
    if rebuild_index:
        build_search_index(directory)
    return existing


def upsert_text_entity(
    directory: dict[str, Any], record: dict[str, Any], *, rebuild_index: bool = True
) -> dict[str, Any]:
    kind = str(record.get("kind") or "").strip()
    display_name = str(record.get("display_name") or record.get("name") or "").strip()
    if not kind or not display_name:
        raise ValueError("Text entity kind and display_name are required.")
    records = directory.setdefault("text_entities", [])
    target = normalize_search_text(display_name)
    existing = None
    if record.get("id"):
        existing = next((item for item in records if item.get("id") == record["id"]), None)
    if existing is None:
        existing = next((
            item for item in records
            if item.get("kind") == kind and target in {
                normalize_search_text(item.get("display_name")),
                *(normalize_search_text(alias) for alias in item.get("aliases", [])),
            }
        ), None)
    if existing is None:
        existing = {
            "id": record.get("id") or _stable_id("text", kind, display_name),
            "kind": kind,
            "display_name": display_name,
            "aliases": [],
            "notes": record.get("notes") or "",
            "sources": [],
            "created_at": record.get("created_at") or _now(),
            "updated_at": record.get("updated_at") or _now(),
        }
        records.append(existing)
    aliases = [*existing.get("aliases", []), *record.get("aliases", [])]
    if normalize_search_text(display_name) != normalize_search_text(existing.get("display_name")):
        aliases.append(display_name)
    existing["aliases"] = _unique_text(aliases)
    if not existing.get("notes") and record.get("notes"):
        existing["notes"] = record["notes"]
    existing["sources"] = _merge_sources(existing.get("sources", []), record.get("sources"))
    existing["updated_at"] = _now()
    if rebuild_index:
        build_search_index(directory)
    return existing


def _trigrams(value: str) -> set[str]:
    return {value[index:index + 3] for index in range(max(0, len(value) - 2))}


def _add_index(index: dict[str, list[str]], key: str, reference: str) -> None:
    values = index.setdefault(key, [])
    if reference not in values:
        values.append(reference)


def build_search_index(directory: dict[str, Any]) -> dict[str, Any]:
    exact: dict[str, list[str]] = {}
    prefix: dict[str, list[str]] = {}
    trigram: dict[str, list[str]] = {}
    record_keys: dict[str, list[dict[str, str]]] = {}

    collections = (
        ("organization", directory.get("organizations", []), "display_name"),
        ("contact", directory.get("person_organization_contacts", []), "name"),
        ("text", directory.get("text_entities", []), "display_name"),
    )
    for kind, records, display_field in collections:
        for record in records:
            reference = f"{kind}|{record['id']}"
            keys: list[dict[str, str]] = []
            for source, raw in (
                ("display", record.get(display_field)),
                *(("alias", alias) for alias in record.get("aliases", [])),
            ):
                normalized = normalize_search_text(raw)
                if not normalized or any(item["value"] == normalized for item in keys):
                    continue
                keys.append({"value": normalized, "source": source, "raw": str(raw)})
                _add_index(exact, normalized, reference)
                for length in range(1, min(len(normalized), 40) + 1):
                    _add_index(prefix, normalized[:length], reference)
                for token in _trigrams(normalized):
                    _add_index(trigram, token, reference)
            record_keys[reference] = keys
    content = json.dumps(record_keys, sort_keys=True, ensure_ascii=False)
    directory["index"] = {
        "exact": exact,
        "prefix": prefix,
        "trigram": trigram,
        "record_keys": record_keys,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    return directory["index"]


def _records_by_reference(directory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for kind, records in (
        ("organization", directory.get("organizations", [])),
        ("contact", directory.get("person_organization_contacts", [])),
        ("text", directory.get("text_entities", [])),
    ):
        for record in records:
            output[f"{kind}|{record['id']}"] = record
    return output


def _match_score(query: str, key: dict[str, str]) -> tuple[float, str] | None:
    value, source = key["value"], key["source"]
    alias = source == "alias"
    if value == query:
        return (98.0 if alias else 100.0), ("alias_exact" if alias else "exact")
    if value.startswith(query):
        return (88.0 if alias else 92.0) + min(3.0, len(query) / max(1, len(value)) * 3), ("alias_prefix" if alias else "prefix")
    if query in value:
        return (78.0 if alias else 82.0) + min(3.0, len(query) / max(1, len(value)) * 3), ("alias_substring" if alias else "substring")
    ratio = SequenceMatcher(None, query, value).ratio()
    if ratio < 0.62:
        return None
    return 55.0 + ratio * 30.0 - (2.0 if alias else 0.0), ("alias_fuzzy" if alias else "fuzzy")


def search_master_data(
    directory: dict[str, Any],
    query: str,
    *,
    entity_kinds: Iterable[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    normalized = normalize_search_text(query)
    if not normalized:
        return {"query": query, "normalized_query": "", "results": [], "ambiguous": False, "resolved_id": None}
    limit = max(1, min(int(limit), 100))
    index = directory.get("index") or {}
    if not index.get("record_keys"):
        index = build_search_index(directory)
    allowed = set(entity_kinds or ("organization", "contact", "text"))
    references = _records_by_reference(directory)

    candidates = set(index.get("exact", {}).get(normalized, []))
    candidates.update(index.get("prefix", {}).get(normalized, []))
    if len(normalized) <= 4:
        candidates.update(index.get("record_keys", {}).keys())
    else:
        for token in _trigrams(normalized):
            candidates.update(index.get("trigram", {}).get(token, []))
    candidates = {ref for ref in candidates if ref.split("|", 1)[0] in allowed}

    results: list[dict[str, Any]] = []
    for reference in candidates:
        record = references.get(reference)
        if not record:
            continue
        best: tuple[float, str, dict[str, str]] | None = None
        for key in index["record_keys"].get(reference, []):
            match = _match_score(normalized, key)
            if match and (best is None or match[0] > best[0]):
                best = (match[0], match[1], key)
        if best is None:
            continue
        kind = reference.split("|", 1)[0]
        display_name = record.get("display_name") or record.get("name") or ""
        secondary = ""
        if kind == "contact":
            organization = references.get(f"organization|{record.get('organization_id')}")
            secondary = organization.get("display_name", "") if organization else ""
        elif kind == "text":
            secondary = record.get("kind", "")
        results.append({
            "id": record.get("id"), "entity_kind": kind,
            "display_name": display_name, "secondary": secondary,
            "match_type": best[1], "score": best[0],
            "matched_value": best[2]["raw"],
            "aliases": deepcopy(record.get("aliases", [])),
        })
    results.sort(key=lambda item: (-item["score"], normalize_search_text(item["display_name"]), item["id"]))
    results = results[:limit]
    ambiguous = len(results) > 1 and results[0]["score"] - results[1]["score"] <= 2.5
    resolved_id = None
    if results and not ambiguous and results[0]["match_type"] in {"exact", "alias_exact"}:
        resolved_id = results[0]["id"]
    return {
        "query": query,
        "normalized_query": normalized,
        "results": results,
        "ambiguous": ambiguous,
        "resolved_id": resolved_id,
    }


def _classification(role: Any) -> str | None:
    normalized = normalize_search_text(role)
    return {
        "owner": "Owner", "architect": "Architect", "vendor": "Vendor",
        "supplier": "Vendor", "engineer": "Engineer",
        "gc": "GC", "general contractor": "GC",
        "cm": "CM", "construction manager": "CM",
    }.get(normalized)


def _project_master_fingerprint(document: dict[str, Any]) -> str:
    """Hash only fields that can contribute reusable suggestions."""
    project = document.get("project", {})
    payload = {
        "project_id": project.get("id"),
        "project": {
            field: project.get(field)
            for field in (
                "owner_name", "owner_legal_name", "owner_address", "owner_website", "owner_phone", "owner_email", "architect", "engineer",
                "general_contractor", "construction_manager", "estimator", "plan_source",
            )
        },
        "contacts": document.get("contacts", []),
        "quote_vendors": [
            {"id": row.get("id"), "vendor": row.get("vendor")}
            for row in document.get("quotes", [])
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seed_master_data(
    projects: Iterable[dict[str, Any]], directory: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Index historical values without modifying any source project document."""
    result = deepcopy(directory) if directory is not None else new_master_directory()
    seeded = set(result.setdefault("seeded_project_ids", []))
    fingerprints = result.setdefault("seeded_project_fingerprints", {})
    organization_fields = (
        ("owner_name", "Owner", "owner_address"),
        ("architect", "Architect", None),
        ("engineer", "Engineer", None),
        ("general_contractor", "GC", None),
        ("construction_manager", "CM", None),
    )
    for document in projects:
        if not isinstance(document, dict):
            continue
        project = document.get("project", {})
        project_id = str(project.get("id") or "unknown")
        fingerprint = _project_master_fingerprint(document)
        if fingerprints.get(project_id) == fingerprint:
            continue
        seeded.add(project_id)
        for field, classification, address_field in organization_fields:
            name = str(project.get(field) or "").strip()
            if name:
                owner_details = {
                    "legal_name": project.get("owner_legal_name"),
                    "website": project.get("owner_website"),
                    "primary_phone": project.get("owner_phone"),
                    "email": project.get("owner_email"),
                } if field == "owner_name" else {}
                upsert_organization(result, {
                    "display_name": name,
                    "classifications": [classification],
                    "address": project.get(address_field) if address_field else "",
                    **owner_details,
                    "sources": [{"project_id": project_id, "field": f"project.{field}"}],
                }, rebuild_index=False)
        for field, kind in (("estimator", "estimator"), ("plan_source", "plan_source")):
            value = str(project.get(field) or "").strip()
            if value:
                upsert_text_entity(result, {
                    "kind": kind, "display_name": value,
                    "sources": [{"project_id": project_id, "field": f"project.{field}"}],
                }, rebuild_index=False)
        for quote in document.get("quotes", []):
            vendor = str(quote.get("vendor") or "").strip()
            if vendor:
                upsert_organization(result, {
                    "display_name": vendor, "classifications": ["Vendor"],
                    "sources": [{"project_id": project_id, "field": "quotes.vendor", "source_id": quote.get("id")}],
                }, rebuild_index=False)
        for contact in document.get("contacts", []):
            organization_name = str(contact.get("organization") or "").strip()
            role = str(contact.get("role") or "").strip()
            organization = None
            if organization_name:
                classification = _classification(role)
                organization = upsert_organization(result, {
                    "display_name": organization_name,
                    "classifications": [classification] if classification else [],
                    "sources": [{"project_id": project_id, "field": "contacts.organization", "source_id": contact.get("id")}],
                }, rebuild_index=False)
            name = str(contact.get("name") or "").strip()
            if name:
                upsert_person_organization_contact(result, {
                    "name": name, "organization_id": organization.get("id") if organization else None,
                    "roles": [role] if role else [], "position": contact.get("position"),
                    "email": contact.get("email"), "office_phone": contact.get("phone"),
                    "mobile_phone": contact.get("mobile_phone"),
                    "sources": [{"project_id": project_id, "field": "contacts", "source_id": contact.get("id")}],
                }, rebuild_index=False)
            if role and role not in STANDARD_CONTACT_ROLES and _classification(role) is None:
                upsert_text_entity(result, {
                    "kind": "contact_role", "display_name": role,
                    "sources": [{"project_id": project_id, "field": "contacts.role", "source_id": contact.get("id")}],
                }, rebuild_index=False)
        fingerprints[project_id] = fingerprint
    result["seeded_project_ids"] = sorted(seeded)
    result["seeded_project_fingerprints"] = dict(sorted(fingerprints.items()))
    build_search_index(result)
    return result


class MasterDataRepository:
    """Persistence adapter for the reusable directory document."""

    def __init__(self, store: JsonStore, name: str = "directory"):
        self.store = store
        self.name = name

    def load_or_create(self) -> dict[str, Any]:
        path = self.store.master_data_path(self.name)
        return self.store.load_master_data(self.name) if path.exists() else new_master_directory()

    def save(self, directory: dict[str, Any], expected_revision: int | None = None) -> dict[str, Any]:
        prepared = deepcopy(directory)
        build_search_index(prepared)
        expected = prepared.get("revision", 0) if expected_revision is None else expected_revision
        return self.store.save_master_data(prepared, int(expected), name=self.name)

    def seed_projects(self, projects: Iterable[dict[str, Any]]) -> dict[str, Any]:
        current = self.load_or_create()
        fingerprints = current.get("seeded_project_fingerprints", {})
        new_projects = [
            project for project in projects
            if isinstance(project, dict)
            and fingerprints.get(str(project.get("project", {}).get("id") or "unknown"))
            != _project_master_fingerprint(project)
        ]
        if not new_projects:
            return current
        seeded = seed_master_data(new_projects, current)
        return self.save(seeded, int(current.get("revision", 0)))

    def search(
        self, query: str, *, entity_kinds: Iterable[str] | None = None, limit: int = 10
    ) -> dict[str, Any]:
        return search_master_data(
            self.load_or_create(), query, entity_kinds=entity_kinds, limit=limit
        )
