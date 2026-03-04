#!/usr/bin/env python3
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "sphs.csv"
PAIRS_PATH = ROOT / "analysis_output" / "entry_cohort_matched_pairs.csv"
OUT_PATH = ROOT / "analysis_output" / "plot_matched_model_trajectories.csv"
OUT_SCATTER_MHI_PATH = ROOT / "analysis_output" / "plot_matched_scatter_mhi.csv"
OUT_SCATTER_NONMHI_PATH = ROOT / "analysis_output" / "plot_matched_scatter_nonmhi.csv"


def norm(value: str) -> str:
    return "".join(value.strip().lower().split())


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def parse_salary_matrix():
    with DATA_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        surname_col = next(c for c in fieldnames if norm(c) in {"surname", "surame"})
        given_col = next(c for c in fieldnames if norm(c) == "givenname")
        mhi_col = next(c for c in fieldnames if norm(c) == "mhi")
        year_cols = [c for c in fieldnames if c.strip().isdigit()]

        records = []
        for row in reader:
            surname = row[surname_col].strip().upper()
            given = row[given_col].strip().upper()
            person_id = f"{surname}, {given}"
            mhi = parse_bool(row[mhi_col])
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
                        "mhi": 1.0 if mhi else 0.0,
                    }
                )
    return records


def load_matched_people():
    matched = set()
    with PAIRS_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            matched.add(row["mhi_person"])
            matched.add(row["non_mhi_person"])
    return matched


def invert_2x2(matrix):
    a, b = matrix[0]
    c, d = matrix[1]
    det = a * d - b * c
    if abs(det) < 1e-12:
        raise RuntimeError("Singular 2x2 matrix in FE fit.")
    inv_det = 1.0 / det
    return [[d * inv_det, -b * inv_det], [-c * inv_det, a * inv_det]]


def fit_matched_fe_slopes(records):
    by_person = {}
    for r in records:
        by_person.setdefault(r["person_id"], []).append(r)
    for person_rows in by_person.values():
        person_rows.sort(key=lambda x: x["year"])

    transformed_rows = []
    start_salaries = []

    for person, person_rows in by_person.items():
        if len(person_rows) < 2:
            continue
        first_year = person_rows[0]["year"]
        mhi = person_rows[0]["mhi"]
        years_since = [float(r["year"] - first_year) for r in person_rows]
        salaries = [float(r["salary"]) for r in person_rows]
        start_salaries.append(salaries[0])

        raw_x1 = years_since
        raw_x2 = [ys * mhi for ys in years_since]

        mean_x1 = sum(raw_x1) / len(raw_x1)
        mean_x2 = sum(raw_x2) / len(raw_x2)
        mean_y = sum(salaries) / len(salaries)

        for i in range(len(person_rows)):
            transformed_rows.append(
                {
                    "person_id": person,
                    "x": [raw_x1[i] - mean_x1, raw_x2[i] - mean_x2],
                    "y": salaries[i] - mean_y,
                }
            )

    n = len(transformed_rows)
    k = 2
    if n <= k:
        raise RuntimeError("Insufficient transformed observations in matched FE fit.")

    xtx = [[0.0, 0.0], [0.0, 0.0]]
    xty = [0.0, 0.0]
    for row in transformed_rows:
        x = row["x"]
        y = row["y"]
        xtx[0][0] += x[0] * x[0]
        xtx[0][1] += x[0] * x[1]
        xtx[1][0] += x[1] * x[0]
        xtx[1][1] += x[1] * x[1]
        xty[0] += x[0] * y
        xty[1] += x[1] * y

    xtx_inv = invert_2x2(xtx)
    beta_non = xtx_inv[0][0] * xty[0] + xtx_inv[0][1] * xty[1]
    beta_interaction = xtx_inv[1][0] * xty[0] + xtx_inv[1][1] * xty[1]

    residuals = []
    for row in transformed_rows:
        x = row["x"]
        fit = x[0] * beta_non + x[1] * beta_interaction
        residuals.append(row["y"] - fit)

    by_cluster = {}
    for idx, row in enumerate(transformed_rows):
        by_cluster.setdefault(row["person_id"], []).append(idx)
    g = len(by_cluster)
    if g <= 1:
        raise RuntimeError("Need at least two clusters for cluster-robust covariance.")

    meat = [[0.0, 0.0], [0.0, 0.0]]
    for indices in by_cluster.values():
        score = [0.0, 0.0]
        for idx in indices:
            x = transformed_rows[idx]["x"]
            e = residuals[idx]
            score[0] += x[0] * e
            score[1] += x[1] * e
        meat[0][0] += score[0] * score[0]
        meat[0][1] += score[0] * score[1]
        meat[1][0] += score[1] * score[0]
        meat[1][1] += score[1] * score[1]

    correction = (g / (g - 1.0)) * ((n - 1.0) / (n - k))
    a00 = xtx_inv[0][0] * meat[0][0] + xtx_inv[0][1] * meat[1][0]
    a01 = xtx_inv[0][0] * meat[0][1] + xtx_inv[0][1] * meat[1][1]
    a10 = xtx_inv[1][0] * meat[0][0] + xtx_inv[1][1] * meat[1][0]
    a11 = xtx_inv[1][0] * meat[0][1] + xtx_inv[1][1] * meat[1][1]

    cov00 = correction * (a00 * xtx_inv[0][0] + a01 * xtx_inv[1][0])
    cov01 = correction * (a00 * xtx_inv[0][1] + a01 * xtx_inv[1][1])
    cov10 = correction * (a10 * xtx_inv[0][0] + a11 * xtx_inv[1][0])
    cov11 = correction * (a10 * xtx_inv[0][1] + a11 * xtx_inv[1][1])
    cov = [[cov00, cov01], [cov10, cov11]]

    se_non = math.sqrt(max(cov[0][0], 0.0))
    interaction_var = cov[1][1]
    se_interaction = math.sqrt(max(interaction_var, 0.0))
    mhi_var = cov[0][0] + cov[1][1] + 2.0 * cov[0][1]
    se_mhi = math.sqrt(max(mhi_var, 0.0))

    common_start_salary = sum(start_salaries) / len(start_salaries)
    return {
        "beta_non": beta_non,
        "beta_interaction": beta_interaction,
        "se_non": se_non,
        "se_interaction": se_interaction,
        "se_mhi": se_mhi,
        "common_start_salary": common_start_salary,
    }


