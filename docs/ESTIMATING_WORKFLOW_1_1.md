# Estimating workflow and data contract 1.1

This document records confirmed web-application behavior introduced by project schema 1.1. It supplements INF-4320's observed workbook evidence. Where an item remains commercially unresolved, the application reports it as unavailable or blocking instead of inventing a value.

## Project and reusable records

- Project Type is restricted to the sixteen approved construction/scope combinations defined in `app.schema.PROJECT_TYPES`.
- Contract Type is restricted to `Bid to CM/GC` or `Bid as GC`.
- Wage Type is stored in the canonical `wage_type` field; `Non-PW` and `PW` are deliberate choices.
- Bid Due Date is a local wall-clock date and time. Save, reopen, export, and snapshot operations do not apply a timezone conversion.
- Migrated unsupported controlled values are preserved with a `legacy_unsupported` status. They are not silently rewritten and must be deliberately replaced before submission.
- Address search reuses the mileage geocoder abstraction. Manual entry remains authoritative when lookup is unavailable, and failed or stale searches never erase entered fields.
- Organizations, person-at-organization contacts, estimators, plan sources, and custom contact roles are indexed in the JSON master-data directory. Search supports canonical case, aliases, prefix/substring matching, and tolerant fuzzy matching. Archived project history remains discoverable after indexing. A reusable-field fingerprint reindexes an existing project only when its reusable history changes, so later vendors or contacts become suggestions without revision churn on every save.
- Editing a selected contact can remain a project-only change or be sent as a deliberate reusable-master update. A master update changes future suggestions and never rewrites historical projects.

## Shared editable-table contract

Cost Codes, Quotes, Frames, Doors, Equipment, Borrowed Lites, and Labor use one delegated table controller and stable row identifiers. Tab moves across editable columns, and Enter moves down the same column. Enter remains ordinary text input in multiline controls.

Each table presents exactly one browser-only trailing working row. It becomes a canonical record only after meaningful input, then a new working row appears. Working rows are excluded from persistence, calculations, audit, and bid-version increments.

Live data tables use one compact visual language and browser-only sorting. A header cycles ascending, descending, then canonical order; Shift-click composes a stable multi-column sort. Blank values remain after populated values, working rows remain last, and sorting never changes persisted row order, quote selection, audit, or Bid version. Hierarchical Bid rows move as complete Cost Code groups so source details and subtotals cannot detach.

A rectangular tab/newline clipboard paste begins at the focused editable cell. The controller uses each table's explicit editable-column map and skips calculated/read-only columns. Valid cells are accepted together; invalid controlled values remain in the pending browser/project validation buffer and do not become authoritative codes. One paste correlation identifier ties its field-level audit records together.

Autosave patches the saved revision and calculated output into the existing interface. It does not replace the page or whole table, so focused input, selection, scroll, and expansion state survive a save.

## Cost codes and quote comparison

Ordinary cost codes resolve against the pinned controlled reference. An exceptional custom code requires the dedicated server-side credential verifier; its secret is environment/local-file backed, hash verified, excluded from source control, and never returned or audited. Custom records stay visibly marked and do not alter the controlled reference.

Removing a referenced code is a deliberate cascade command. A dry run returns dependencies; declining preserves everything. Confirming removes active dependent detail, audits affected identities under one correlation identifier, and recalculates. Immutable submitted and awarded snapshots are never rewritten.

Quote grouping is the full normalized Cost Code. Historical `group_id` is retained as dormant migration evidence. Base Quotes are presented in one continuous table with Cost Code as the first editable column and one trailing working row for the whole table. Changing a Quote's grouping code preserves stable identity and manual Used provenance; it does not depend on the current visual sort.

Quote adjustment order is:

1. start with base price;
2. subtract a dollar credit or a percentage of the original base price;
3. calculate a dollar surcharge or a percentage of the post-credit subtotal;
4. add the surcharge.

Negative surcharge is invalid. Lineage retains the base, entered types/values, extended credit and surcharge, intermediate subtotal, and final adjusted amount. Exact Decimal intermediates are retained and the currency extension is rounded once to cents.

One completed quote is selected automatically. With several completed quotes, the lowest final adjusted pre-tax quote is automatic until an estimator changes a Used checkbox. That action changes the code to manual selection, where zero, one, or several Used quotes are preserved. All Used quotes add into Base Product. Migrated Used choices are classified as legacy/manual so recalculation cannot silently replace them.

Quote square footage is editable. A blank value defaults from combined matching Frame sections only and is not overwritten after an estimator supplies a value. Bid square footage is independent and uses Frame plus Borrowed Lite area exactly once per cost code.

