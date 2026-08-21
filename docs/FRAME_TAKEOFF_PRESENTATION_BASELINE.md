# Frame Takeoff presentation baseline

## Recovery point

The polished Frame Takeoff implementation that preceded the temporary functional-baseline interface is preserved locally in Git:

- Commit: `ef136ba` (`Baseline polished Frame Takeoff implementation`)
- Tag: `frame-takeoff-polished-baseline-2026-08-19`

The tag captures the entire repository, not only screenshots or copied markup. For example, the earlier renderer can be inspected without changing the working tree with:

```powershell
git show frame-takeoff-polished-baseline-2026-08-19:app/static/app.js
```

Do not delete this tag during ordinary cleanup. It is the restoration and comparison boundary for later Frame Takeoff design work.

## Active production-compact path

There is one active Frame Takeoff data and calculation path. The production-compact renderer uses the project schema, configuration material rules, event handling, autosave queue, optimistic revision checks, atomic persistence, audit changes, server calculations, normalized Bid lines, immutable submission snapshots, and lifecycle services.

`FRAME_TAKEOFF_PRESENTATION` in `app/static/app.js` identifies the active presentation as `production-compact`. It is a marker, not a feature flag and not a second calculation implementation. `app/static/index.html` loads `styles.css`.

Base is the presentation authority for Frame Takeoff. Alternate tabs must reuse the same section structure, column order, controls, spacing, and interaction patterns; Alternate-specific UI should be limited to inherited/modified/added/removed state and the actions required to manage those deltas.

The following capabilities remain active in the basic view:

- Multiple cost-code-derived Frame Spec Sections with create, collapse, expand, and safe remove behavior.
- Editable frame-line fields, calculated quantities, one trailing working row, Enter-based rapid entry, row duplication, and row deletion.
- Section-specific installation-material applicability, factors, rates, Tie Back quantity, and Backpans / Insulation quantity.
- Separate Grouping / Spec Code at the section level and full-reference Actual Cost Code classification for project-specific materials.
- Section totals and installation-material results.
- Stable three-state column sorting that moves only rendered rows, retains the trailing working row, and never mutates canonical takeoff order.
- Existing autosave, persistence, audit, recovery, authorization, calculation lineage, and downstream Bid behavior.

## Preserved historical presentation

The tag remains a comparison point for prior badges, metric-card summaries, decorative section identity, and control treatments. Current production-compact behavior must be changed selectively; the tagged source is historical evidence, not an active second renderer.

## Later restoration or redesign

Use the tag as a reference when evaluating future presentation changes. Do not restore `app/static/app.js` or `styles.css` wholesale from the tag, because doing so would discard later functional, accessibility, alternate, sorting, and commercial-lineage work.
