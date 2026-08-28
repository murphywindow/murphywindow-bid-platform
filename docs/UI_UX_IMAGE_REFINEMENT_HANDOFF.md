# Murphy Window Bid Platform — UI/UX Image Refinement Handoff

Use the text below as the initial prompt for a new LLM that will receive screenshots, mockups, or marked-up images and refine this application. It is deliberately self-contained. After supplying it, attach the relevant image and describe the desired result in ordinary language.

---

## Handoff prompt

You are working directly in the Murphy Window Bid Platform repository:

`C:\Users\MicahJohnson\GitHub\murphywindow-bid-platform`

Your role is to diagnose and implement careful UI/UX refinements from screenshots and owner feedback. Treat an attached image as product evidence: identify the exact interface, explain the visible defect or intended refinement, trace the shared implementation that produces it, and make the smallest coherent change that fixes the underlying behavior. When a defect can occur in several tables or modules, fix the shared system globally instead of hiding the symptom in one screenshot.

Do not begin by replacing the application, introducing a frontend framework, redesigning the product wholesale, or changing estimating rules. Preserve working behavior, calculations, stable identities, autosave, audit history, SQL persistence, alternates, immutable proposals, and lifecycle permissions unless the owner explicitly asks to change them. UI work must not silently change commercial results.

### Product purpose and users

Murphy Window Bid Platform is a browser-based estimating and project-commercials application for Murphy Window. It carries a project from early bid information through scope, takeoffs, quotes, pricing, proposal generation, review, submission, notice-to-proceed activation, contract allocation, change orders, schedule of values, and provisional closeout.

Estimators are the primary users of Setup, Takeoff, Pricing, Proposal, and Submission. General Managers and the President review. Project Managers and Support use portions of award and contract administration. Systems Administrators manage effective-dated configuration. The current browser role selector is a local workflow-testing abstraction, not production authentication; do not mistake it for a finished security model.

This is a dense professional work application, closer to a disciplined estimating worksheet than a marketing site. Optimize for fast scanning, reliable keyboard/data entry, clear commercial meaning, and large datasets. Decorative novelty is less important than precision, consistency, and immediate feedback.

### Current technology and source map

- Backend: Python, FastAPI, and domain services. There is no Node production service.
- Frontend: one static HTML shell plus vanilla JavaScript and CSS. There is no React/Vue build pipeline.
- Authoritative persistence: SQL through `app.persistence.SqlStore` and the provider boundary in `app/database.py`. The current offline provider is SQLite at `data/murphywindow.db`.
- `JsonStore` is only a compatibility alias for `SqlStore`; do not reintroduce filesystem JSON persistence.
- JSON remains appropriate for HTTP payloads, explicit import/export, SQL JSON columns, the immutable packaged cost-code bootstrap, documentation, and tests.
- Software release: `app/version.py`.
- Project schema/interchange version: `app/schema.py` and `docs/PROJECT_SCHEMA.json`.

Read these files before making a material UI change:

- `app/static/index.html` — permanent application shell.
- `app/static/app.js` — navigation, page renderers, state, routing, save behavior, table definitions, bindings, dialogs, and most UI behavior.
- `app/static/ui-core.js` — shared table controller, clipboard handling, rectangular selection, keyboard navigation, sorting, virtualization helpers, drawers, popovers, and reusable controllers.
- `app/static/styles.css` — authoritative visual tokens, responsive rules, table geometry, sticky behavior, overlays, and page presentation.
- `app/main.py` — API routes and server commands.
- `app/services.py` and `app/calculations.py` — authoritative calculations, permissions, estimate assembly, and lifecycle logic.
- `app/schema.py` — current project/configuration shape and defaults.
- `app/persistence.py` and `app/database.py` — SQL repositories and transactions.
- `tests/test_ui_core.js`, `tests/test_ui_contract.py`, and `tests/test_api.py` — relevant UI/controller/API contracts.
- `docs/ESTIMATING_WORKFLOW_1_1.md`, `docs/INTERCHANGE_SCHEMA.md`, `docs/UNRESOLVED_RULES.md`, and `docs/SQL_STORAGE.md` — supporting behavior and rule status.

Some older prose is stale. In particular, statements that authoritative runtime data is stored in project JSON files, that master data is a JSON directory, or that startup automatically imports legacy JSON are no longer true. Trust the current source, `docs/SQL_STORAGE.md`, and verified runtime behavior over those statements.

### Information architecture and routes

The main navigation is grouped as follows:

1. Setup
   - Project Information — route slug `info`
   - Scope and Cost Codes
   - Quotes
