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
| [research] excluded: curr rank not Professor | 379 |
| [research] excluded: no exact name match in curr year | 3 |
| [research] cohort size | 22 |
| [teaching] excluded: curr rank not Professor | 156 |
| [teaching] excluded: no exact name match in curr year | 3 |
| [teaching] cohort size | 0 |

## Research-stream cohort (n = 22)

| Statistic | 2024 paid | 2025 paid | Change (2025 - 2024) |
|---|---|---|---|
| Minimum | $141,651 | $143,600 | -$15,183 |
| Lower quartile | $175,856 | $185,436 | $9,678 |
| Median | $187,444 | $200,958 | $11,909 |
| Upper quartile | $207,208 | $222,442 | $18,103 |
| Maximum | $219,324 | $236,864 | $28,891 |

### Wallace's position

| Measure | Wallace | Rank (1 = highest) | Percentile |
|---|---|---|---|
| 2024 paid | $141,651 | 22 of 22 | 0 |
| 2025 paid | $143,600 | 22 of 22 | 0 |
| Change (2025 - 2024) | $1,949 | 21 of 22 | 5 |

### 2025 figures with Wallace's annualized base ($162,628.83) in place of his paid figure

| Statistic | 2025 paid | Change (2025 - 2024) |
|---|---|---|
| Minimum | $158,772 | -$15,183 |
| Lower quartile | $185,436 | $10,324 |
| Median | $200,958 | $12,953 |
| Upper quartile | $222,442 | $19,963 |
| Maximum | $236,864 | $28,891 |

| Measure | Wallace | Rank (1 = highest) | Percentile |
|---|---|---|---|
| 2025 paid | $162,629 | 21 of 22 | 5 |
| Change (2025 - 2024) | $20,978 | 5 of 22 | 81 |

## Teaching-stream cohort (n = 0)

Too few members for summary statistics.
