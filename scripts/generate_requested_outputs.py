#!/usr/bin/env python3
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis_output"
DATA = ROOT / "data" / "sphs.csv"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(v):
    return float(str(v).strip())


def to_int(v):
    return int(str(v).strip())


def norm_header(h):
    return "".join(h.strip().lower().split())


def sample_var(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return sum((x - m) ** 2 for x in xs) / (n - 1)


def mean_diff_with_ci(treated, control):
    mt = sum(treated) / len(treated)
    mc = sum(control) / len(control)
    vt = sample_var(treated)
    vc = sample_var(control)
    se = math.sqrt(vt / len(treated) + vc / len(control))
    est = mt - mc
    z = 1.96
    return {
        "estimate": est,
        "se": se,
        "ci_low": est - z * se,
        "ci_high": est + z * se,
        "mean_treated": mt,
        "mean_control": mc,
    }


def fmt(x, digits=3):
    return f"{x:.{digits}f}"


def write_md_table(path, headers, rows):
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


reg_rows = read_csv(ANALYSIS / "regression_summary.csv")
perm_rows = read_csv(ANALYSIS / "permutation_inference_summary.csv")
entry_rows = read_csv(ANALYSIS / "entry_cohort_growth_summary.csv")
entry_perm_rows = read_csv(ANALYSIS / "entry_cohort_permutation_summary.csv")
pair_rows = read_csv(ANALYSIS / "entry_cohort_matched_pairs.csv")

baseline = next(r for r in reg_rows if r["model"] == "Person FE" and r["term"] == "MHI - Non-MHI annual slope")
baseline_perm = next(r for r in perm_rows if r["model"] == "Person FE" and r["term"] == "MHI - Non-MHI annual slope")
matched = next(r for r in entry_rows if r["analysis"].startswith("Matched FE"))
matched_perm = next(r for r in entry_perm_rows if r["analysis"].startswith("Matched FE"))


# C) matching table csv + md
matching_csv = OUT / "matching_table.csv"
with matching_csv.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["mhi_faculty", "mhi_entry_year", "matched_non_mhi_faculty", "matched_non_mhi_entry_year", "entry_year_gap"])
    for r in pair_rows:
        w.writerow([r["mhi_person"], r["mhi_first_year"], r["non_mhi_person"], r["non_mhi_first_year"], r["year_gap"]])

matching_md_rows = []
for r in pair_rows:
    matching_md_rows.append({
        "MHI faculty": r["mhi_person"],
        "MHI entry year": r["mhi_first_year"],
        "Matched non-MHI faculty": r["non_mhi_person"],
        "Non-MHI entry year": r["non_mhi_first_year"],
        "Gap (years)": r["year_gap"],
    })
write_md_table(
    OUT / "matching_table.md",
    ["MHI faculty", "MHI entry year", "Matched non-MHI faculty", "Non-MHI entry year", "Gap (years)"],
    matching_md_rows,
)