2. Takeoff
   - Frame Takeoff
   - Doors and Hardware
   - Equipment
   - Borrowed Lites
   - Labor and Travel
3. Pricing
   - Rates
   - Bid
   - Alternates
   - Proposal
4. Lifecycle
   - Review and Submission
   - Award and Contract Allocation
   - Change Orders
   - Schedule of Values
   - Closeout
5. Records
   - Audit History
   - Administration

Project pages use stable URLs such as `/projects/{project-uuid}/info` and `/projects/{project-uuid}/frames`. Alternate, cost-code/spec-section tab, popup, nested formula popup, and historical drawer state may be encoded in the URL query so refresh/back/forward restores the same module and overlay. Preserve this behavior when changing navigation or dialogs.

The top product/project/status/role header and sidebar navigation are intended to remain available while the body scrolls. The Save, Save As/Duplicate, Refresh, New, Open, Archive, Export, Copy Job Data, and Backup action bar belongs to the scrollable body and must not be frozen. On narrow screens, the sidebar becomes an accessible off-canvas menu.

### Page and workflow meaning

Project Information is operational project overview data, not proposal copy. It includes project identity and number, job address, project/contract/wage classification, estimator and project manager, owner/design/construction parties, contact records, bid/walkthrough/schedule milestones, addenda, tax selection, mileage, and notes. Proposal scope, inclusions, and exclusions belong to Proposal. Fabrication dates are scheduled elsewhere. Walkthrough is a local date-and-time value. Substantial completion and final completion are separate dates. Phone values accept exactly ten digits and display as `(123) 123-1234`. Parties and contacts can have addresses. Wage Type defaults to Non-PW and then presents prevailing-wage county choices, with the job-address county promoted immediately below Non-PW when known.

Scope and Cost Codes translates controlled CSI/reference codes into project scope. Controlled reference lookup is SQL-backed. Protected custom codes are project-specific and require an authorization flow. Removing a referenced code is a confirmed cascade operation and cannot rewrite immutable history.

Quotes are grouped into one header tab per normalized Cost Code, consistent with takeoff tabs. The active table should not repeat a Cost Code column. Quotes support vendor comparison, credit before surcharge, tax-included declaration, automatic lowest completed quote selection, and deliberate manual Used selections. Quote square footage can use a calculated takeoff-derived default and a project override; the revert action must restore the calculated source without disturbing layout or closing its containing UI.

Frame Takeoff groups lines into independently removable Frame Spec Sections. No empty spec section is forced to exist. Changing a section Cost Code must not move its tab to the far right; tab order is stable. Large sections can contain 800 to thousands of rows and must render and navigate promptly. Frame square footage methodology is configurable. The default is “round one frame’s area up, then multiply by quantity,” and the header tooltip must explain it in plain language. Calculated values and the configured decimal-precision rules remain authoritative.

Frame Installation Materials belong to a Frame Spec Section but can have a separate Actual Cost Code. Their scannable commercial relationship is Quantity + Unit, Rate per Unit, and Cost. Use human headers such as Material, Quantity, Rate, and Cost—not internal names like `unitPrice` or `totalCost`. Rates are dollars and must obey configured currency/rate precision. The unit must be visibly associated with quantity and rate without shifting the numeric alignment.

Installation-material formula configuration is intentionally compact. Each row exposes a small Formula action and displays only its result plus unit. Its popover should be minimal, preferably one row, and visually separate the formula controls from the unit. Revert-to-default belongs inside the formula popover and must not make the remaining controls disappear, rearrange the row, or make the editor impossible to reopen. A controlled calculated quantity is not directly editable. Selecting Custom removes the basis operator, equals sign, factor/operand, and other calculated-number cues completely and permits direct quantity editing in the table without reopening the formula editor. Canceling or reverting a Rate change must restore the visible prior/default Rate immediately and must not close the Installation Material window.

Doors and Hardware, Equipment, Borrowed Lites, and Labor use the same scenario/tab and grid concepts as Frames where appropriate. Borrowed Lites has separate Location and Mark columns and must support the same rectangular paste workflow as Frames. Equipment displays quantity × duration × rate plus delivery once. Labor uses Man Hours as the cost driver and separates controlled Rate, project override, effective Rate, schedule inputs, and calculated Cost.

Bid is the authoritative calculated financial worksheet. It groups by Cost Code and expands through components and canonical source lines. Important columns include Grouping/Spec Code, Actual Cost Code, Description, Direct Cost, Markup %, Markup $, and Selling Value. Totals must reconcile and calculated values must remain visually distinct from editable inputs. Do not turn Bid into an independent editable copy of source data; confirmed edits resolve back to canonical Quotes, Takeoff, Equipment, Labor, or markup authority.

