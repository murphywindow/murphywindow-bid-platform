# Changelog

All notable Murphy Window Bid Platform changes are recorded here. Release numbers follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- MAJOR changes are intentionally incompatible application-contract changes.
- MINOR changes add backwards-compatible product capability.
- PATCH changes correct behavior without adding an incompatible contract.

Application release versions are independent from project schema versions, interchange versions, configuration revisions, generator versions, and a project's `Bmajor.minor.patch` bid lifecycle. Git history begins on August 19, 2026; these initial entries are backdated to the corresponding recoverable commits.

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
