# Owner cost-code reference

Source: `codes.xlsx`, worksheet `Sheet1`, range `A1:B9332`, supplied August 17, 2026.

| Check | Result |
| --- | ---: |
| Populated source rows | 9,332 |
| Normalized unique codes | 9,330 |
| Blank codes | 0 |
| Blank descriptions | 0 |
| Duplicate normalized codes | 2 |
| Source SHA-256 | `5f2bb30463165990d7ad5a6a4cc341d9acd4509de6a331298ba63ebb31f7a026` |

The importer treats both columns as data only. It does not evaluate cell text as commands or instructions.

## Preserved duplicates

- `06 05 73`: source rows 1404–1405, preferred description `Wood Treatment`, alias `Wood Treatments`.
- `21 13 00`: source rows 4016–4017, preferred description `Fire-Suppression Sprinkler Systems`, alias `Fire Suppression Sprinkler System`.

Trailing spaces in the second occurrence normalize to the same stable code. The application exposes one searchable code record and preserves the alternate description and both source row numbers. It does not silently discard either source entry.

## Application behavior

`data/reference/codes.json` is the canonical imported payload. Configuration `cfg-2026-08-17-v2` first adopted it; current configuration `cfg-2026-08-19-v5` retains the same owner-confirmed reference, owner rate tables, and versioned mileage settings while adding the schema 1.1 policy metadata. Search matches display code, normalized code, primary description, and description aliases. Selecting a result creates a project cost-code record containing the reference ID and reference configuration ID.

An entered code not found in this list is preserved for correction and produces a field-specific `invalid_cost_code` validation warning. The list does not supply internal MWD mappings, vendor directories, deduct status, tax treatment, or commercial pricing; those remain separate versioned data and must not be inferred from the code description.

Project scope records and Frame Spec Sections use the selected code as a Grouping / Spec Code. A project-specific Installation Material may use any entry in this full reference as its Actual Cost Code without adding that entry to project scope. Actual classification is shown separately in Bid and does not create a top-level subtotal or a scope-removal dependency. Authorization for an Actual Cost Code outside this controlled reference remains unresolved and protected.

Re-import with:

```powershell
.\.venv\Scripts\python.exe scripts\import_codes.py C:\path\to\codes.xlsx data\reference\codes.json
```

Review the reported counts/hash and run the full tests before creating and activating a new configuration version. Historical submitted and awarded estimates remain pinned to their original configuration.