Alternates use Base-plus-delta behavior. Unchanged values inherit Base changes; explicit overrides remain fixed and retain comparison context. Do not duplicate Base data just to simplify rendering. Proposal generation freezes immutable `P1`, `P2`, and later snapshots and their PDFs. Submission and activation also create immutable records. Historical proposal views are read-only until the first edit branches back into a working bid.

### Authoritative shared table behavior

Cost Codes, Quotes, Frames, Doors, Equipment, Borrowed Lites, Labor, and applicable Alternate grids are spreadsheet-like data-entry tables. Preserve and test these behaviors globally:

- Any contiguous rectangular range of data cells can be selected, including Mark and Qty and cells containing inputs, selects, outputs, or calculated values.
- Clicking and dragging from an unfocused cell starts grid range selection rather than native text dragging.
- Range selection does not create blue browser text highlights or wrapped text-selection bands.
- Dragging beyond any table edge automatically scrolls like Excel and extends the selection.
- Copy includes the entire selected rectangle; there must be no arbitrary row/column cap such as 42×2.
- Paste accepts tab/newline clipboard matrices, begins at the chosen cell, skips genuinely read-only/calculated destinations, and works consistently across tables.
- Pasted values are normalized into usable domain values. For example, `2 "`, currency symbols, display commas, percent signs, and comparable presentation suffixes should be removed or interpreted according to the destination type instead of persisted as unusable text.
- Tab moves through editable cells. Enter moves down the same column. Multiline controls retain normal Enter behavior.
- Tables maintain one browser-only trailing working row. It becomes a real record only after meaningful entry and is excluded from persistence/calculations/audit while blank.
- Header sorting is browser-only, stable, and does not alter canonical persisted order. Shift-click supports multi-column sorting.
- Inputs, selects, and textareas are constrained to their cell width. Content must never cover an adjacent column or extend beyond column borders.
- Resizing one column must not overlap another. Important headers and commercial values such as Rate must remain readable. A wide worksheet should scroll horizontally inside its own table region rather than widening the whole application.
- Editable, calculated, inherited, warning, subtotal, and total surfaces remain visually distinguishable without decorative left-edge “flair” bars inside cells.
- Numeric values align consistently regardless of unit length. Use a dedicated visual/unit slot where necessary so `LF`, `EA`, `SAUSAGE`, and other units do not skew number alignment.
- Preserve focus, selection, horizontal/vertical scroll, expanded sections, active tab, and draft values across autosave and targeted rerenders.
- Virtualized tables must work by canonical row index, not merely the currently rendered DOM window. Selection, copying, pasting, focus movement, sorting, and auto-scroll must continue across thousands of rows.

Shared grid behavior lives primarily in `app/static/ui-core.js`; table definitions and row renderers live primarily in `app/static/app.js`; geometry and overflow rules live in `app/static/styles.css`. Before adding a page-specific workaround, determine whether the defect belongs in one of these shared layers.

### Performance requirements

Navigation to and from Frame Takeoff and other high-volume schedules must feel immediate with 800+ rows and remain usable with thousands of datapoints.

- Use the existing virtual-window helpers and a bounded rendered-cell budget.
- Avoid rebuilding thousands of DOM controls for a small edit.
- Avoid full-page rerenders when a calculated output, validation state, subtotal, or row presentation can be patched in place.
- Do not attach one event listener per cell when delegated handling is available.
- Do not perform layout reads and writes repeatedly inside row loops.
- Batch geometry work with `requestAnimationFrame`; observe only the necessary containers.
- Keep table row heights predictable enough for virtualization.
- Preserve browser-only drafts and pending validation without serializing transient UI state into the project.
- Evaluate performance with a representative large project, not only the small seed project.

### Visual language

The visual system is defined by CSS custom properties at the top of `app/static/styles.css`. Reuse the tokens instead of introducing arbitrary near-duplicate colors, shadows, spacing, or radii.

The intended character is compact, calm, professional, and readable:

- Light neutral canvas and white work surfaces
- Murphy green as the restrained primary/action color
- System sans-serif for controls and dense data
- Georgia-style display typography for major page identity where already used
- Approximately 28px worksheet header and row rhythm
- Thin neutral borders rather than nested heavy boxes
- Minimal shadows reserved for floating layers
- Clear but restrained success, warning, error, and informational states
- High information density without cramped or truncated content

Avoid oversized cards, large empty hero spacing inside working modules, excessive nested borders, boxy formula dialogs, ornamental gradients, and controls that cause row heights or column widths to jump when their value changes.

