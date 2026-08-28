# Job-data interchange schema 1.5.0

`GET /api/projects/{id}/job-data` and the **Copy job data** action produce a UTF-8 JSON object with:

- `schema`: constant `murphywindow.job-data`;
- `version`: `1.5.0`;
- `generated_at`: UTC ISO-8601 timestamp;
- `project`, `contacts`, and `quotes`: authoritative project records;
- `bid`: the current server-calculated Base estimate, including lines, totals, warnings, alternate deltas, and lineage;
- `submissions` and `award`: immutable lifecycle references/snapshots;
- `contract`: current normalized contract allocations;
- `bid_tabulation`: market comparison records.

Arrays are always arrays, including when empty. JSON escaping is handled by the server serializer. Stable record IDs—not display labels or former workbook coordinates—are relationship keys. Commercially restricted PCO stages are outside this interchange contract.

Import accepts the full project document described by `docs/PROJECT_SCHEMA.json`, not the smaller job-data payload. By default import creates a new project ID so an existing local project is never overwritten.

Version 1.2.0 replaced prefixed alternate rows and inclusion checkboxes with canonical Base-plus-delta alternates. Each alternate stores only added records, removed Base record IDs, and explicit field overrides; its effective commercial state, conflicts, Cost Code impacts, Add/Deduct classification, and deterministic Scope of Change are calculated from Base. The migration converts active 1.1 prefixed rows to alternate-only additions and preserves immutable historical payloads unchanged.

Version 1.3.0 adds optional alternate names, explicit Grouping / Spec Code versus Actual Cost Code output, and typed line-markup authority. `working_estimate.component_markup_overrides[source_key]` stores either `{mode: "percentage", value}` or `{mode: "amount", value}` with provenance. Alternate line-markup decisions use the same representation as Base-plus-delta overrides, so an inheriting alternate follows later Base changes while an explicitly overridden alternate remains fixed. Legacy `{rate}` records are migrated losslessly to percentage mode. Older 1.0–1.2 project documents are migrated in memory before use; migration is idempotent.

Version 1.5.0 adds substantial and final completion dates, date-time walkthroughs, addresses for project parties and contacts, stable Frame Spec Section tab ordering, a separate Borrowed Lite location field, and direct custom Installation Material quantities. Version 1.4.0 normalized optional zero quantities to null. Older active documents migrate in memory; immutable historical snapshots remain unchanged.

The immutable proposal snapshot envelope remains version 1.0.0: it already freezes the complete canonical project/configuration state, so these new commercial fields are additive payload content rather than an envelope-format change. Existing snapshot files are never migrated or rewritten.

`takeoff_sections[].additional_materials` optionally stores project-specific Installation Material definitions. These records use the controlled material calculation vocabulary (`square_feet`, `perimeter_lf`, `head_sill_qty`, `caulking_lf`, `quantity`, `tie_back_qty`, `backpan_lf`, or `manual_quantity`). Formula definitions use `operator` (`multiply`, `divide`, `add`, or `subtract`) and `operand`; legacy `factor` remains equivalent to a multiply operand. Per-section project formula changes remain isolated in `material_overrides[material_id]` through `source_override`, `operator_override`, and `operand_override`, and can be removed to restore the controlled formula. A `controlled_rate_id` may reference controlled configuration; project rates remain in `material_overrides[material_id].rate_override`, so project edits never mutate controlled Rates. The material's existing `cost_code` field is its Actual Cost Code classification and may use the full controlled reference. The containing Frame Spec Section's `code` is the Grouping / Spec Code used for scope, Bid aggregation, and cascade dependencies. An absent `additional_materials` member remains equivalent to an empty array.
