#!/usr/bin/env python3
"""
Build skeptic-focused appendix outputs.

Outputs:
- analysis_output/appendix_skeptic_specification_grid.csv
- analysis_output/appendix_skeptic_permutation_placebo.csv
- analysis_output/appendix_skeptic_leave_one_pair_out.csv
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis_output"
DATA = ROOT / "data" / "sphs.csv"

ENTRY_GROWTH_MAIN = ANALYSIS / "entry_cohort_growth_summary.csv"
ENTRY_GROWTH_DISCLOSURE = ANALYSIS / "entry_cohort_growth_summary_disclosure_start.csv"
ENTRY_PERM_MAIN = ANALYSIS / "entry_cohort_permutation_summary.csv"
ENTRY_PERM_DISCLOSURE = ANALYSIS / "entry_cohort_permutation_summary_disclosure_start.csv"
REGRESSION_SUMMARY = ANALYSIS / "regression_summary.csv"
PERM_SUMMARY = ANALYSIS / "permutation_inference_summary.csv"
MATCHED_PAIRS_MAIN = ANALYSIS / "entry_cohort_matched_pairs.csv"

SPEC_GRID_OUT = ANALYSIS / "appendix_skeptic_specification_grid.csv"
PLACEBO_OUT = ANALYSIS / "appendix_skeptic_permutation_placebo.csv"
LEAVE_ONE_OUT = ANALYSIS / "appendix_skeptic_leave_one_pair_out.csv"


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(value: str) -> Optional[float]:
    raw = (value or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def to_int(value: str) -> Optional[int]:
    raw = (value or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def fmt(value: Optional[float], digits: int = 3) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def norm_header(value: str) -> str:
    return "".join((value or "").strip().lower().split())


def parse_bool(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def find_row(rows: Iterable[Dict[str, str]], **filters: str) -> Optional[Dict[str, str]]:
    for row in rows:
        if all((row.get(k, "") == v for k, v in filters.items())):
            return row
    return None


def build_specification_grid() -> List[Dict[str, str]]:
    entry_main = read_csv(ENTRY_GROWTH_MAIN)
    entry_main_perm = read_csv(ENTRY_PERM_MAIN)
    entry_disclosure = read_csv(ENTRY_GROWTH_DISCLOSURE)
    entry_disclosure_perm = read_csv(ENTRY_PERM_DISCLOSURE)
    regression = read_csv(REGRESSION_SUMMARY)
    regression_perm = read_csv(PERM_SUMMARY)

    specs: List[Tuple[str, str, str, str]] = [
        ("Matched FE (±1 year)", "Matched set", "cv-or-disclosure", "main"),
        ("Matched FE (±1 year)", "Matched set", "disclosure-only", "disclosure"),
        ("Within-cohort FE", "2017-2019", "cv-or-disclosure", "main"),
        ("Within-cohort FE", "2017-2019", "disclosure-only", "disclosure"),
        ("Pooled with entry-cohort FE", "All cohorts", "cv-or-disclosure", "main"),
        ("Pooled with entry-cohort FE", "All cohorts", "disclosure-only", "disclosure"),
    ]

    out_rows: List[Dict[str, str]] = []
    for analysis, bucket, start_rule, which in specs:
        growth_rows = entry_main if which == "main" else entry_disclosure
        perm_rows = entry_main_perm if which == "main" else entry_disclosure_perm

        summary = find_row(growth_rows, analysis=analysis, cohort_bucket=bucket)
        perm = find_row(perm_rows, analysis=analysis, cohort_bucket=bucket)
        if summary is None:
            continue

        out_rows.append(
            {
                "model_check": analysis,
                "cohort_bucket": bucket,
                "start_year_rule": start_rule,
                "estimate": summary.get("estimate", ""),
                "std_error": summary.get("std_error", ""),
                "ci_low": summary.get("ci_low", ""),
                "ci_high": summary.get("ci_high", ""),
                "p_two_sided": perm.get("p_two_sided", "") if perm else "",
                "n_permutations": perm.get("n_permutations", "") if perm else "",
                "n_obs": summary.get("n_obs", ""),
                "n_clusters": summary.get("n_clusters", ""),
                "n_treated_clusters": summary.get("n_treated_clusters", ""),
            }
        )

    base_fe = find_row(regression, model="Person FE", term="MHI - Non-MHI annual slope")
    base_perm = find_row(regression_perm, model="Person FE", term="MHI - Non-MHI annual slope")
    if base_fe is not None and base_perm is not None:
        out_rows.append(
            {
                "model_check": "Person FE (baseline)",
                "cohort_bucket": "All years",
                "start_year_rule": "not applicable",
                "estimate": base_fe.get("estimate", ""),
                "std_error": base_fe.get("std_error", ""),
                "ci_low": base_fe.get("ci_lower", ""),
                "ci_high": base_fe.get("ci_upper", ""),
                "p_two_sided": base_perm.get("p_two_sided", ""),
                "n_permutations": base_perm.get("n_permutations", ""),
                "n_obs": base_fe.get("n_obs", ""),
                "n_clusters": base_fe.get("n_clusters", ""),
                "n_treated_clusters": base_perm.get("n_treated_clusters", ""),
            }
        )

    return out_rows


def build_permutation_placebo_rows(spec_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    entry_main_perm = read_csv(ENTRY_PERM_MAIN)
    entry_disclosure_perm = read_csv(ENTRY_PERM_DISCLOSURE)
    regression_perm = read_csv(PERM_SUMMARY)

    out_rows: List[Dict[str, str]] = []

    for row in spec_rows:
        model_check = row["model_check"]
        bucket = row["cohort_bucket"]
        start_rule = row["start_year_rule"]

        if model_check == "Person FE (baseline)":
            perm = find_row(regression_perm, model="Person FE", term="MHI - Non-MHI annual slope")
            if perm is None:
                continue
            out_rows.append(
                {
                    "model_check": model_check,
                    "cohort_bucket": bucket,
                    "start_year_rule": start_rule,
                    "observed_estimate": perm.get("observed_estimate", ""),
                    "null_q025": perm.get("null_q025", ""),
                    "null_q975": perm.get("null_q975", ""),
                    "null_std_dev": perm.get("null_std_dev", ""),
                    "p_two_sided": perm.get("p_two_sided", ""),
                    "n_permutations": perm.get("n_permutations", ""),
                    "inference_method": perm.get("inference_method", ""),
                }
            )
            continue

        perm_rows = entry_main_perm if start_rule == "cv-or-disclosure" else entry_disclosure_perm
        perm = find_row(perm_rows, analysis=model_check, cohort_bucket=bucket)
        if perm is None:
            continue
        out_rows.append(
            {
                "model_check": model_check,
                "cohort_bucket": bucket,
                "start_year_rule": start_rule,
                "observed_estimate": perm.get("observed_estimate", ""),
                "null_q025": perm.get("null_q025", ""),
                "null_q975": perm.get("null_q975", ""),
                "null_std_dev": perm.get("null_std_dev", ""),
                "p_two_sided": perm.get("p_two_sided", ""),
                "n_permutations": perm.get("n_permutations", ""),
                "inference_method": perm.get("inference_method", ""),
            }
        )

    return out_rows


def load_salary_records() -> List[Dict[str, object]]:
    rows = read_csv(DATA)
    if not rows:
        return []
    fields = list(rows[0].keys())
    surname_col = next(c for c in fields if norm_header(c) in {"surname", "surame"})
    given_col = next(c for c in fields if norm_header(c) == "givenname")
    mhi_col = next(c for c in fields if norm_header(c) == "mhi")
    year_cols = sorted((c for c in fields if (c or "").strip().isdigit()), key=lambda y: int(y))

    records: List[Dict[str, object]] = []
    for row in rows:
        surname = (row.get(surname_col) or "").strip().upper()
        given = (row.get(given_col) or "").strip().upper()
        if not surname or not given:
            continue
        person_id = f"{surname}, {given}"
        mhi = 1.0 if parse_bool(row.get(mhi_col, "")) else 0.0
        for yc in year_cols:
            raw = (row.get(yc) or "").strip()
            if not raw:
                continue
            salary = float(raw.replace("$", "").replace(",", ""))
            records.append(
                {
                    "person_id": person_id,
                    "year": int(yc),
                    "salary": salary,
                    "mhi": mhi,
                }
            )
    return records


def load_pair_rows() -> List[Dict[str, str]]:
    return read_csv(MATCHED_PAIRS_MAIN)


def mat_mul_2x2(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    return [
        [a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1]],
        [a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1]],
    ]


def mat_scale_2x2(a: List[List[float]], scalar: float) -> List[List[float]]:
    return [
        [a[0][0] * scalar, a[0][1] * scalar],
        [a[1][0] * scalar, a[1][1] * scalar],
    ]


def invert_2x2(a: List[List[float]]) -> Optional[List[List[float]]]:
    det = a[0][0] * a[1][1] - a[0][1] * a[1][0]
    if abs(det) < 1e-12:
        return None
    inv_det = 1.0 / det
    return [
        [a[1][1] * inv_det, -a[0][1] * inv_det],
        [-a[1][0] * inv_det, a[0][0] * inv_det],
    ]


def fit_matched_fe(
    records: List[Dict[str, object]],
    first_year_by_person: Dict[str, int],
    include_people: Iterable[str],
) -> Optional[Dict[str, float]]:
    include = set(include_people)
    subset = [r for r in records if r["person_id"] in include and r["person_id"] in first_year_by_person]
    by_person: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in subset:
        by_person[str(row["person_id"])].append(row)

    x_rows: List[Tuple[float, float]] = []
    y_vals: List[float] = []
    cluster_ids: List[str] = []
    mhi_by_person: Dict[str, float] = {}

    for person_id, person_rows in by_person.items():
        if len(person_rows) < 2:
            continue
        first_year = first_year_by_person.get(person_id)
        if first_year is None:
            continue
        sorted_rows = sorted(person_rows, key=lambda r: int(r["year"]))
        mhi = float(sorted_rows[0]["mhi"])
        mhi_by_person[person_id] = mhi

        raw_x1 = [float(int(r["year"]) - first_year) for r in sorted_rows]
        raw_x2 = [x * mhi for x in raw_x1]
        raw_y = [float(r["salary"]) for r in sorted_rows]

        mean_x1 = sum(raw_x1) / len(raw_x1)
        mean_x2 = sum(raw_x2) / len(raw_x2)
        mean_y = sum(raw_y) / len(raw_y)

        for x1, x2, y in zip(raw_x1, raw_x2, raw_y):
            x_rows.append((x1 - mean_x1, x2 - mean_x2))
            y_vals.append(y - mean_y)
            cluster_ids.append(person_id)

    n = len(y_vals)
    k = 2
    if n <= k:
        return None

    xtx = [[0.0, 0.0], [0.0, 0.0]]
    xty = [0.0, 0.0]
    for (x1, x2), y in zip(x_rows, y_vals):
        xtx[0][0] += x1 * x1
        xtx[0][1] += x1 * x2
        xtx[1][0] += x2 * x1
        xtx[1][1] += x2 * x2
        xty[0] += x1 * y
        xty[1] += x2 * y

    xtx_inv = invert_2x2(xtx)
    if xtx_inv is None:
        return None

    beta0 = xtx_inv[0][0] * xty[0] + xtx_inv[0][1] * xty[1]
    beta1 = xtx_inv[1][0] * xty[0] + xtx_inv[1][1] * xty[1]

    residuals: List[float] = []
    for (x1, x2), y in zip(x_rows, y_vals):
        residuals.append(y - (beta0 * x1 + beta1 * x2))

    cluster_to_indices: Dict[str, List[int]] = defaultdict(list)
    for idx, cluster in enumerate(cluster_ids):
        cluster_to_indices[cluster].append(idx)
    g = len(cluster_to_indices)
    if g <= 1:
        return None

    meat = [[0.0, 0.0], [0.0, 0.0]]
    for idxs in cluster_to_indices.values():
        s0 = 0.0
        s1 = 0.0
        for i in idxs:
            s0 += x_rows[i][0] * residuals[i]
            s1 += x_rows[i][1] * residuals[i]
        meat[0][0] += s0 * s0
        meat[0][1] += s0 * s1
        meat[1][0] += s1 * s0
        meat[1][1] += s1 * s1

    correction = (g / (g - 1.0)) * ((n - 1.0) / (n - k))
    covariance = mat_scale_2x2(mat_mul_2x2(mat_mul_2x2(xtx_inv, meat), xtx_inv), correction)
    se1 = math.sqrt(max(covariance[1][1], 0.0))
    if se1 > 0:
        z = beta1 / se1
        p_two = math.erfc(abs(z) / math.sqrt(2.0))
    else:
        p_two = float("nan")
    ci_low = beta1 - 1.96 * se1
    ci_high = beta1 + 1.96 * se1

    treated_clusters = sum(1 for pid in cluster_to_indices if mhi_by_person.get(pid) == 1.0)
    return {
        "estimate": beta1,
        "std_error": se1,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_two_sided": p_two,
        "n_obs": float(n),
        "n_clusters": float(g),
        "n_treated_clusters": float(treated_clusters),
    }


def build_leave_one_out_rows() -> List[Dict[str, str]]:
    records = load_salary_records()
    pairs = load_pair_rows()
    if not records or not pairs:
        return []

    first_year_by_person: Dict[str, int] = {}
    all_people: List[str] = []
    for p in pairs:
        mhi_person = p.get("mhi_person", "")
        non_person = p.get("non_mhi_person", "")
        mhi_year = to_int(p.get("mhi_first_year", ""))
        non_year = to_int(p.get("non_mhi_first_year", ""))
        if mhi_person and mhi_year is not None:
            first_year_by_person[mhi_person] = mhi_year
            all_people.append(mhi_person)
        if non_person and non_year is not None:
            first_year_by_person[non_person] = non_year
            all_people.append(non_person)

    all_people_set = set(all_people)
    full_fit = fit_matched_fe(records, first_year_by_person, all_people_set)
    if full_fit is None:
        return []

    rows: List[Dict[str, str]] = [
        {
            "removed_pair": "None (full matched sample)",
            "estimate": fmt(full_fit["estimate"]),
            "std_error": fmt(full_fit["std_error"]),
            "ci_low": fmt(full_fit["ci_low"]),
            "ci_high": fmt(full_fit["ci_high"]),
            "p_two_sided": fmt(full_fit["p_two_sided"]),
            "delta_vs_full": "0.000",
            "n_obs": str(int(full_fit["n_obs"])),
            "n_clusters": str(int(full_fit["n_clusters"])),
            "n_treated_clusters": str(int(full_fit["n_treated_clusters"])),
        }
    ]

    for p in pairs:
        mhi_person = p.get("mhi_person", "")
        non_person = p.get("non_mhi_person", "")
        remove_set = {mhi_person, non_person}
        include_people = sorted(all_people_set - remove_set)
        fit = fit_matched_fe(records, first_year_by_person, include_people)
        if fit is None:
            continue
        delta = fit["estimate"] - full_fit["estimate"]
        left_label = mhi_person.replace(",", " |")
        right_label = non_person.replace(",", " |")
        rows.append(
            {
                "removed_pair": f"{left_label} vs {right_label}",
                "estimate": fmt(fit["estimate"]),
                "std_error": fmt(fit["std_error"]),
                "ci_low": fmt(fit["ci_low"]),
                "ci_high": fmt(fit["ci_high"]),
                "p_two_sided": fmt(fit["p_two_sided"]),
                "delta_vs_full": fmt(delta),
                "n_obs": str(int(fit["n_obs"])),
                "n_clusters": str(int(fit["n_clusters"])),
                "n_treated_clusters": str(int(fit["n_treated_clusters"])),
            }
        )

    # Keep full row first; then sort leave-one-out rows by absolute perturbation.
    header = rows[0]
    rest = rows[1:]
    rest.sort(key=lambda r: abs(to_float(r["delta_vs_full"]) or 0.0), reverse=True)
    return [header] + rest


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    spec_rows = build_specification_grid()
    write_csv(
        SPEC_GRID_OUT,
        spec_rows,
        [
            "model_check",
            "cohort_bucket",
            "start_year_rule",
            "estimate",
            "std_error",
            "ci_low",
            "ci_high",
            "p_two_sided",
            "n_permutations",
            "n_obs",
            "n_clusters",
            "n_treated_clusters",
        ],
    )

    placebo_rows = build_permutation_placebo_rows(spec_rows)
    write_csv(
        PLACEBO_OUT,
        placebo_rows,
        [
            "model_check",
            "cohort_bucket",
            "start_year_rule",
            "observed_estimate",
            "null_q025",
            "null_q975",
            "null_std_dev",
            "p_two_sided",
            "n_permutations",
            "inference_method",
        ],
    )

    loo_rows = build_leave_one_out_rows()
    write_csv(
        LEAVE_ONE_OUT,
        loo_rows,
        [
            "removed_pair",
            "estimate",
            "std_error",
            "ci_low",
            "ci_high",
            "p_two_sided",
            "delta_vs_full",
            "n_obs",
            "n_clusters",
            "n_treated_clusters",
        ],
    )

    print(f"Wrote skeptic specification grid: {SPEC_GRID_OUT}")
    print(f"Wrote skeptic permutation placebo table: {PLACEBO_OUT}")
    print(f"Wrote skeptic leave-one-out table: {LEAVE_ONE_OUT}")


if __name__ == "__main__":
    main()