def build_matched_scatter_rows(records):
    by_person = {}
    for r in records:
        by_person.setdefault(r["person_id"], []).append(r)
    for person_rows in by_person.values():
        person_rows.sort(key=lambda x: x["year"])

    mhi_rows = []
    nonmhi_rows = []
    for person, person_rows in by_person.items():
        if not person_rows:
            continue
        first_year = person_rows[0]["year"]
        is_mhi = bool(person_rows[0]["mhi"])
        for row in person_rows:
            out_row = {
                "years_since_entry": int(row["year"] - first_year),
                "salary": f'{row["salary"]:.3f}',
                "faculty": person,
            }
            if is_mhi:
                mhi_rows.append(out_row)
            else:
                nonmhi_rows.append(out_row)
    return mhi_rows, nonmhi_rows


def main():
    all_records = parse_salary_matrix()
    matched_people = load_matched_people()
    matched_records = [r for r in all_records if r["person_id"] in matched_people]

    fit = fit_matched_fe_slopes(matched_records)
    beta_non = fit["beta_non"]
    est = fit["beta_interaction"]
    common_start_salary = fit["common_start_salary"]
    z = 1.96
    non_ci_low = beta_non - z * fit["se_non"]
    non_ci_high = beta_non + z * fit["se_non"]
    mhi_slope = beta_non + est
    mhi_ci_low_slope = mhi_slope - z * fit["se_mhi"]
    mhi_ci_high_slope = mhi_slope + z * fit["se_mhi"]
    int_ci_low = est - z * fit["se_interaction"]
    int_ci_high = est + z * fit["se_interaction"]

    horizon = 10
    rows = []
    for t in range(horizon + 1):
        non_fit = common_start_salary + beta_non * t
        non_low = common_start_salary + non_ci_low * t
        non_high = common_start_salary + non_ci_high * t
        mhi_fit = common_start_salary + mhi_slope * t
        mhi_ci_low = common_start_salary + mhi_ci_low_slope * t
        mhi_ci_high = common_start_salary + mhi_ci_high_slope * t
        gap_fit = est * t
        gap_ci_low = int_ci_low * t
        gap_ci_high = int_ci_high * t
        rows.append(
            {
                "years_since_entry": t,
                "nonmhi_fit": f"{non_fit:.3f}",
                "nonmhi_ci_low": f"{non_low:.3f}",
                "nonmhi_ci_high": f"{non_high:.3f}",
                "mhi_fit": f"{mhi_fit:.3f}",
                "mhi_ci_low": f"{mhi_ci_low:.3f}",
                "mhi_ci_high": f"{mhi_ci_high:.3f}",
                "gap_fit": f"{gap_fit:.3f}",
                "gap_ci_low": f"{gap_ci_low:.3f}",
                "gap_ci_high": f"{gap_ci_high:.3f}",
            }
        )

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "years_since_entry",
                "nonmhi_fit",
                "nonmhi_ci_low",
                "nonmhi_ci_high",
                "mhi_fit",
                "mhi_ci_low",
                "mhi_ci_high",
                "gap_fit",
                "gap_ci_low",
                "gap_ci_high",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    scatter_mhi, scatter_nonmhi = build_matched_scatter_rows(matched_records)
    with OUT_SCATTER_MHI_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["years_since_entry", "salary", "faculty"])
        writer.writeheader()
        writer.writerows(scatter_mhi)
    with OUT_SCATTER_NONMHI_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["years_since_entry", "salary", "faculty"])
        writer.writeheader()
        writer.writerows(scatter_nonmhi)

    print(f"Wrote matched model trajectory data: {OUT_PATH}")
    print(f"Wrote matched MHI scatter data: {OUT_SCATTER_MHI_PATH}")
    print(f"Wrote matched non-MHI scatter data: {OUT_SCATTER_NONMHI_PATH}")
    print(
        "Model summary:",
        f"non-MHI slope={beta_non:.3f},",
        f"matched FE slope gap={est:.3f},",
        f"95% CI=[{int_ci_low:.3f}, {int_ci_high:.3f}]",
    )


if __name__ == "__main__":
    main()
