# Are Interdisciplinary Faculty Evaluated Equitably? Evidence from SPHS Salary Disclosures (2011–2025)

**Author:** James R. Wallace, School of Public Health Sciences (SPHS), University of Waterloo
**Report:** [`SPHS_Salary_Analysis.pdf`](SPHS_Salary_Analysis.pdf) (May 2026), built from [`main.tex`](main.tex)

This repository has the report, the data and the code behind it. The analysis asks whether faculty
affiliated with the Master of Health Informatics (MHI) program have had slower salary growth than
their SPHS colleagues. Salary is the cumulative result of annual performance reviews, so it is one
observable proxy for how those reviews have treated interdisciplinary work.

## Findings

From the report's executive summary:

- **Sample:** 37 currently listed SPHS faculty, 35 of them with at least one disclosed salary,
  giving 342 person-year observations (2011–2025).
- **Position in the School's distribution:** about 80% of MHI person-years fall below the
  within-year median salary, against about 41% of non-MHI person-years.
- **Growth:** a three-step unconditional growth model (`lme4`) estimates the MHI annual growth gap
  at about −$1,595 per year (95% CI −$3,121 to −$69, p = 0.049). Comparisons aligned by career
  stage give about −$2,700 to −$3,000 per year.

The analysis is descriptive. Public disclosures don't include APR ratings, promotion dates or
workload, so it can't identify the mechanism behind the differences. The report recommends a
faculty-level equity audit that links salary to those records.

## Data

All inputs are public:

- **Salaries:** University of Waterloo salary disclosures, 2011–2025. Ontario's *Public Sector
  Salary Disclosure Act* only requires salaries of $100,000 or more to be disclosed, so careers are
  left-censored and the panel is unbalanced. Missing years are not imputed.
- **MHI affiliation:** the public SPHS Health Informatics faculty roster.
- **Faculty list and research groups:** the public SPHS faculty listing.

`data/sphs.csv` is the panel used in the report: one row per faculty member, an `MHI` flag and one
column per year. `data/public_sphs_scrape/` has the roster and group tags. `data/raw/manifest.csv`
records the retrieval date and SHA-256 hash of each archived disclosure page.

No internal personnel records were used. Two optional covariates (terminal-degree domain and
self-defined research factors) come from faculty CVs that are **not** in this repository; see
below.

## Repository layout

| Path | Contents |
|---|---|
| `main.tex`, `format.tex`, `bib.bib` | The report (LaTeX, pgfplots) |
| `SalaryData/`, `SalaryData.xcodeproj` | Main analysis (Swift): regressions, segmented growth, entry cohorts |
| `scripts/` | Python data collection and output builders; `lme4_growth_models.R` for the multilevel models |
| `scripts/run_full_pipeline.sh` | Runs everything in order |
| `analysis_output/`, `outputs/`, `output/` | Generated tables and figure data used by the report |
| `figures/` | Figures |
| `tests/` | Unit tests for the promotion-cohort script |

## Reproducing the analysis

Requirements: Python 3 (standard library, plus `pymupdf` for the steps that read CVs), Xcode
(macOS) for the Swift analysis, R with `lme4` and `lmerTest`, and a TeX distribution with
`pgfplots` and `biblatex` for the report.

```bash
sh scripts/run_full_pipeline.sh       # data, analysis and report inputs
Rscript scripts/lme4_growth_models.R  # multilevel growth models
latexmk -pdf main.tex                 # the report
python3 -m unittest discover -s tests
```

Steps 4 and 7 of the pipeline read faculty CVs from `Faculty CVs/`, which is not in the
repository, so a full rerun needs those files. The generated files in `analysis_output/` are the
ones the report was built from.

### Private CV-based covariate (local only)

To add the terminal-degree domain factor from private CVs:

1. Place CV PDFs in `Faculty CVs/` (this folder is gitignored).
2. Run:

```bash
python3 scripts/build_terminal_degree_domains.py
```

This writes `data/private_terminal_degree_domain.csv` (also gitignored).  
The Swift analysis automatically uses this file when present.

### Public SPHS group tags

To pull publicly available researcher-group tags from the SPHS faculty listing:

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

## Licence

- **Code** (`scripts/`, `SalaryData/`, `SalaryData.xcodeproj`, `tests/`): [MIT](LICENSE).
- **Report, figures and derived data** (`main.tex`, `format.tex`, `SPHS_Salary_Analysis.pdf`,
  `figures/`, `data/`, `analysis_output/`, `outputs/`, `output/`):
  [CC BY 4.0](LICENSE-CC-BY-4.0).

The salary figures themselves are public records from the University of Waterloo's disclosures
under Ontario's *Public Sector Salary Disclosure Act*. The licence covers this compilation and
analysis, not those records.

## Citing

See [`CITATION.cff`](CITATION.cff), or GitHub's "Cite this repository" button.
