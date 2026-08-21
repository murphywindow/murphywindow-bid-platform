# Changelog

All notable Murphy Window Bid Platform changes are recorded here. Release numbers follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- MAJOR changes are intentionally incompatible application-contract changes.
- MINOR changes add backwards-compatible product capability.
- PATCH changes correct behavior without adding an incompatible contract.

Application release versions are independent from project schema versions, interchange versions, configuration revisions, generator versions, and a project's `Bmajor.minor.patch` bid lifecycle. Git history begins on August 19, 2026; these initial entries are backdated to the corresponding recoverable commits.

## Unreleased

### Changed

- Clamped keyboard-driven table alignment to the exact horizontal scroll range so maintaining focused-column visibility cannot create blank space beyond the first or last column.
- Recognized both Base and Alternate Frame DOM structures when revealing a keyboard-focused column, ensuring the whole Base column clears the frozen Qty overlay.
- Deferred the final keyboard-focus table alignment until after the browser completes native Tab focus behavior, preventing left-tabbed cells from being pulled back underneath frozen columns.
- Kept the horizontally scrolled table synchronized with keyboard focus so Tab and arrow navigation reveal the entire active cell without letting it hide behind frozen Frame columns or the sticky Actions column.
- Removed the residual rounded left border below the final Base Frame row by targeting the nested table wrapper correctly; the same correction now applies transient scrollbar behavior consistently to Base and Alternates.
- Fixed Installation Material formula editing in Base and Alternates so basis, operator, operand, unit, and rate changes persist without stale rerenders; added an immediate quantity/cost preview with an explicit Total; and optimized the compact table to remain scroll-free.
- Preserved the active page and numbered Alternate in the browser URL across application refreshes and browser reloads, and hid the Home workspace until startup routing resolves to eliminate the initial Home flash.
- Removed the added/changed/removed accent rail from Alternate Frame sections so semantic row color carries state without shifting the section's left edge.
- Separated Frame totals from the table into a borderless measured rail, preserving the last Frame row as the table edge while keeping totals aligned and preventing overlap behind frozen columns during horizontal scrolling.
- Made Frame horizontal scrollbars transient: they remain hidden at rest, appear while the grid is hovered or moving horizontally, and fade back out after scrolling stops.
- Corrected Base Frame totals-rail discovery and added a CSS column fallback so totals always render as one aligned horizontal row, including before measured widths are applied.
- Restricted the Frame outline to the actual table so it ends at the last Frame row, and limited the horizontal scrollbar thumb to active scrolling or direct thumb hover instead of general table hover.
- Matched the Frame table's lower corner geometry to its rounded upper corners while retaining the normal unshaded body-row surface.
- Collapsed the Frame scrollbar entirely while idle, restoring its thin track only during horizontal movement or while the pointer is in the scrollbar zone, including Firefox and Chromium-specific behavior.
- Replaced the Frame table outline with cell-owned perimeter borders so the left edge terminates precisely at the final Frame row and cannot continue beside the separate totals rail.
- Added a confirmed Delete section action to the Spec Section pencil dialog, with Base deletion and Alternate-aware remove/discard behavior.
- Reworked the Bid workspace into a compact nine-column Cost Code summary with zero-value groups omitted, source components disclosed on demand, and no horizontal worksheet scrolling.
- Added a dense, data-driven, single-sheet Bid Review PDF for Base and Alternates, including commercial totals, effective configuration, Cost Code/source lineage, takeoff inputs, Installation Material formulas, and validation.
- Restored numbered Alternate context on Quotes and routed Alternate Quotes through the shared Frame-style semantic table treatment without status pills.
- Made empty Frame drafts disappear when the estimator clicks away, while populated drafts continue through the normal persistence workflow.
- Allowed Installation Material formula units to be changed or added, kept operator changes stable through recalculation, and removed visible formula-override pills.
- Inverted the vertical bid-history scale so lower, more aggressive values appear at the bottom and higher, more conservative values appear at the top.
- Compacted Installation Material formula tables with narrower columns and space-saving two-line headers in Base and Alternates.
- Standardized displayed square-foot units on lowercase `ft²` and `$/ft²`, and removed dotted underlines from tooltip-enabled text and controls.
- Vertically centered headers, values, entry controls, and row actions across shared Base, Alternate, proposal, and subtotal table cells.
- Narrowed the Frame Caulk Passes, Head / Sill, and Install Mats columns in Base and Alternates, using compact two-line headings while retaining manual resizing.
- Fixed the sticky Frame Qty column to the Mark column's measured width so their divider remains stationary during horizontal scrolling and resizing.
- Replaced the long Frame Spec Section stack with compact section tabs in Base and Alternates, keeping one section workspace visible at a time.
- Limited Frame scenario-tab labels to Base and numbered Alternates, keeping optional Alternate names and descriptions out of the tab strip.
- Reduced Spec Section tabs to Cost Codes only and placed New Section immediately after the rightmost Spec Section tab.
- Removed the redundant Base/Alternate takeoff summary header above the Frame Spec Section tabs.
- Removed the duplicate Frame Spec Section Cost Code dropdown; new sections now require a Cost Code before creation, while the active tab provides a compact edit action for later changes.
- Added live-editable Installation Material formulas in Base and Alternates using a measured basis (including `ft²`), an operator, and a value, with immediate quantity/cost previews and one-click Revert to the inherited controlled formula.
- Added per-row removal controls for controlled and project-specific section Installation Materials, with dependency confirmation and immutable-history protection.
- Centered text within Frame cell editors and readouts themselves, including textareas, selects, calculated outputs, material selectors, and Actions controls.
- Pinned a compact Base/Alternate live-price strip in the application header, isolated it from save-status reflow, and added direction-aware green/red rolling-number updates with reduced-motion support.
- Standardized calculated dollar totals outside tables on the Proposal Amount display typeface while preserving the interface font for entry fields and table values.
- Refined Base and Alternate Frame worksheets with narrower resizable columns, stable sticky dividers and Actions headers, uniform cell borders, semantic row colors, expandable text cells, and reliable page scrolling.
- Kept Frame column-resize targets invisible and vertically centered all header/body cell content so drag affordances no longer resemble thick table borders.
- Added a mixed-state All checkbox to Base and Alternate frame-line Installation Material pickers for one-action selection or clearing.
- Limited missing-quantity strike-throughs to dimension-started Frame rows and deferred the default three caulking passes until perimeter becomes calculable.
- Simplified Base and Alternate Installation Materials into the same compact calculation layout and corrected irregular material-unit plurals.
- Made Frame Cost Code selectors fit the widest managed code and exposed inline Cost Code creation without leaving Frame takeoff.
- Prevented dialog Cancel actions from triggering required-field validation.
- Replaced automatic trailing editable rows with explicit, browser-only Add Row drafts across shared tables; Enter and rectangular paste create only the requested rows.
- Made Frame headers horizontal and sticky, kept identity/action columns available during horizontal work, moved missing-quantity acknowledgement beside Qty, and shortened Frame Cost Code selection to the code with its description alongside.
- Collapsed Base Installation Materials to one effective editable Rate with Controlled/Override provenance and a Revert action; the configuration table no longer exposes a Cost Code column.
- Unified live estimating tables around shared spacing, divider, surface, header, row, input, focus, calculated, inherited, warning, and action-control tokens; refined Frame section composition and made the compact Installation Materials table terminate at its content width.
- Consolidated the application shell and estimating surfaces onto the documented exact `--ui-*` visual system, including 52px/15rem shell geometry, three control sizes, 28px data rows, the eight-column Frame header, and exact Frame and compact-material column budgets.
- Contained wide estimating worksheets within the padded workspace so horizontal overflow remains inside each table wrapper instead of extending beyond the body margins.
- Refined the Frame section header with quieter tooltip affordances, stronger identity/metric alignment, a contained History instrument, and a consistent action-cell divider.
- Changed the Frame header’s per-SF metric to quote-inclusive Cost Code selling value per SF, matching the current value used by its historical comparison.

