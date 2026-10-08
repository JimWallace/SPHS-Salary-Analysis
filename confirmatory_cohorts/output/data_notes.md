# Data notes

## Sources

University of Waterloo salary disclosure lists, archived once under `data/raw/` (raw HTML gitignored). New for this analysis: 2021 and 2022.

| Year | URL | Retrieved | SHA-256 |
|---|---|---|---|
| 2021 | https://uwaterloo.ca/about/accountability/salary-disclosure-2021 | 2026-10-08 | `77696204ff7e54a17b11802a7bafd9cd956c9ee09c1d7f0d250acdb66491fff0` |
| 2022 | https://uwaterloo.ca/about/accountability/salary-disclosure-2022 | 2026-10-08 | `abbea20ff490ce3563d1b104a1adea88bc6dce6c440acc2224c4c9a6d624f380` |
| 2023 | https://uwaterloo.ca/about/accountability/salary-disclosure-2023 | 2026-10-08 | `b78034e1588ccd4260332fd6ec5991d09c05f32962b3292d84a567aaa705f490` |
| 2024 | https://uwaterloo.ca/about/accountability-reports/salary-disclosure-2024 | 2026-10-08 | `f8a66bedbda1c0a87c07178236d105f7cbaff752a8951257c7ce36aa37f7c5a8` |
| 2025 | https://uwaterloo.ca/about/accountability-reports/salary-disclosure-2025 | 2026-10-08 | `edb27afc5c798d0b5e16712904814b467e78a31e625281264ff3bdc5064e4080` |

Format check: every list has one table with the same five columns (Surname, Given name, Position title, Salary paid, Taxable benefits), five cells in every row, and no missing salaries. Difference: the 2021-2023 lists have no "Teaching Stream" titles; teaching-stream faculty were titled "Lecturer" until 2023. Those titles have no academic rank, so the research-stream rule is the same in every year. One new title form, "Professor Emeritus" (2022), has no rank and is not used.

## Cohorts

| Cohort | Members | Administrative-title cases | Other non-exact matches | Not a main-campus Professor in 2025 |
|---|---|---|---|---|
| 2022 | 27 | 1 | 1 | 3 |
| 2023 | 14 | 0 | 2 | 0 |
| 2024 | 26 | 0 | 3 | 0 |
| 2025 | 22 | 0 | 2 | n/a |

- Administrative-title cases: an Associate Professor in the year before whose title in the cohort year (or the year before) has an administrative role. They are not included or excluded automatically; they are in `review/manual_matches.csv`.
- Other non-exact matches (names not unique, matched by middle initial, fuzzy suggestions, stream changes) are in the same file. Fuzzy suggestions are never added to a cohort.
- Attrition: these members are excluded from Analysis A (2025 salary). Analysis B (salary in the promotion year) keeps them.

## Lump-sum and retroactive payment flags

Year-over-year increases above 15% in disclosed salary, 2021-2025, for every cohort member, excluding the promotion year and the year after. No figure is adjusted. Total flags: 15. List (anonymous IDs, no salaries): `output/lump_sum_flags.csv`.

| Year | Flags |
|---|---|
| 2022 | 1 |
| 2023 | 5 |
| 2024 | 8 |
| 2025 | 1 |

Not flagged by this rule: 5 increases above 15% in a member's promotion year and 7 in the year after. Analysis B uses the promotion-year salary, so these figures can include lump sums. They raise colleagues' values, so they can only make my position look worse, not better.

For information: 1 year-over-year decreases larger than 15% (possible leaves or sabbaticals).

## Faculty of Health subset

A member counts only if surname and first given name both match the current public unit listings (SPHS, Kinesiology and Health Sciences, Recreation and Leisure Studies). The listings show current faculty, so people who left are missed. This matters more for the older cohorts.