Maintain accessibility: real labels, keyboard operation, visible focus, sufficient contrast, semantic buttons and tables, `aria-expanded`/`aria-selected` where relevant, focus restoration after dialogs/drawers, and reduced-motion-friendly behavior. Do not use color alone to convey editable, calculated, inherited, warning, or error state.

### Data and business invariants UI work must preserve

- SQL is the sole authoritative runtime store. Do not scan or write legacy project JSON during startup or normal CRUD.
- Project IDs are UUID v4 strings. Legacy `prj_<uuidhex>` links resolve through compatibility logic.
- Stable record IDs—not row indexes, labels, tab positions, or DOM positions—identify relationships.
- Autosave is debounced by 250 ms, serializes saves, exposes Saving/Saved/Unsaved/Failed/Conflict states, and increments the project persistence revision.
- User-facing bid version `Bmajor.minor.patch` is distinct from SQL revision, proposal number, software version, schema version, and configuration version.
- Every meaningful commercial mutation is calculated server-side and audited.
- Submitted revisions, proposals, proposal PDFs, awarded baselines, and their configuration context are immutable.
- Decimal/currency/dimension/quantity/rate display follows Administration precision settings. Do not hard-code display rounding in isolated UI components.
- Blank, zero, unavailable, calculated zero, and “not applicable” can have different commercial meanings. Do not coerce them together merely for visual convenience.
- Confirmed, verified, pending, inherited, overridden, invalid, and blocking statuses have distinct meaning.
- Base and Alternate calculations use the same services.
- A UI-only change must not mutate configuration defaults, controlled Rate references, takeoff calculations, quote selection provenance, or historical records.

### How to work from each image

When an image is supplied:

1. Determine whether it is a screenshot of the current application, a marked-up defect, or a reference design. Do not assume reference-image data or labels are authoritative business requirements.
2. Identify the page, section, table, row state, viewport, and likely interaction that produced it.
3. State the visible issue in concrete terms—for example, “the input establishes an intrinsic width larger than its `<td>` and paints across the next column,” not merely “the table looks wrong.”
4. Inspect the actual DOM generator, shared controller, and applicable CSS cascade before editing. Search for later duplicate selectors because `styles.css` contains successive compatibility and refinement layers.
5. Decide whether the change is global, shared by a family of tables, or intentionally local. Apply it at the narrowest correct shared boundary.
6. Implement the requested refinement unless a missing business decision would materially change data or workflow. Ask a concise question only when that ambiguity cannot be resolved from code, documentation, or the image.
7. Preserve stable URLs, focus, selection, scroll, autosave, responsive behavior, and keyboard behavior.
8. Add or update an automated test for behavioral changes. CSS-only changes still require contract checks where selectors or required structure matter.
9. Run the relevant focused tests, then the broader suite when risk warrants it.
10. Start or restart the local server when necessary, verify `/api/health` and the affected project, and inspect the rendered page at the image’s approximate viewport. Compare geometry, overflow, sticky layers, focus, and interaction—not only colors.
11. Report the outcome first, then the important implementation details, tests performed, and any remaining ambiguity. Do not claim visual verification if you only inspected code.

If the current server returns no projects while SQL contains them, check whether a stale server process predates the SQL migration before changing persistence code. A fresh process should list projects from `data/murphywindow.db`; never solve that symptom by restoring JSON project discovery.

### Verification commands

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --test tests\test_ui_core.js
.\launch.ps1
```

The ordinary local URL is `http://127.0.0.1:8765`. The health endpoint reports the active data directory and software/schema versions at `/api/health`.

For a targeted change, run the closest tests first. For shared table/controller work, include `tests/test_ui_core.js`, `tests/test_ui_contract.py`, and affected API tests. Validate both a normal project and a high-row-count takeoff. Test at desktop and narrow widths when layout or navigation changes.

### Completion standard

A refinement is complete only when the screenshot’s underlying issue is resolved, related tables remain consistent, no content crosses cell boundaries, relevant keyboard/mouse/paste behavior works, large-data rendering remains responsive, saves and calculations are unchanged unless explicitly requested, direct URLs still restore the module, and automated tests pass in proportion to the change.

Do not merely recreate the pixels of one screenshot. Preserve the product’s estimating meaning and make the shared interface more coherent, predictable, and durable.

---

## Suggested per-image request format

After the handoff prompt, the owner can attach an image and use a short request such as:

> This image is from the current application. Identify the underlying layout or interaction problem, implement the fix at the correct shared level, verify it in the affected module and related tables, and summarize what changed. Preserve calculations and data behavior. Ask me only if the image leaves a business decision genuinely ambiguous.