## [2.3.0] - 2026-08-20

### Added

- Shared stable three-state sorting and a compact visual language across editable, read-only, and hierarchical live tables, with browser-only persisted sort state and Shift-click multi-column sorting.
- Optional alternate names with deterministic `Alternate n` / `Alternate n — Name` labels and stable internal IDs/keys.
- Separate Grouping / Spec Code and Actual Cost Code classification for Installation Materials, including full-reference selection and dual-code Bid lineage.
- Source-line Markup % or Markup $ authority for Base and alternates, with mode switching, clearing, audit provenance, inheritance, and zero-cost handling.

### Changed

- Consolidated Base Quotes into one continuous table with Cost Code first and one trailing working row.
- Advanced project/job-data schema to 1.3.0 with an idempotent migration for optional alternate names and typed markup authority.
- Scope dependency cascades continue to follow grouping codes; nested Actual Cost Code classification never removes a containing Frame Spec Section.

## [2.2.0] - 2026-08-20

### Changed

- Replaced the expandable Cost Code card/detail presentation with a cohesive worksheet showing component rows, Cost Code subtotals, and a compact grand total.
- Added explicit Direct Cost, Markup Percentage, Markup Dollars, Selling Value, SF, and $/SF columns with fixed numeric alignment and desktop horizontal scrolling.
- Base Product, Installation Materials, LAF, LAS, Design Labor, and other meaningful components now appear without expanding the Cost Code; canonical source detail remains on demand.
- Historical pricing is a compact subtotal indicator with full evidence retained in the existing drawer.
- Base/ALT navigation now consistently follows the page header across Bid and supported takeoff modules, preserving scroll position during switches.
- Selecting an ALT renders its authoritative calculated effective estimate in the same Bid worksheet and shows its net delta and compact Scope of Change near the tabs.

