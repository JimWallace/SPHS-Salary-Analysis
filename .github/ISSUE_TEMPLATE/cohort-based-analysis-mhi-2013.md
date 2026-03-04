---
name: Cohort-Based Analysis Anchored to MHI Establishment (2013)
about: Evaluate whether MHI growth differentials are concentrated among post-MHI entrants
labels: analysis, deferred
---

## ISSUE: Add Cohort-Based Analysis Anchored to Establishment of MHI Program (2013)

### Summary
We should evaluate whether salary growth differentials between MHI and non-MHI faculty are concentrated among faculty hired during or after the establishment of the MHI program (circa 2013), rather than among long-tenured legacy faculty.

### Rationale
- The mechanism of potential disadvantage likely operates through the contemporary APR process.
- Long-tenured faculty (pre-2013 entrants) accumulated salary under earlier regimes and may not reflect current evaluation dynamics.
- If bias exists, it should be most visible among faculty whose entire career progression occurred after MHI institutionalization.

### Proposed Design (to implement later)

1. Define Cohort Variable
   - Compute `firstDisclosureYear` for each faculty member.
   - Define:
     - `legacy = firstDisclosureYear <= 2012`
     - `postMHI = firstDisclosureYear >= 2013` (or 2014 to avoid boundary ambiguity)

2. Add Interaction Model
   Extend growth model with:
   - `year_c * MHI * postMHI`

   Interpretation:
   - baseline MHI growth gap among legacy faculty
   - additional MHI growth gap among post-MHI hires

3. Alternative Specification
   - Run segmented growth model separately for:
     - (a) full sample
     - (b) postMHI cohort only
   - Compare coefficients.

4. Reporting
   - Always report full-sample results.
   - Present cohort analysis as mechanism test, not replacement.
   - Do not exclude individuals by name.

5. Open Questions to Resolve
   - Confirm precise public documentation of MHI program launch year within SPHS.
   - Decide whether cutoff should be 2013 or 2014.
   - Verify sufficient MHI clusters in postMHI cohort for stable estimation.

### Status
Defer implementation until next coding session. Revisit after 2025 salary data is added.
