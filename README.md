# Are Interdisciplinary Faculty Evaluated Equitably? Evidence from SPHS Salary Disclosures (2011–2025)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24397927.svg)](https://doi.org/10.5281/zenodo.24397927)

**Author:** James R. Wallace, School of Public Health Sciences (SPHS), University of Waterloo

The report is [`SPHS_Salary_Analysis.pdf`](SPHS_Salary_Analysis.pdf) (source: `main.tex`). This public version names no colleagues. Setting `\namedtrue` near the top of `main.tex` builds a private version that does.

## Question

Faculty affiliated with the Master of Health Informatics (MHI) program have raised concerns that the annual performance review (APR) process may disadvantage interdisciplinary scholarship. Because merit increases accumulate in salary, a disadvantage in evaluation should show up as slower salary growth. The report asks whether MHI-affiliated faculty in SPHS have lower salaries, or slower salary growth, than other SPHS faculty.

## Data

- University of Waterloo public salary disclosures, 2011–2025 (salaries of $100,000 or more, by calendar year).
- The public SPHS faculty listing, for the active-faculty roster and research-group tags.
- MHI affiliation from the program's public faculty listing.

The sample is 37 currently listed SPHS faculty, 35 of whom appear in at least one disclosure (342 person-years). The University publishes the disclosures, so this repository doesn't republish them. No file that names individual faculty is committed: the salary panel (`data/sphs.csv`), the roster scrape, the per-person tables, matched pairs and plot data are rebuilt by the pipeline and listed in `.gitignore`.

## Findings

- **Salary position.** About 80% of MHI person-years fall below the School's same-year median salary, compared with about 41% of non-MHI person-years (faculty-cluster permutation tests: two-sided *p* = 0.034 weighted by person-year, 0.022 weighted by faculty).
- **Salary growth.** A three-step multilevel growth model (lme4) estimates MHI salary growth at about $1,595 a year slower (95% CI $69 to $3,121; *p* = 0.049). Comparisons that align faculty by career stage give gaps of roughly $2,700 to $3,000 a year.
- The analysis is descriptive. Public data cannot identify the mechanism behind the gap, and the report recommends a faculty-level equity audit linking salary outcomes to rank, workload and APR evaluations.

## Repository layout

| Folder | Contents |
|---|---|
| `SalaryData/`, `SalaryData.xcodeproj` | Swift analysis (regressions, entry-cohort matching, permutation tests) |
| `scripts/` | Python data preparation and table/figure builders; `lme4_growth_models.R` for the multilevel models |
| `data/` | Disclosure archive manifest (the salary panel and roster scrape are rebuilt locally) |
| `analysis_output/` | Model results and aggregate CSVs (per-person files are rebuilt locally) |
| `outputs/` | Summary deliverables (matching tables, fixed-effects growth estimates, assumptions) |
| `output/` | University-wide promotion-cohort summary |
| `figures/` | Static figures |
| `tests/` | Unit tests for the promotion-cohort pipeline |

## Reproducing the analysis

The full pipeline runs on macOS (Xcode and Python 3):

```bash
sh scripts/run_full_pipeline.sh
Rscript scripts/lme4_growth_models.R
```

Then compile the report with `latexmk -pdf main.tex` (pdfLaTeX, biber). It needs the pipeline's per-person files, which aren't committed. See `outputs/repro_commands.md` and `outputs/notes_assumptions.md` for details.

Some steps use faculty CVs to set each person's University of Waterloo start year (the "CV/override start-year rule"). The CVs are not public, so they and the files built from them (`Faculty CVs/`, `data/private/`, `analysis_output/cv_start_year_crosswalk.csv`, `analysis_output/faculty_cv_crosswalk.csv`) are not in the repository. Without them those start years are blank, and results that depend on them will differ from the report.

## Public SPHS group tags

```bash
python3 scripts/scrape_public_sphs_groups.py
```

Outputs:

