# INF-4320 rule status and unresolved requirements

INF-4320 v2.1.0 is a **Developing** specification. This application distinguishes:

- **Verified** — directly observed workbook structure or formula behavior.
- **Confirmed** — business rule explicitly confirmed by the owner in INF-4320.
- **Pending** — insufficient evidence. The application exposes a configuration or provisional record and does not claim policy approval.

## Safe seed defaults

The project tax selection still seeds to the unconfigured `0` record unless a jurisdiction-specific rate is deliberately selected. Base/LAF/LAS markup, bond rates, and both hidden PCO markup stages seed to `0`. Bond and contingency seed disabled. These are intentionally non-commercial safe values, visibly labeled pending. The documented contingency formula (greater of 1% or $3,000) is implemented and confirmed, but enable/override authority is pending. The six-band bond engine is implemented and tested with supplied configurations; INF-4320 does not publish the six actual thresholds or rates.

Frame material rates/factors and door hardware prices use the values observed in the workbook, labeled **verified embedded defaults**, not universal business standards. The 14.25% fringe credit and NTP activation trigger are labeled confirmed.

Owner-provided rate tables are stored in configuration version 3. Their numeric source values are preserved, but county classification/effective date, vendor refresh cadence, and some rate-unit interpretations remain pending. `#N/A` is unavailable—not zero. The supplied 7.38% tax record is specifically labeled Minnesota/Sherburne and is not a statewide default.

## Owner decisions still required

The 2.1 web contract now confirms Project Type, Contract Type, Wage Type, local Bid Due Date/time, reusable records, Quote adjustment/selection, Frame and Door quantity exceptions, controlled project overrides, Man-Hours Labor scheduling, and per-code Bid aggregation. The following decisions remain unresolved:

1. Remaining required project fields, file naming/reuse, and submission evidence.
2. Large-bid dollar/risk/customer/scope threshold and proof of GM/President review.
3. Exact Support delegation and activation reversal/correction handling.
4. Contract re-estimate control total, approval, and ability to change total value.
5. Bond six-band numeric schedule plus bond/contingency enable and override authority.
6. Hidden PCO markup rates, sources, approval, change authority, and contract-effect approval.
7. Minnesota wage/rate import cadence, effective-date selection, evidence retention, and verification.
8. Tax exemption evidence and jurisdictional tax rates.
9. Travel/per diem/lodging/excluded-day logic and authority.
10. Equipment duration semantics and certain DRS-to-BID lineage.
11. SOV role, approval, underallocation treatment, and rounding policy beyond reconciliation.
12. Closeout gates, final approval, exceptions, archive location, and retention period.
13. Exact approved Minneapolis mileage origin, route-provider service level, and whether travel policy uses one-way, round-trip, or another mileage basis.
14. A controlled Design Labor rate and its source/effective-date authority.
15. The authoritative Door/Hardware monetary route into Bid, including cost code, tax, and markup treatment.
16. Whether Installation Materials should receive a distinct controlled markup; until confirmed, the web contract explicitly inherits Base Product markup.
17. The exact protected authorization workflow for a custom Actual Cost Code that is absent from the owner-controlled reference. Current Installation Material classification accepts the full controlled reference only; it does not silently create project scope or a custom reference.

Until resolved, closeout is explicitly `provisional_pending_policy`; activation cannot be reversed through the UI; overallocated SOV lines are blocked; and underallocated lines remain pending treatment. Enabled travel without a controlled policy, Design Labor without a controlled rate, and other required unavailable commercial inputs remain structured submission blockers. The application does not infer Door/Hardware selling cost or invent a separate Installation Materials markup.
