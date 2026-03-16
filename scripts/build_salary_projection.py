#!/usr/bin/env python3
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis_output"

VERIFY_PATH = ANALYSIS / "appendix_analysis_verification_matrix.csv"
LME4_PATH = ANALYSIS / "lme4_growth_model_summary_latex.csv"
MATCHED_PATH = ANALYSIS / "entry_cohort_growth_summary.csv"
OUT = ANALYSIS / "salary_projection_james_wallace.csv"


def to_float(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return float(s.replace("$", "").replace(",", ""))


def read_csv(path, delimiter=","):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def find_wallace_row(rows):
    for row in rows:
        name = str(row.get("Faculty", "")).upper()
        if "WALLACE" in name and "JAMES" in name:
            return row
    raise ValueError("Could not find James Wallace in verification matrix.")


def extract_years(row):
    year_cols = [c for c in row.keys() if c.strip().isdigit()]
    years = []
    for y in year_cols:
        val = to_float(row.get(y))
        if val is None:
            continue
        years.append((int(y), val))
    if not years:
        raise ValueError("No salary values found for James Wallace.")
    years.sort(key=lambda x: x[0])
    return years


def parse_lme4_gap(rows):
    for row in rows:
        term = str(row.get("term", "")).lower()
        if "mhi growth gap" in term or "year_c:mhi" in term:
            return to_float(row.get("estimate"))
    raise ValueError("Could not find MHI growth gap in lme4 summary.")


def parse_matched_gap(rows):
    for row in rows:
        analysis = str(row.get("analysis", "")).lower()
        if analysis.startswith("matched fe"):
            return to_float(row.get("estimate"))
    raise ValueError("Could not find matched FE estimate.")


def main():
    verify_rows = read_csv(VERIFY_PATH)
    wallace = find_wallace_row(verify_rows)
    years = extract_years(wallace)
    first_obs_year, first_obs_salary = years[0]
    t1, s1 = years[-1]

    start_year_raw = wallace.get("Start Year", "")
    start_year = int(str(start_year_raw).strip()) if str(start_year_raw).strip() else first_obs_year
    T = t1 - start_year

    lme4_rows = read_csv(LME4_PATH, delimiter=";")
    conservative_gap = parse_lme4_gap(lme4_rows)

    matched_rows = read_csv(MATCHED_PATH)
    matched_gap = parse_matched_gap(matched_rows)

    conservative_gap_abs = abs(conservative_gap)
    matched_gap_abs = abs(matched_gap)
    conservative_raise = conservative_gap_abs * T
    matched_raise = matched_gap_abs * T
    conservative_proj = s1 + conservative_raise
    matched_proj = s1 + matched_raise

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "name",
                "start_year",
                "first_obs_year",
                "first_obs_salary",
                "t1",
                "s1",
                "T",
                "conservative_gap",
                "conservative_gap_abs",
                "matched_gap",
                "matched_gap_abs",
                "conservative_raise",
                "matched_raise",
                "conservative_proj",
                "matched_proj",
            ]
        )
        w.writerow(
            [
                wallace.get("Faculty", "WALLACE JAMES R."),
                start_year,
                first_obs_year,
                f"{first_obs_salary:.2f}",
                t1,
                f"{s1:.2f}",
                T,
                f"{conservative_gap:.2f}",
                f"{conservative_gap_abs:.2f}",
                f"{matched_gap:.2f}",
                f"{matched_gap_abs:.2f}",
                f"{conservative_raise:.2f}",
                f"{matched_raise:.2f}",
                f"{conservative_proj:.2f}",
                f"{matched_proj:.2f}",
            ]
        )


if __name__ == "__main__":
    main()
