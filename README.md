# Murphy Window Bid Platform

A local, browser-based estimating application controlled by **INF-4320 v2.2.0**. The current software release is **v2.3.0**. It uses FastAPI and a lightweight server-rendered shell/vanilla browser client—no Node production service and no external database. All authoritative data remains in human-readable JSON on this Windows computer.

## Launch

From PowerShell:

```powershell
cd C:\Users\MicahJohnson\GitHub\murphywindow-bid-platform
.\launch.ps1
```

The launcher creates/reuses `.venv`, installs the pinned `requirements.txt` when its hash changes, starts on `http://127.0.0.1:8765`, and opens the default browser. Override the port with `./launch.ps1 -Port 9000` or `$env:MURPHY_BID_PORT=9000`. The server binds only to localhost.

Stop cleanly with **Ctrl+C** in the launcher window. Project saves are discrete server transactions; there is no partially open database transaction on shutdown. A tab with unsaved changes displays a browser warning.

## Data, saves, and recovery

- Primary projects: `data/projects/<stable-project-id>.json`
- Automatic/manual snapshots: `data/backups/<stable-project-id>/`
- Effective-dated configuration: `data/configurations/`
- Reusable historical master data: `data/master-data/`
- Controlled historical comparison fixtures: `data/historical-reference/` (kept out of the normal project picker)
- Local hash-backed application secrets: `data/secrets/` (ignored by Git)
- Optional export workspace: `data/exports/`
- Immutable proposal snapshots: `data/proposals/<stable-project-id>/<proposal-id>.json`
- Original proposal PDFs: `data/proposal-artifacts/<stable-project-id>/<artifact-id>.pdf`

An actual committed form change marks the tab **Unsaved changes** and starts an immediate save after a 250 ms browser-event debounce. Rapid changes may share one atomic disk write, but every changed datapoint receives its own bid patch increment and audit event. The client shows **Saving**, **Saved**, **Unsaved changes**, **Save failed**, or **Save conflict** and never starts overlapping saves. Explicit Save uses the same transaction immediately.

### Bid version convention

Every project shows a bid-semantic version such as `B0.3.7`:

- **Patch** increments for each committed datapoint modification and each recorded action (review, backup, re-estimate, PCO, SOV, etc.). Ten fields changed within one autosave window are one atomic disk write but ten patch increments and ten datapoint audit events.
- **Minor** increments and patch resets to zero when an immutable bid submission is created.
- **Major** increments and minor/patch reset to zero when notice-to-proceed activation creates the awarded baseline.

The independent JSON file `revision` is a concurrency/persistence counter; the `Bmajor.minor.patch` value is the user-facing bid/workflow version. A submitted estimate revision stores its exact bid version, and an award records both the accepted submitted version and activation version.

Those counters are not proposal identities. Autosave revision ≠ Proposal version, and current editable state ≠ historical Proposal snapshot. Explicit generation assigns an immutable `P1`, `P2`, … identity plus a separately editable Proposal Name. The complete normalized project and effective configuration are canonicalized with sorted object keys and hashed with SHA-256. Operational metadata (file revision, autosave/update time, bid patch counter, audit/history IDs, UI state, proposal/artifact identity, and branch metadata) is excluded; all commercial inputs, descriptions, source selection, calculated results, proposal language, and frozen effective configuration are included. Exact fingerprints are rejected as duplicates even when a different name is entered; the same price is permitted when any included state differs.

### Software release version

The platform itself follows Semantic Versioning (`MAJOR.MINOR.PATCH`). The authoritative value is in `app/version.py`, is used by FastAPI, and is returned by `/api/health`. Release history is maintained in [CHANGELOG.md](CHANGELOG.md). This software version is deliberately separate from project schema, job-data interchange, configuration, generator, JSON file revision, and the per-project `Bmajor.minor.patch` bid lifecycle.

Before replacing an existing primary file, the server copies it to the project backup directory. It writes the new JSON to a temporary sibling, flushes and `fsync`s it, then uses atomic `os.replace`; a failed/interrupted write leaves the prior primary intact. Twenty backups are retained by default. **Backup** creates a labeled manual snapshot. **Refresh** warns before discarding dirty or failed changes. Expected file revisions detect concurrent-tab edits; reload one tab and reapply its changes rather than overwriting the other.

If a primary JSON is malformed, Open offers the newest valid backup. To restore explicitly, use the recovery API (`POST /api/projects/{id}/recover` with `{"backup":"filename.json"}`) after reviewing the backup list returned by Open. Recovery is audited. For manual disaster recovery, stop the server, copy a validated backup to a new filename outside `data`, then use project Import so the original is not overwritten.

Write-permission failures leave the in-browser document dirty and show **Save failed**. Restore write permission to `data`, then press Save. Do not close the only dirty tab until Save succeeds or export/copy its data.

### Driving mileage from Rogers