## Frame, Door, Equipment, and rate exceptions

Frame commercial formulas and dimension normalization remain unchanged. Frame and Door quantities have no automatic value. A meaningful row with blank or zero quantity is warning/blocking unless that specific line has a retained, audited acknowledgement; acknowledged rows remain visibly exceptional.

Installation-material and Labor rate records retain controlled rate, project override, effective rate, configuration/source identity, and override provenance separately. A project override never edits the pinned configuration. Clearing it returns to the current applicable controlled rate.

A Frame Spec Section Cost Code is the Grouping / Spec Code. Each project-specific Installation Material separately stores an Actual Cost Code chosen from the full controlled reference, even when that code is not in project scope. Bid groups the material under its section while exposing both codes and the material description. Scope removal dependency checks follow grouping only: an Actual Cost Code reference alone never deletes the containing section or material.

Equipment extension remains `quantity × duration × rate + delivery`, with delivery applied once. The displayed subtotal is the sum of pre-tax line extensions. Tax is applied separately in Bid and honors the line's taxable declaration.

## Labor

The application derives a unique Labor candidate for every normalized code referenced by Quotes, Frames, Doors/hardware linkage, Equipment, or Borrowed Lites. Automatic rows retain source identities. Deleting one records an exclusion; manual re-add clears the exclusion. A previously sourced row is retained and flagged stale instead of disappearing, and an unresolved stale row blocks submission unless its eligible line acknowledgement is recorded.

For the current model, Man Hours is the cost driver:

- labor cost = Man Hours × effective rate;
- working days = Man Hours ÷ (crew size × hours per worker per day);
- calendar weeks = working days ÷ workdays per week;
- shift label = workdays per week × hours per worker per day (for example `5x8`).

Hours per worker per day are limited to 0–24 and workdays per week to 0–7, with two-decimal input. Blank or zero denominators return unavailable values, never infinity. Migrated productivity rows retain their legacy inputs and derive migration Man Hours from the prior explicit/calculated basis so historical cost does not change.

Travel/per-diem lineage can retain schedule inputs, but no controlled overnight/lodging formula is published. Enabling spend without such a policy remains a structured blocker. Likewise, a controlled Design labor rate must be configured before Design cost is commercially available.

## Bid and submission

Bid derives one summary per normalized code without duplicating canonical source records. Expandable components include Base Product, Installation Materials, Labor, Equipment, Borrowed Lites, and any proven canonical source. Door/hardware cost remains unavailable until its commercial route is confirmed.

Each summary reports Cost, Margin Dollars, Margin Percentage, Value, Frame-plus-Borrowed-Lite square footage, and Value per square foot. Component/source overrides are keyed by stable canonical identity and retain default, override, effective value, reason, actor, and audit lineage. Clearing an override resumes the current category default. Installation Materials explicitly inherit Base Product markup until a distinct controlled default exists.

Every source line exposes one controlling markup authority: Markup % or Markup $. Percentage authority recalculates dollars when direct cost changes; dollar authority retains the entered amount and derives the effective percentage, including an unavailable percentage at zero direct cost. Switching authority replaces the former mode, clearing returns to the category default, and deduct lines inherit the commercial sign. Base and alternate decisions are recalculated by the same service and frozen into revisions, proposal states, exports, and comparisons.

Edits initiated from expanded Bid detail require a typed command with explicit confirmation and expected revision. The server resolves and updates the canonical source record, audits it, recalculates, and returns the same project revision path used by originating pages.

Submission blocks current controlled-value errors, unresolved pasted values, meaningful Frame/Door rows without quantity, unresolved stale Labor, and unavailable required controlled rates. Eligible line acknowledgements affect only their named line and remain in review/audit output.

## Migration and unresolved commercial policy

Schema 1.0 documents load through an idempotent 1.0-to-1.1 migration. The loader does not rewrite a project file merely because it was opened; migrated content persists through a normal authorized save or duplicate/import command. Immutable snapshots and deprecated fields remain intact.

Configuration `cfg-2026-08-19-v5` is a new immutable configuration identity. It retains the v4 owner references and controlled numeric rates, adds schema 1.1 policy metadata, records Installation Materials markup as inherited from Base Product until a distinct controlled value exists, and represents the absent Design Labor rate as unavailable. Existing projects and frozen revisions remain pinned to their recorded configuration IDs.

The following monetary rules are intentionally not guessed:

- travel, overnight, per-diem, lodging, excluded-day, and related tax policy;
- a controlled Design labor rate;
- the authoritative Door/hardware cost route into Bid, including tax, markup, and code;
- actual six-band bond values and a separate Installation Materials markup default.
