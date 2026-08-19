# Job-data interchange schema 1.0.0

`GET /api/projects/{id}/job-data` and the **Copy job data** action produce a UTF-8 JSON object with:

- `schema`: constant `murphywindow.job-data`;
- `version`: `1.0.0`;
- `generated_at`: UTC ISO-8601 timestamp;
- `project`, `contacts`, and `quotes`: authoritative project records;
- `bid`: the current server-calculated working estimate, including lines, totals, warnings, alternate inclusion, and lineage;
- `submissions` and `award`: immutable lifecycle references/snapshots;
- `contract`: current normalized contract allocations;
- `bid_tabulation`: market comparison records.

Arrays are always arrays, including when empty. JSON escaping is handled by the server serializer. Stable record IDs—not display labels or former workbook coordinates—are relationship keys. Commercially restricted PCO stages are outside this interchange contract.

Import accepts the full project document described by `docs/PROJECT_SCHEMA.json`, not the smaller job-data payload. By default import creates a new project ID so an existing local project is never overwritten.