Enter a complete job street address, city/state, and ZIP on Project Information. After the address change is committed, the app automatically requests a route; **Calculate route** retries on demand. It geocodes the destination, calculates the fastest driving route from the configured Rogers, Minnesota 55374 city-center point, converts route meters to miles, and rounds half-up to one decimal. The mileage remains manually editable.

The calculation stores the input and matched addresses, origin/destination coordinates, miles, route duration, providers, rounding rule, timestamp, and application-settings configuration ID. A repeated unchanged address uses the persisted result unless a manual retry is requested. Failures never erase the prior mileage. The lookup requires internet access and currently uses the U.S. Census Geocoder first, OpenStreetMap Nominatim as a rate-limited cached fallback, and OSRM for routing. Public-service availability is not guaranteed; configure self-hosted or contracted endpoints before broader/multi-user deployment. The default city-center origin is configurable and should be replaced with the exact approved Rogers departure location if mileage policy requires it.

## Realistic test-project generator

The home page includes **Generate realistic test project**. It creates and immediately persists a clearly labeled synthetic draft at `B0.0.0`. Leave the seed blank for a new scenario, or enter the same number or memorable text to reproduce the same profile and values in a distinct project file.

Generation is curated rather than unconstrained randomness. A scenario contains aligned project information and dates, six contacts, owner-reference cost codes covering every generated source (including Equipment), Base quote/frame/door/equipment/borrowed-lite/labor data, and inherited ALT1 differences migrated into the canonical Base-plus-delta model. Across Base and ALT-specific additions it includes four three-vendor quote groups, five frame sections with 40 dimensional rows, and the other documented test buckets. Names and email domains are fictitious, the internal notes and project list identify test data, and no generated project is submitted or awarded. Travel, contingency, and bond remain disabled because generation must not silently assert unresolved policy.

### Base-plus-delta alternates

Base is the primary estimate. Creating an alternate immediately exposes inherited Base records on each applicable estimating page; unchanged fields continue to inherit future Base corrections. Alternate edits store explicit Added records, Removed Base IDs, or Modified field overrides. If Base later changes an overridden field, the alternate retains the override, shows Original Base / Current Base / Alternate override, and offers reset-to-inherit. User-facing labels are deterministic (`Alternate 1` or `Alternate 1 — North Elevation`) while stable internal IDs and keys remain unchanged. The Bid engine recalculates the effective alternate through the same authoritative services as Base, then reports effective Alternate minus Base by Cost Code, source category, and total. Add/Deduct/Zero is derived from the net selling-value delta. The deterministic Scope of Change and separate customer description flow into Bid, Proposal, immutable snapshots, PDFs, and comparisons.

### Frame Installation Materials and Bid detail

Each Frame Spec Section can add project-specific Installation Materials alongside controlled defaults. The section code is the Grouping / Spec Code; each added material may independently choose an Actual Cost Code from the full controlled reference without adding it to project scope. Added lines use the same basis/factor/rate calculation path, may reference a controlled Rate without modifying it, and participate in per-frame applicability, alternates, Bid, Proposal snapshots, comparison, and audit. Removal requires confirmation when applicability or downstream cost exists.

The Bid Cost Code row expands into Base Product, LAF (Field Labor), LAS (Shop Labor), Design Labor where applicable, and Installation Materials. Each component expands again to canonical source rows; material detail retains its originating Frame Spec Section, quantity, unit, effective rate, markup, cost, and selling value.

The primary Bid view is a cohesive financial worksheet. Component rows show Grouping / Spec Code, Actual Cost Code, Description, Direct Cost, Markup %, Markup $, and Selling Value. A source line can be controlled by either markup percentage or markup dollars; clearing the line decision resumes its category default. Cost Code subtotals and a compact grand-total band reconcile the worksheet. Base and Alternate tabs remain directly beneath the page header, and an alternate renders its authoritative effective commercial estimate in the same worksheet rather than as a report below Base.

For historical comparison testing, run `.\.venv\Scripts\python.exe scripts\seed_historical_bids.py --count 240`. The deterministic archive contains clearly classified, immutable submitted reference bids spanning every supported Project Type, dated takeoffs, Cost Code value/SF, costs, and margins. It is intentionally separate from `data/projects`; the Historical drawer identifies how many controlled reference fixtures are included. Use 100–500 records and replace these fixtures with completed company evidence before treating the benchmark as production history.

## Workflow and permissions

The local role selector is an authentication abstraction for testing, not enterprise identity. Server routes enforce role authorization:

- Estimator: project/estimate inputs, quotes, takeoffs, alternates, proposal, submission.
- General Manager / President: review; restricted PCO visibility.
- Project Manager: NTP activation, contract re-estimate, PCO, SOV, provisional closeout.
- Support: authorized NTP activation and SOV work; exact business delegation remains pending.
- Systems Administrator: effective-dated configuration; administration does not confer pricing approval.