## [2.1.0] - 2026-08-20

### Added

- Project-specific Frame Spec Section Installation Materials using canonical basis, factor, controlled-reference/project-rate, applicability, Cost Code, snapshot, alternate, comparison, and audit behavior.
- Dependency-aware custom-material removal and dynamic per-frame material selection.
- Bid component hierarchy for Base Product, LAF, LAS, Design Labor, and Installation Materials with source-level disclosure and Frame-section identity.

### Changed

- Reduced non-essential header, card, module, empty-state, summary, and table spacing while preserving readable controls and keyboard behavior.
- Added structural numeric column widths, tabular alignment, responsive summary wrapping, and horizontal overflow contracts to prevent financial, percentage, SF, and $/SF collisions.
- Proposal comparison now reports project-specific Installation Material changes through business fields instead of structural object coercion.

## [2.0.0] - 2026-08-20

### Added

- Canonical Base-plus-delta alternates with inherited records, explicit Added/Removed/Modified operations, retained overrides, Base-change conflict review, and reset-to-inherit.
- Authoritative effective-ALT-minus-Base calculation by Cost Code and source category, automatic Add/Deduct/Zero classification, downstream frame/material/labor effects, and deterministic Scope of Change.
- Alternate tabs across estimating modules, customer descriptions, Proposal/Bid detail, frozen snapshot and comparison support, and a schema 1.1-to-1.2 migration.
- Modernized commercial proposal PDF modeled on the established Murphy form: compact company/project tables, scope sections, written price statement, alternates, acceptance signatures, and immutable artifact footer.

### Removed

- Active prefixed `ALT1-` through `ALT4-` takeoffs and Bid inclusion checkboxes. Migrated legacy rows remain preserved as explicit ALT-only additions; immutable history remains untouched.

## [1.3.0] - 2026-08-20

### Added

- Dedicated immutable proposal snapshot storage, deterministic commercial-state fingerprints, editable Proposal Names, permanent `P1` sequence identities, ancestry, branch sources, and one-to-one artifact references.
- Whole-workspace historical proposal mode with silent first-edit branching, mutation isolation, frozen effective configuration, void-with-reason, compact Proposal History, and proposal-to-proposal comparison.
- Explicit proposal history/read/generate/branch/void/compare/artifact/ancestry APIs and automated lifecycle coverage.

### Changed

- Proposal chronology and ancestry are independent; generating from an older proposal records the actual source rather than the previously generated proposal.
- Legacy submissions, estimate revisions, awards, and artifacts remain unchanged. Existing records without provable ancestry retain null/unknown ancestry instead of receiving invented relationships.

## [1.2.0] - 2026-08-19

### Added

- Schema 1.1 migration and reusable JSON master-data/search infrastructure.
- Immutable configuration `cfg-2026-08-19-v5`, retaining prior controlled rates while adding schema 1.1 policy metadata and explicit unavailable/inherited commercial states.
- Shared stable editable-table, trailing-draft-row, keyboard, autocomplete, and Excel-paste behavior.
- Controlled project values, protected custom cost codes, dependency-aware cascade removal, structured address search, quote adjustments and selection provenance, rate overrides, Labor scheduling/source linkage, and per-code Bid summaries.
- Explicit software-version metadata and release-history policy.

### Changed

- Autosave updates authoritative state without replacing the active page or dropping focus.
- Quote comparison, submission validation, and Bid aggregation now follow the owner-confirmed web estimating contract while retaining legacy source data.
- INF-4320 and repository documentation distinguish confirmed web behavior from observed workbook behavior and unresolved commercial policy.

### Fixed

- Blank working rows no longer enter persistence, audit, calculation, or bid-version history.
- Missing quantities, invalid controlled values, stale Labor, and unavailable required rates cannot silently pass submission.

## [1.1.1] - 2026-08-19

Source commit: `0f68f05`

### Fixed

- Activated the deliberately plain functional HTML interface as the actual Frame Takeoff presentation.
- Kept the preserved polished presentation dormant and recoverable instead of deleting it.

## [1.1.0] - 2026-08-19

Source commit: `eaea060`

### Changed

- Temporarily simplified Frame Takeoff presentation so its sections, editable frame data, calculations, installation materials, and totals could be evaluated without the polished product layer.
- Documented the restoration boundary for the preserved polished implementation.

## [1.0.0] - 2026-08-19

Source commit and tag: `ef136ba`, `frame-takeoff-polished-baseline-2026-08-19`

### Added

- Established the first recoverable software baseline for the FastAPI, vanilla JavaScript, HTML/CSS, and JSON-backed bid-to-closeout application.
- Preserved the polished Frame Takeoff implementation in source control.
