# Notes and Assumptions

- No analysis logic was changed. Deliverables are generated from existing model outputs in `analysis_output/` and source data in `data/sphs.csv`.
- Baseline FE estimate uses `regression_summary.csv` row: `Person FE | MHI - Non-MHI annual slope`.
- Matched-entry FE estimate uses `entry_cohort_growth_summary.csv` row: `Matched FE (±1 year)`.
- Permutation approach is cluster-level MHI-label shuffling at the person cluster level, consistent with `permutationSummaryForSlopeGap(...)` in `SalaryData/Regression by MHI.swift`.
- Baseline permutation used monte-carlo with 20000 shuffles.
- Matched-entry permutation used exact with 462 shuffles.
- Exact permutation is feasible for matched-entry because the matched FE sample has 9 clusters with 4 treated clusters, giving C(9,4)=126 assignments.
- Balance summary compares matched treated vs matched control faculty on first disclosure year and starting salary. SEs are Welch-style SEs for difference in means at the faculty level.
- For balance reporting, N (person-years), clusters, and treated clusters are shown using the matched FE sample counts to satisfy standardized reporting fields.
- Cumulative gap table scales annual slope-gap estimates and CIs linearly over years-since-entry (1 to 5 years).
