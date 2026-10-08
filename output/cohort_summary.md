# Promotion cohort: Associate Professor (2024) to Professor (2025)

Source: University of Waterloo salary disclosure lists for 2024 and 2025, archived under `data/raw/` (see `data/raw/manifest.csv` for retrieval dates and SHA-256 hashes).

Cohort: research-stream faculty on the main campus whose title was "Associate Professor" in 2024 and "Professor" in 2025, matched by exact normalized name. Affiliated colleges, non-regular ranks (Research, Clinical, Adjunct, Visiting) and teaching-stream titles are not in this cohort. Fuzzy name matches are not in the cohort; they are in the manual-review file.

## Read this first

- The comparison is descriptive, not causal.
- The 2025 figures blend about six months at each rank (promotions take effect on July 1).
- "Paid" is the salary paid in the calendar year. Comparator figures can include sabbaticals, stipends and other payments.
- Wallace's 2025 paid figure includes about eight months of sabbatical at 85% pay. The last section uses his annualized base salary instead.
- Quartiles use the inclusive method (Python `statistics.quantiles`, `method="inclusive"`).
- Percentile = percentage of the other cohort members with a lower value.

## Filter counts

| Step | Count |
|---|---|
| prev-year rows | 2245 |
| excluded: affiliated college | 74 |
| excluded: non-regular rank (Research/Clinical/Adjunct/Visiting) | 18 |
| excluded: rank not Associate in prev year | 1590 |
| [research] Associate pool, main campus | 404 |
| [teaching] Associate pool, main campus | 159 |
| [research] excluded: curr rank not Professor | 378 |
| [research] excluded: name not unique in a year | 2 |
| [research] excluded: no exact name match in curr year | 3 |
| [research] cohort size | 21 |
| [teaching] excluded: curr rank not Professor | 156 |
| [teaching] excluded: no exact name match in curr year | 3 |
| [teaching] cohort size | 0 |

## Research-stream cohort (n = 21)

| Statistic | 2024 paid | 2025 paid | Change (2025 - 2024) |
|---|---|---|---|
| Minimum | $141,651 | $143,600 | -$15,183 |
| Lower quartile | $175,432 | $185,253 | $9,522 |
| Median | $186,803 | $199,973 | $11,825 |
| Upper quartile | $208,589 | $223,678 | $17,306 |
| Maximum | $219,324 | $236,864 | $28,891 |

### Wallace's position

| Measure | Wallace | Rank (1 = highest) | Percentile |
|---|---|---|---|
| 2024 paid | $141,651 | 21 of 21 | 0 |
| 2025 paid | $143,600 | 21 of 21 | 0 |
| Change (2025 - 2024) | $1,949 | 20 of 21 | 5 |

### 2025 figures with Wallace's annualized base ($162,628.83) in place of his paid figure

| Statistic | 2025 paid | Change (2025 - 2024) |
|---|---|---|
| Minimum | $158,772 | -$15,183 |
| Lower quartile | $185,253 | $10,145 |
| Median | $199,973 | $11,992 |
| Upper quartile | $223,678 | $18,369 |
| Maximum | $236,864 | $28,891 |

| Measure | Wallace | Rank (1 = highest) | Percentile |
|---|---|---|---|
| 2025 paid | $162,629 | 20 of 21 | 5 |
| Change (2025 - 2024) | $20,978 | 5 of 21 | 80 |

## Teaching-stream cohort (n = 0)

Too few members for summary statistics.
