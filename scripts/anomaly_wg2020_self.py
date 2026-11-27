#!/usr/bin/env python3
"""Test 1: the Working Group's published 2020 model applied to the subject's own 2020 record.

Usage:
  python3 scripts/anomaly_wg2020_self.py            # needs the private input file below
  python3 scripts/anomaly_wg2020_self.py --example  # reproduces the Working Group's worked example only

This applies the fitted equation published in the Salary Anomaly Working Group report (Table 4,
data/wg2021_table4_coefficients.csv) to one person's 1 May 2020 record. It does not fit anything and
does not use the selective-increase formula of the Memorandum of Agreement: it evaluates the published
regression line, as the Working Group's own worked example does.

Private input (gitignored; written as a template on first run):
  data/private/subject_wg2020.csv  one row:
    base_salary_2020_05_01   annual base salary on 1 May 2020, excluding stipends
    r_scores_2014_2020       the overall merit ratings for 2014-2020 that exist, separated by ";"
    opa_count_2020           Outstanding Performance Awards received by 1 May 2020
    current_rank_2020        rank on 1 May 2020 (pre-filled from the 2019-2020 disclosed titles)
    rank_at_hire, hire_year, degree_year, highest_degree, academic_group  (pre-filled)

Private outputs (never published unless the subject decides otherwise):
  data/private/anomaly_wg2020_self.csv
  data/private/anomaly_wg2020_self.md   the full calculation, term by term, for checking by hand
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COEFS = ROOT / "data" / "wg2021_table4_coefficients.csv"
INPUT = ROOT / "data" / "private" / "subject_wg2020.csv"
OUT_CSV = ROOT / "data" / "private" / "anomaly_wg2020_self.csv"
OUT_MD = ROOT / "data" / "private" / "anomaly_wg2020_self.md"

REF_YEAR = 2020
FLAG_ABS, FLAG_REL = 5000.0, 0.90
GROUPS = {"Health": None, "Arts": "ARTS", "Eng": "ENG", "Env": "ENV", "Math": "MATH", "Sci": "SCI", "SAF": "SAF",
          "Econ": "Econ", "CSCS": "CSCS", "SOVS": "SOVS", "Pharmacy": "Pharmacy"}
RANKS = {"Assistant": None, "Associate": "Associate Professor", "Professor": "Professor", "Lecturer": "Lecturer"}

TEMPLATE = {
    "base_salary_2020_05_01": "",
    "r_scores_2014_2020": "",
    "opa_count_2020": "",
    "current_rank_2020": "Associate",
    "rank_at_hire": "Assistant",
    "hire_year": "2014",
    "degree_year": "2012",
    "highest_degree": "Doctoral",
    "academic_group": "Health",
}


def load_coefs() -> dict[str, float]:
    with COEFS.open(encoding="utf-8") as f:
        return {r["term"]: float(r["estimate"]) for r in csv.DictReader(f)}


def terms(c: dict[str, float], *, r_avg: float, opa: int, hire_year: int, degree_year: int, degree: str,
          rank: str, rank_at_hire: str, group: str) -> list[tuple[str, float, float]]:
    """(term, value, coefficient) for every non-zero term of the Working Group's equation, R score last."""
    lag, yrs = hire_year - degree_year, REF_YEAR - hire_year
    out = [("Intercept", 1, c["(Intercept)"]), ("Lag", lag, c["Lag"]), ("Years at UW", yrs, c["Years.UW"]),
           ("Years at UW squared", yrs ** 2, c["Years.UW.sq"]), ("OPAs", opa, c["OPA"])]
    if degree != "Bachelor":
        out.append((f"Highest degree: {degree}", 1, c[f"Highest.Degree:{degree}"]))
    if RANKS[rank_at_hire]:
        out.append((f"Rank at hire: {RANKS[rank_at_hire]}", 1, c[f"Rank.at.Hire:{RANKS[rank_at_hire]}"]))
        out.append((f"Lag x rank at hire: {RANKS[rank_at_hire]}", lag, c[f"Lag x Rank.at.Hire:{RANKS[rank_at_hire]}"]))
    if RANKS[rank]:
        out.append((f"Current rank: {RANKS[rank]}", 1, c[f"Current.Rank:{RANKS[rank]}"]))
    g = GROUPS[group]
    if g:
        out.append((f"Academic group: {g}", 1, c[f"Academic.Group:{g}"]))
        if rank != "Lecturer":
            out.append((f"Academic group {g} x professorial rank", 1, c[f"Academic.Group:{g} x Prof"]))
    out.append(("Average R score", r_avg, c["R-score avg"]))
    return [t for t in out if t[1] != 0]


