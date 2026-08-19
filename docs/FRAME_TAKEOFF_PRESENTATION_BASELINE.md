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

## Active functional path

There is one active Frame Takeoff data and calculation path. The temporary basic renderer continues to use the existing project schema, configuration material rules, event handling, autosave queue, optimistic revision checks, atomic persistence, audit changes, server calculations, normalized Bid lines, immutable submission snapshots, and lifecycle services.

`FRAME_TAKEOFF_PRESENTATION` in `app/static/app.js` identifies the active presentation as `functional-baseline`. It is a marker, not a feature flag and not a second calculation implementation.

The following capabilities remain active in the basic view:

- Multiple cost-code-derived Frame Spec Sections with create, collapse, expand, and safe remove behavior.
- Editable frame-line fields, calculated quantities, one trailing working row, Enter-based rapid entry, row duplication, and row deletion.
- Section-specific installation-material applicability, factors, rates, Tie Back quantity, and Backpans / Insulation quantity.
- Section totals and installation-material results.
- Existing autosave, persistence, audit, recovery, authorization, calculation lineage, and downstream Bid behavior.

## Intentionally dormant presentation

The prior badges, verification note, metric-card summary, decorative section identity, icon-only controls, and other polished Frame Takeoff treatments are intentionally absent from the active renderer. Their source remains available through the baseline tag. They are dormant presentation work, not evidence of obsolete product capability.

Shared application navigation, project context, role context, save controls, and all non-Frame-Takeoff pages remain on their established presentation path.

## Later restoration or redesign

Use the tag as a reference and selectively reintroduce presentation around the active functional path. Do not restore `app/static/app.js` wholesale from the tag, because doing so would also discard later functional fixes. Compare the tagged renderer and scoped Frame Takeoff CSS, then port only the presentation decisions deliberately selected for the next design.
