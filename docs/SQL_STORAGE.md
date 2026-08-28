# SQL storage and JSON classification

`data/murphywindow.db` is the application's sole authoritative persistent store. Normal startup initializes SQL schema migrations and performs SQL-to-SQL compatibility upgrades only. It does not scan, watch, import, restore, synchronize, or compare legacy filesystem data.

The provider boundary is `DatabaseProvider`; application repositories use parameterized DB-API operations and transactions. SQLite is the offline Windows provider. Provider-specific connection behavior and schema installation are isolated in `app/database.py` so a hosted provider can adapt connections, placeholders, and genuinely provider-specific DDL without changing UI or domain services.

## Controlled legacy migration

Legacy import is an explicit operator action:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_to_sql.py --data-root data --source-root C:\path\to\legacy-data
```

The command hashes its source manifest, imports and verifies records transactionally, records per-file hashes in `data_migrations`, and records durable status in `legacy_migration_runs`. A completed migration returns its recorded report and will not scan or re-import changed files. The former JSON store implementation has been removed; `JsonStore` is now only a compatibility import name for `SqlStore`.

## Remaining JSON classifications

Every remaining JSON file is covered by one of these non-authoritative categories:

| Path | Category | Runtime authority |
| --- | --- | --- |
| `docs/PROJECT_SCHEMA.json` | Static documentation/schema | None |
| `app/static-data/codes.json` | Immutable bootstrap seed for an empty SQL database | None after insertion; SQL is authoritative |
| `legacy-data/sql-cutover-2026-08-26/**/*.json` | Verified SQL migration inputs archived outside `data/` | None; retained only as rollback evidence |
| `tests/**`, `.pytest-tmp*/**`, `tmp/pytest-*/**` JSON | Test fixtures and temporary test output | None |
| Project JSON returned by `GET /api/projects/{id}/export` | Explicit user-initiated interchange/download | None; importing requires the explicit import endpoint and creates an SQL record |

JSON serialization inside services is used for HTTP payloads, immutable hashing, SQL aggregate columns, or explicit interchange. It does not write runtime application state to files. `scripts/seed_live_testing_alternates.py`, `scripts/import_codes.py`, and `scripts/migrate_to_sql.py` print JSON reports to standard output only. The cost-code importer writes through `SqlStore.save_cost_code_reference`; it does not create a persistent JSON file.

The live `data/` directory contains the SQLite database and optional user-selected export output only. Removing the archived legacy JSON tree cannot affect startup or CRUD behavior.
