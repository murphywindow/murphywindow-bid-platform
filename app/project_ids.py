"""Compact, URL-safe project identity generation."""
from __future__ import annotations

import re
from collections.abc import Collection
from uuid import UUID, uuid4


PROJECT_ID_CAPACITY = 2 ** 122
PROJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SEED_TEST_PROJECT_ID = "06e84ea0-a276-45e2-af97-0d220556b945"
LEGACY_SEED_TEST_PROJECT_ID = "prj_00000000000000000000000000004320"


def is_project_id(value: object) -> bool:
    return bool(PROJECT_ID_PATTERN.fullmatch(str(value or "")))


def random_project_id(existing: Collection[str] = ()) -> str:
    """Return a canonical UUID v4 not present in ``existing``."""
    occupied = {str(value).lower() for value in existing}
    if len(occupied) >= PROJECT_ID_CAPACITY:
        raise RuntimeError("The project ID space is exhausted.")
    while True:
        candidate = str(uuid4())
        if candidate not in occupied:
            return candidate


def canonical_legacy_uuid(value: str) -> str | None:
    """Preserve the UUID identity used by legacy ``prj_<uuidhex>`` IDs."""
    match = re.fullmatch(r"prj_([0-9a-f]{32})", str(value or ""))
    if not match:
        return None
    parsed = UUID(hex=match.group(1))
    return str(parsed) if parsed.version == 4 else None