def fitted(ts) -> float:
    return sum(v * b for _, v, b in ts)


def worked_example(c) -> float:
    """The report's example: Environment, hired Assistant 2010, PhD 2008, average R 1.5, Associate in 2020,
    no OPAs. Published fitted salary: 138182.10."""
    return fitted(terms(c, r_avg=1.5, opa=0, hire_year=2010, degree_year=2008, degree="Doctoral",
                        rank="Associate", rank_at_hire="Assistant", group="Env"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--example", action="store_true")
    args = ap.parse_args()
    c = load_coefs()
    ex = worked_example(c)
    if abs(ex - 138182.10) > 0.5:
        sys.exit(f"Coefficient check FAILED: worked example gives {ex:,.2f}, report says 138,182.10")
    print(f"Worked example reproduced: {ex:,.2f} (report: 138,182.10)")
    if args.example:
        return

    if not INPUT.exists():
        INPUT.parent.mkdir(parents=True, exist_ok=True)
        with INPUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(TEMPLATE))
            w.writeheader()
            w.writerow(TEMPLATE)
        sys.exit(f"Wrote a template to {INPUT.relative_to(ROOT)}. Fill in base salary, R scores and OPAs, then rerun.")
    with INPUT.open(encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    missing = [k for k in ("base_salary_2020_05_01", "r_scores_2014_2020", "opa_count_2020") if not row[k].strip()]
    if missing:
        sys.exit(f"Fill in {', '.join(missing)} in {INPUT.relative_to(ROOT)}.")

    scores = [float(x) for x in row["r_scores_2014_2020"].replace(",", ";").split(";") if x.strip()]
    r_avg = sum(scores) / len(scores)
    actual = float(row["base_salary_2020_05_01"].replace(",", "").replace("$", ""))
    kw = dict(opa=int(row["opa_count_2020"]), hire_year=int(row["hire_year"]), degree_year=int(row["degree_year"]),
              degree=row["highest_degree"], rank=row["current_rank_2020"], rank_at_hire=row["rank_at_hire"],
              group=row["academic_group"])
    ts = terms(c, r_avg=r_avg, **kw)
    fit = fitted(ts)
    gap = fit - actual
    flagged = gap > FLAG_ABS and actual < FLAG_REL * fit
    b_r = c["R-score avg"]
    without_r = fit - r_avg * b_r
    r_matching = (actual - without_r) / b_r                      # R at which fitted = actual
    r_flag = (max(actual + FLAG_ABS, actual / FLAG_REL) - without_r) / b_r  # flagged if average R above this

    result = {
        "base_salary_2020_05_01": f"{actual:.2f}", "r_scores_used": len(scores), "r_average": f"{r_avg:.4f}",
        "opa_count": kw["opa"], "fitted_2020": f"{fit:.2f}", "fitted_minus_actual": f"{gap:.2f}",
        "actual_over_fitted": f"{actual / fit:.4f}", "crit_abs": gap > FLAG_ABS, "crit_rel": actual < FLAG_REL * fit,
        "flagged": flagged, "r_at_which_fitted_equals_actual": f"{r_matching:.3f}",
        "r_above_which_flagged": f"{r_flag:.3f}",
    }
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(result))
        w.writeheader()
        w.writerow(result)

    md = ["# Test 1: the Working Group's 2020 model applied to my 1 May 2020 record (PRIVATE)", "",
          f"Coefficients: Working Group report, Table 4 (`data/wg2021_table4_coefficients.csv`); worked example "
          f"reproduced ({ex:,.2f}).", "", "| Term | Value | Coefficient | Contribution |", "|---|---|---|---|"]
    md += [f"| {t} | {v:g} | {b:,.2f} | {v * b:,.2f} |" for t, v, b in ts]
    md += [f"| **Fitted salary** | | | **{fit:,.2f}** |", "",
           f"- Actual base salary, 1 May 2020: {actual:,.2f}",
           f"- Fitted minus actual: {gap:,.2f} (rule: more than 5,000) -> {'met' if gap > FLAG_ABS else 'not met'}",
           f"- Actual / fitted: {actual / fit:.1%} (rule: below 90%) -> {'met' if actual < FLAG_REL * fit else 'not met'}",
           f"- **Flagged under the full model: {'YES' if flagged else 'NO'}**", "",
           f"- Average R used: {r_avg:.3f} ({len(scores)} scores)",
           f"- Average R at which the model would predict exactly my salary: {r_matching:.3f}",
           f"- Average R above which my salary would be flagged: {r_flag:.3f}", ""]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[6:]))
    print(f"Wrote {OUT_CSV.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)} (private).")


if __name__ == "__main__":
    main()
