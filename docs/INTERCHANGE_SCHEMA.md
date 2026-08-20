# Job-data interchange schema 1.2.0

`GET /api/projects/{id}/job-data` and the **Copy job data** action produce a UTF-8 JSON object with:

- `schema`: constant `murphywindow.job-data`;
- `version`: `1.2.0`;
- `generated_at`: UTC ISO-8601 timestamp;
- `project`, `contacts`, and `quotes`: authoritative project records;
- `bid`: the current server-calculated Base estimate, including lines, totals, warnings, alternate deltas, and lineage;
- `submissions` and `award`: immutable lifecycle references/snapshots;
- `contract`: current normalized contract allocations;
- `bid_tabulation`: market comparison records.

Arrays are always arrays, including when empty. JSON escaping is handled by the server serializer. Stable record IDs—not display labels or former workbook coordinates—are relationship keys. Commercially restricted PCO stages are outside this interchange contract.

Import accepts the full project document described by `docs/PROJECT_SCHEMA.json`, not the smaller job-data payload. By default import creates a new project ID so an existing local project is never overwritten.

Version 1.2.0 replaces prefixed ALT rows and inclusion checkboxes with canonical Base-plus-delta alternates. Each alternate stores only added records, removed Base record IDs, and explicit field overrides; its effective commercial state, conflicts, Cost Code impacts, Add/Deduct classification, and deterministic Scope of Change are calculated from Base. The migration converts active 1.1 prefixed rows to ALT-only additions and preserves immutable historical payloads unchanged. Older 1.0 and 1.1 project documents are migrated in memory before use; migration is idempotent.

`takeoff_sections[].additional_materials` optionally stores project-specific Installation Material definitions. These records use the controlled material calculation vocabulary (`perimeter_lf`, `head_sill_qty`, `caulking_lf`, `quantity`, `tie_back_qty`, `backpan_lf`, or `manual_quantity`). A `controlled_rate_id` may reference controlled configuration; project rates remain in `material_overrides[material_id].rate_override`, so project edits never mutate controlled Rates. An absent `additional_materials` member is equivalent to an empty array, which keeps existing schema 1.2 documents valid without a destructive migration.
