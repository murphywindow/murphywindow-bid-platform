# Owner Rate Reference

Configuration `cfg-2026-08-17-v3` first normalized the rate tables supplied by the owner on 2026-08-17. Configuration `cfg-2026-08-17-v4` added versioned mileage settings. Current configuration `cfg-2026-08-19-v5` retains those records unchanged and adds schema 1.1 policy metadata, explicit Base Product inheritance for Installation Materials markup, and an unavailable Design Labor placeholder rather than inventing a rate. The complete normalized records are emitted to the human-readable configuration JSON under `data/configurations/` and are defined in `app/rate_reference.py` for reproducible installation.

## Included source data

- 2025 field non-prevailing-wage burden rows and average
- 2025 field prevailing-wage source rows, including literal unavailable (`#N/A`) values
- Shop burden rows and average
- Ten percentage overhead factors, the fixed $1.75 health-insurance amount, and the supplied 36%/$1.75 total
- Standard field rate $68.53, shop rate $38.85, unavailable PW standard rate, and $120 per diem
- All 87 Minnesota county basic/fringe/total rows
- 22 rental/equipment rows with original rate unit and delivery fields
- 17 material/vendor rows with tax, surcharge, notes, and last-check data
- Owner-supplied 7.38% Minnesota/Sherburne combined tax reference last checked 2024-09-01

## Interpretation and safeguards

`#N/A` and blank values are stored as JSON `null`, accompanied by a status/source value. They are never converted to zero. County rows did not include a labor classification or effective date, so those fields remain null and each record is labeled `owner_provided_pending_classification_and_effective_date`.

The county `fringe_credit`, `usable_fringe`, and `estimated_company_rate` fields are calculated using the confirmed 14.25% credit:

`fringe credit = basic rate × 0.1425`

`estimated company rate = basic rate + published fringe − fringe credit`

These calculated fields do not turn the incomplete county row into an official wage determination. The user must verify county, classification, effective date, and applicable wage publication before commercial use.

Source burden values are preserved without silently forcing arithmetic reconciliation. In particular, supplied shop total-burden values do not always equal the displayed hourly wage plus displayed direct overhead. This is retained as source lineage rather than “corrected” without owner direction.

Material notes—such as the backpan square-foot update note—are stored as source notes, not interpreted as instructions to change INF-4320 calculation rules. Rental rows with old or missing check dates remain visibly stale/unverified. The Sherburne tax reference must only be selected after confirming project jurisdiction and the current rate.

## Test-project behavior

Generated public and K-12 scenarios select their location’s county row and use the calculated company rate for synthetic field labor. Non-PW scenarios use $68.53 field and $38.85 shop rates. Equipment records reference the imported rental IDs/configuration version. Per diem is populated at $120 but remains disabled because travel policy is unresolved. The 7.38% tax reference is selected only for generated Sherburne County locations.

All generated records retain `rate_id`, `rate_version`, and generation metadata. Submitted and awarded revisions remain pinned to their original configuration; adding version 3 does not rewrite earlier version-2 projects.
