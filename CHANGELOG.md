# Changelog

All notable Murphy Window Bid Platform changes are recorded here. Release numbers follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- MAJOR changes are intentionally incompatible application-contract changes.
- MINOR changes add backwards-compatible product capability.
- PATCH changes correct behavior without adding an incompatible contract.

Application release versions are independent from project schema versions, interchange versions, configuration revisions, generator versions, and a project's `Bmajor.minor.patch` bid lifecycle. Git history begins on August 19, 2026; these initial entries are backdated to the corresponding recoverable commits.

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