PCO markup stages are removed from responses to unauthorized roles, not merely hidden with CSS. Every server command records actor, selected role, UTC time, entity/action, prior/new value, reason, and correlation ID. The local selector is intentionally suitable for workflow testing only; deployment to a shared/multi-user host requires real authentication and operating authorization.

Proposal generation creates a dedicated immutable snapshot and one-to-one artifact binding without interrupting live autosave. Proposal History opens any snapshot across the complete estimating workspace. Its persistent banner distinguishes `Viewing Pn` from `Current Working Bid`; the first actual edit atomically creates a new live branch, retains the first edit and frozen configuration, and records the true source proposal. Chronological order does not imply ancestry. Generated proposals are never deleted: Void requires a reason and retains snapshot, artifact, ancestry, audit evidence, branching, and comparison. Proposal comparison uses two frozen snapshots and reports summary, Cost Code, source-record, and proposal-language changes.

Submission continues to create its existing immutable estimate revision and submission artifact. Activation requires NTP evidence/date and an accepted submitted revision, is idempotent for an identical retry, creates one immutable awarded snapshot, and initializes contract allocation. PM re-estimates never rewrite the award. PCOs use sequential markup stages. SOV shows under/exact/over status. Closeout is provisional because INF-4320 does not define controlled completion.

## Schema and rule documentation

- [Project JSON Schema](docs/PROJECT_SCHEMA.json)
- [Job-data interchange](docs/INTERCHANGE_SCHEMA.md)
- [Owner cost-code reference](docs/COST_CODE_REFERENCE.md)
- [Owner rate reference](docs/RATE_REFERENCE.md)
- [Unresolved commercial rules](docs/UNRESOLVED_RULES.md)

All currency inputs retain cent precision. Submitted revisions and proposal snapshots freeze raw Base data, alternate differences and calculated results, normalized estimate lines, calculation lineage, configuration ID, and totals so future Base, alternate, or configuration edits cannot change history. Stable IDs replace workbook cell coordinates.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers named calculation services, boundaries, tax/quote behavior, fringe, markups, contingency, synthetic six-band bond boundaries, alternates, atomic persistence/recovery/conflicts, permissions/redaction, immutable submission/activation, PM re-estimating, PCO, SOV, closeout status, JSON interchange, and API behavior. The INF-4320 PSSC golden outputs are represented as an acceptance fixture because the source line inputs and actual bond band schedule are not published; the test proves reconciliation metrics without pretending to reconstruct absent inputs.

## Troubleshooting

- **Port already in use:** run `./launch.ps1 -Port 8766`.
- **PowerShell blocks scripts:** use `powershell -ExecutionPolicy Bypass -File .\launch.ps1` for this launch, subject to local IT policy.
- **Dependency install fails:** confirm Python 3 is available via `py -3`, network access is available for the first install, and `.venv` is writable.
- **Blank bid:** select a used quote or add a cost-producing frame material, internal borrowed lite, equipment, or labor record; inspect Bid validation.
- **No quote $/SF:** add a matching frame/borrowed-lite code and dimensions. Total quote cost may remain valid; unit analysis is shown as unavailable.
- **Missing rate:** configure an effective rate or enter a versioned working assumption. The engine never silently substitutes a missing rate with zero.
- **Save conflict:** another tab saved first. Keep this tab open, use Export/Copy if needed, reload, and reapply intentional changes.
- **Malformed JSON:** use Open recovery, inspect backups, and restore the newest valid snapshot. Never edit the primary while the server is running.
- **Proposal PDF:** explicitly generated proposals and submitted revisions have immutable artifact identities; a historical PDF is always rendered from its frozen artifact body, never current project data.

The app intentionally excludes the erroneous SharePoint dependency, dormant GPT extension, broken Excel references, missing tool-panel/dispatcher targets, wrong reset targets, former separate ALT worksheets, and deprecated SOV PDF button.

The owner-provided `codes.xlsx` is imported read-only into `data/reference/codes.json`: 9,332 populated source rows become 9,330 normalized unique searchable records. The two duplicate normalized codes retain their alternative descriptions and source rows. Run `python scripts/import_codes.py C:\path\to\codes.xlsx` to produce a new reference payload, then create a new configuration version; existing submitted/awarded estimates remain pinned.

In **Scope and Cost Codes**, begin typing either a code or description to receive matches from this imported reference. Selecting a match normalizes the code and fills its owner-reference description. The description remains an editable project field; later calculations fill only blank descriptions and never replace project-specific wording.

Submitted proposal artifacts provide **Preview PDF** and **Download PDF** actions, reproducing the supported Excel proposal-export outcome without depending on Excel or macros. Filenames include the project identifier and frozen bid version; the PDF response also carries the immutable artifact ID.

On first startup the app creates **MW Bid Platform Test Project** (`TEST-4320`) with sample codes, competing quotes, a canonical inherited ALT1, frame takeoff, equipment, borrowed-lite, field labor, and shop labor. It is an ordinary persistent project: edit it freely, duplicate it for another scenario, and run it through submission/activation. Startup never overwrites it after creation.