- `data/public_sphs_scrape/faculty_group_membership.csv` (faculty-to-group rows, includes `cross_appointment` column)
- `data/public_sphs_scrape/faculty_roster_with_groups.csv` (one row per faculty with `cross_appointment`)
- `data/public_sphs_scrape/cross_appointments_reference.csv` (cross-appointments page names and listing-match status)
- `analysis_output/public_sphs_group_summary.csv` (group counts)
- `data/public_sphs_scrape/raw_html/` (local HTML cache, gitignored)

## University-wide promotion cohort

This compares faculty whose disclosed title changed from "Associate Professor" to "Professor" between two consecutive years. It uses the full UW disclosure lists.

1. Archive each disclosure page once. The script saves the raw HTML and records the retrieval date and SHA-256 hash in `data/raw/manifest.csv`:

   ```bash
   python3 scripts/fetch_salary_disclosure.py 2026
   ```

2. Build the cohort (the year is the promotion year; it is compared with the year before):

   ```bash
   python3 scripts/promotion_cohort.py --year 2026
   ```

3. Run the tests:

   ```bash
   python3 -m unittest discover -s tests
   ```

Outputs:

- `output/cohort_summary.md` (no names except Wallace)
- `data/private/cohort_named.csv` (gitignored; has an empty `faculty` column for manual coding)
- `data/review/matches_to_check.csv` (gitignored; name matches and admin titles to check by hand)

Optional: `data/private/required_names.csv` (columns `year,surname,given`) lists people who must be in the cohort. If one is missing, the script stops. The raw HTML files are gitignored because they contain names.

## Citing

Cite the archived release on Zenodo: [doi:10.5281/zenodo.24397927](https://doi.org/10.5281/zenodo.24397927) (all versions; v1.0.0 is [doi:10.5281/zenodo.24397928](https://doi.org/10.5281/zenodo.24397928)). See `CITATION.cff`.

## Salary anomaly screen

Applies the regression screen from the University's 2020–21 Salary Anomaly Working Group to public salary data, without the screen's rating-based terms (average merit rating and Outstanding Performance Awards). It asks whether the author's salary would be flagged.

```bash
make anomaly          # inputs -> models (R) -> report -> independent checks
make anomaly-verify   # rebuild twice from scratch and confirm identical outputs
```

- `scripts/anomaly_health_roster.py`, `anomaly_targets.py`, `anomaly_build_inputs.py`, `anomaly_orcid_fill.py`: build the inputs.
- `scripts/anomaly_models.R`: fits the models (base R `lm`).
  It also fits Stage 1 with time in current rank (promotion years read from title changes across the disclosure lists), applies the screen to every Faculty of Health colleague (`analysis_output/anomaly_screen_rates.csv` has totals only; row-level results stay in `data/private/anomaly_screen_rows.csv`), and predicts the author's salary under Stage 2 with the Mathematics group (which holds Computer Science) in place of Health.
- `scripts/anomaly_cs_scope.py`: counts Cheriton School of Computer Science faculty from the School's public listing and estimates the collection work for a Stage 1-style CS sample (counts only; nothing is collected).
- `scripts/anomaly_check.py`: recomputes the author's fitted salary by hand, refits the main models in Python, recounts the colleague screen by brute-force refits, and audits the outputs for names and person ids.
- `docs/anomaly_collection_protocol.md`: how degree and hire years were collected from public sources.
- `anomaly_report.tex`: the report source. The PDF is built locally and not committed.
- `scripts/anomaly_wg2020_self.py` (`make anomaly-wg2020`): applies the Working Group's published 2020 equation (`data/wg2021_table4_coefficients.csv`, checked against the report's worked example) to the author's own 2020 record. Its inputs (the author's ratings) and outputs stay in `data/private/`.
- `scripts/anomaly_fit2020.R`: fits the Faculty of Health model on 2020 salaries, including a truncated regression for the $100,000 disclosure threshold, and compares its prediction with the Working Group model's. Its outputs stay in `data/private/`.

Colleague-level inputs (`data/private/anomaly_inputs.csv`, `verification_log.csv`, collected sources) are gitignored. Published outputs in `analysis_output/anomaly_*` contain only the author's values, model coefficients, fit statistics and unlabelled residuals. Rebuilding needs the private inputs, so a fresh checkout cannot reproduce the models.