# Parse sphs data for balance + trajectories
with DATA.open(newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames or []
    surname_col = next(c for c in fields if norm_header(c) in {"surname", "surame"})
    given_col = next(c for c in fields if norm_header(c) == "givenname")
    mhi_col = next(c for c in fields if norm_header(c) == "mhi")
    year_cols = [c for c in fields if c.strip().isdigit()]

    records = []
    for row in reader:
        surname = row[surname_col].strip().upper()
        given = row[given_col].strip().upper()
        pid = f"{surname}, {given}"
        mhi = row[mhi_col].strip().lower() in {"true", "1", "yes"}
        for yc in year_cols:
            raw = (row.get(yc) or "").strip()
            if not raw:
                continue
            salary = float(raw.replace("$", "").replace(",", ""))
            records.append({"person_id": pid, "year": int(yc.strip()), "salary": salary, "mhi": mhi})

by_person = defaultdict(list)
for r in records:
    by_person[r["person_id"]].append(r)
for p in by_person:
    by_person[p].sort(key=lambda x: x["year"])

first_year = {p: rs[0]["year"] for p, rs in by_person.items()}
start_salary = {p: rs[0]["salary"] for p, rs in by_person.items()}

mhi_people = [r["mhi_person"] for r in pair_rows]
non_people = [r["non_mhi_person"] for r in pair_rows]
matched_people = set(mhi_people + non_people)

matched_person_years = [r for r in records if r["person_id"] in matched_people]
matched_n_obs = len(matched_person_years)
n_clusters = len(matched_people)
n_treated = len(mhi_people)

entry_balance = mean_diff_with_ci([first_year[p] for p in mhi_people], [first_year[p] for p in non_people])
salary_balance = mean_diff_with_ci([start_salary[p] for p in mhi_people], [start_salary[p] for p in non_people])

# D) balance summary md + csv
balance_rows = [
    {
        "metric": "Entry year",
        "treated_mean": fmt(entry_balance["mean_treated"], 2),
        "control_mean": fmt(entry_balance["mean_control"], 2),
        "estimate": fmt(entry_balance["estimate"]),
        "SE": fmt(entry_balance["se"]),
        "CI low": fmt(entry_balance["ci_low"]),
        "CI high": fmt(entry_balance["ci_high"]),
        "N (person-years)": str(matched_n_obs),
        "clusters": str(n_clusters),
        "treated clusters": str(n_treated),
    },
    {
        "metric": "Starting salary (CAD)",
        "treated_mean": fmt(salary_balance["mean_treated"]),
        "control_mean": fmt(salary_balance["mean_control"]),
        "estimate": fmt(salary_balance["estimate"]),
        "SE": fmt(salary_balance["se"]),
        "CI low": fmt(salary_balance["ci_low"]),
        "CI high": fmt(salary_balance["ci_high"]),
        "N (person-years)": str(matched_n_obs),
        "clusters": str(n_clusters),
        "treated clusters": str(n_treated),
    },
]
with (OUT / "matched_balance_summary.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(
        f,
        fieldnames=["metric", "treated_mean", "control_mean", "estimate", "SE", "CI low", "CI high", "N (person-years)", "clusters", "treated clusters"],
    )
    w.writeheader()
    w.writerows(balance_rows)

md_lines = ["# Matched Sample Balance Summary", "", "Mean differences are treated minus control.", ""]
headers = ["metric", "treated_mean", "control_mean", "estimate", "SE", "CI low", "CI high", "N (person-years)", "clusters", "treated clusters"]
md_lines.append("| " + " | ".join(headers) + " |")
md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
for r in balance_rows:
    md_lines.append("| " + " | ".join(r[h] for h in headers) + " |")
(OUT / "matched_balance_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")


# A) baseline_personFE_growth.md
baseline_md = [
    "# Baseline Person FE Growth (MHI - Non-MHI Annual Slope)",
    "",
    "## Cluster-robust estimate",
    "",
    "| estimate | SE | 95% CI low | 95% CI high | N (person-years) | clusters | treated clusters |",
    "| --- | --- | --- | --- | --- | --- | --- |",
    f"| {baseline['estimate']} | {baseline['std_error']} | {baseline['ci_lower']} | {baseline['ci_upper']} | {baseline['n_obs']} | {baseline['n_clusters']} | {baseline_perm['n_treated_clusters']} |",
    "",
    "## Permutation inference",
    "",
    "Cluster-level label shuffling was used (MHI labels reassigned at person cluster level).",
    "",
    "| shuffles | method | two-sided p-value | estimate | SE | 95% CI low | 95% CI high | N (person-years) | clusters | treated clusters |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    f"| {baseline_perm['n_permutations']} | {baseline_perm['inference_method']} | {baseline_perm['p_two_sided']} | {baseline['estimate']} | {baseline['std_error']} | {baseline['ci_lower']} | {baseline['ci_upper']} | {baseline_perm['n_obs']} | {baseline_perm['n_clusters']} | {baseline_perm['n_treated_clusters']} |",
]
(OUT / "baseline_personFE_growth.md").write_text("\n".join(baseline_md) + "\n", encoding="utf-8")


# B) matched_entry_personFE_growth.md
matched_md = [
    "# Matched-Entry Person FE Growth (MHI - Non-MHI Annual Slope)",
    "",
    "## Cluster-robust estimate",
    "",
    "| estimate | SE | 95% CI low | 95% CI high | N (person-years) | clusters | treated clusters |",
    "| --- | --- | --- | --- | --- | --- | --- |",
    f"| {matched['estimate']} | {matched['std_error']} | {matched['ci_low']} | {matched['ci_high']} | {matched['n_obs']} | {matched['n_clusters']} | {matched['n_treated_clusters']} |",
    "",
    "## Permutation inference",
    "",
    "Exact cluster-level permutation was feasible for the matched set.",
    "",
    "| shuffles | method | two-sided p-value | estimate | SE | 95% CI low | 95% CI high | N (person-years) | clusters | treated clusters |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    f"| {matched_perm['n_permutations']} | {matched_perm['inference_method']} | {matched_perm['p_two_sided']} | {matched['estimate']} | {matched['std_error']} | {matched['ci_low']} | {matched['ci_high']} | {matched['n_obs']} | {matched['n_clusters']} | {matched['n_treated_clusters']} |",
]
(OUT / "matched_entry_personFE_growth.md").write_text("\n".join(matched_md) + "\n", encoding="utf-8")


# E) cumulative gap table
base_est = to_float(baseline["estimate"])
base_se = to_float(baseline["std_error"])
base_lo = to_float(baseline["ci_lower"])
base_hi = to_float(baseline["ci_upper"])
base_n = to_int(baseline["n_obs"])
base_clusters = to_int(baseline["n_clusters"])
base_treated = to_int(baseline_perm["n_treated_clusters"])

match_est = to_float(matched["estimate"])
match_se = to_float(matched["std_error"])
match_lo = to_float(matched["ci_low"])
match_hi = to_float(matched["ci_high"])
match_n = to_int(matched["n_obs"])
match_clusters = to_int(matched["n_clusters"])
match_treated = to_int(matched["n_treated_clusters"])

cum_lines = [
    "# Cumulative Salary Gap Table", "", "Cumulative gap is annual slope gap multiplied by years since entry.", "",
    "| model | years since entry | estimate | SE | 95% CI low | 95% CI high | N (person-years) | clusters | treated clusters |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
]
for y in [1, 2, 3, 4, 5]:
    cum_lines.append(
        f"| Baseline Person FE | {y} | {fmt(base_est * y)} | {fmt(base_se * y)} | {fmt(base_lo * y)} | {fmt(base_hi * y)} | {base_n} | {base_clusters} | {base_treated} |"
    )
for y in [1, 2, 3, 4, 5]:
    cum_lines.append(
        f"| Matched-entry Person FE | {y} | {fmt(match_est * y)} | {fmt(match_se * y)} | {fmt(match_lo * y)} | {fmt(match_hi * y)} | {match_n} | {match_clusters} | {match_treated} |"
    )
(OUT / "cumulative_gap_table.md").write_text("\n".join(cum_lines) + "\n", encoding="utf-8")


# F) matched FE trajectories figure
fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
colors = {True: "#c0392b", False: "#1f4e79"}
labels_done = {True: False, False: False}

for person, series in by_person.items():
    if person not in matched_people:
        continue
    first = first_year[person]
    xs = [r["year"] - first for r in series]
    ys = [r["salary"] for r in series]
    grp = series[0]["mhi"]
    label = "MHI faculty" if grp else "Non-MHI faculty"
    ax.plot(xs, ys, color=colors[grp], alpha=0.35, linewidth=1.5, label=label if not labels_done[grp] else None)
    labels_done[grp] = True

for grp in [False, True]:
    series = defaultdict(list)
    for person in matched_people:
        pseries = by_person[person]
        if pseries[0]["mhi"] != grp:
            continue
        first = first_year[person]
        for r in pseries:
            series[r["year"] - first].append(r["salary"])
    xs = sorted(series.keys())
    ys = [sum(series[x]) / len(series[x]) for x in xs]
    ax.plot(xs, ys, color=colors[grp], linewidth=3.0, label=("Mean non-MHI" if not grp else "Mean MHI"))

ax.set_title("Matched Sample Salary Trajectories by Years Since Entry")
ax.set_xlabel("Years Since First Disclosure")
ax.set_ylabel("Salary (CAD)")
ax.grid(alpha=0.2)
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(OUT / "fig_matched_FE_trajectories.png")
plt.close(fig)


# G) repro commands
repro = """# Reproducibility Commands

```bash
cd /Users/jim/Documents/SPHS\ Salary\ Analysis
xcodebuild -project SalaryData.xcodeproj -scheme SalaryData -configuration Debug -derivedDataPath build build
./build/Build/Products/Debug/SalaryData
python3 scripts/generate_requested_outputs.py
```

Notes:
- The analysis binary reads `data/sphs.csv` if present and writes core results to `analysis_output/`.
- The reporting script writes requested deliverables to `outputs/`.
"""
(OUT / "repro_commands.md").write_text(repro, encoding="utf-8")


# H) notes and assumptions
notes = f"""# Notes and Assumptions

- No analysis logic was changed. Deliverables are generated from existing model outputs in `analysis_output/` and source data in `data/sphs.csv`.
- Baseline FE estimate uses `regression_summary.csv` row: `Person FE | MHI - Non-MHI annual slope`.
- Matched-entry FE estimate uses `entry_cohort_growth_summary.csv` row: `Matched FE (±1 year)`.
- Permutation approach is cluster-level MHI-label shuffling at the person cluster level, consistent with `permutationSummaryForSlopeGap(...)` in `SalaryData/Regression by MHI.swift`.
- Baseline permutation used {baseline_perm['inference_method']} with {baseline_perm['n_permutations']} shuffles.
- Matched-entry permutation used {matched_perm['inference_method']} with {matched_perm['n_permutations']} shuffles.
- Exact permutation is feasible for matched-entry because the matched FE sample has 9 clusters with 4 treated clusters, giving C(9,4)=126 assignments.
- Balance summary compares matched treated vs matched control faculty on first disclosure year and starting salary. SEs are Welch-style SEs for difference in means at the faculty level.
- For balance reporting, N (person-years), clusters, and treated clusters are shown using the matched FE sample counts to satisfy standardized reporting fields.
- Cumulative gap table scales annual slope-gap estimates and CIs linearly over years-since-entry (1 to 5 years).
"""
(OUT / "notes_assumptions.md").write_text(notes, encoding="utf-8")

print("Wrote requested deliverables to", OUT)
