#!/usr/bin/env python3
import csv
import random
import re
from math import ceil, erf, floor, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "sphs.csv"
OUT = ROOT / "analysis_output"
SPHS_LIST = ROOT / "SalaryData" / "SPHS Faculty List.swift"

FOCUSED_MHI = {
    "BUTT, ZAHID",
    "CHAURASIA, ASHOK",
    "CHEN, HELEN H.",
    "LEE, JOON",
    "LEE, JOON H.",
    "LUO, HAO",
    "MCKILLOP, IAN",
    "MORITA, PLINIO",
    "TORRES ESPIN, ABEL",
    "WALLACE, JAMES R.",
}


def canon(name: str) -> str:
    return " ".join(name.strip().upper().split())


def load_allowed_faculty() -> set[str]:
    text = SPHS_LIST.read_text(encoding="utf-8")
    names = re.findall(r'"([^"\n]+)"', text)
    return {canon(name) for name in names}


def transpose(m):
    return [list(row) for row in zip(*m)]


def matmul(a, b):
    out = [[0.0 for _ in range(len(b[0]))] for _ in range(len(a))]
    for i in range(len(a)):
        for j in range(len(b[0])):
            s = 0.0
            for k in range(len(b)):
                s += a[i][k] * b[k][j]
            out[i][j] = s
    return out


def matvec(a, v):
    return [sum(a[i][j] * v[j] for j in range(len(v))) for i in range(len(a))]


def invert(a):
    n = len(a)
    m = [row[:] for row in a]
    inv = [[0.0] * n for _ in range(n)]
    for i in range(n):
        inv[i][i] = 1.0

    for i in range(n):
        pivot = i
        for r in range(i, n):
            if abs(m[r][i]) > abs(m[pivot][i]):
                pivot = r
        if abs(m[pivot][i]) < 1e-12:
            raise ValueError("Singular matrix")
        if pivot != i:
            m[i], m[pivot] = m[pivot], m[i]
            inv[i], inv[pivot] = inv[pivot], inv[i]

        p = m[i][i]
        for j in range(n):
            m[i][j] /= p
            inv[i][j] /= p

        for r in range(n):
            if r == i:
                continue
            f = m[r][i]
            for c in range(n):
                m[r][c] -= f * m[i][c]
                inv[r][c] -= f * inv[i][c]
    return inv


def outer(u, v):
    return [[u[i] * v[j] for j in range(len(v))] for i in range(len(u))]


def add_in_place(a, b):
    for i in range(len(a)):
        for j in range(len(a[0])):
            a[i][j] += b[i][j]


def read_long_rows():
    rows = []
    allowed = load_allowed_faculty()
    with INPUT.open(newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r)
        norm = [h.strip().lower().replace(" ", "") for h in header]
        surname_idx = 0
        given_idx = 1
        year_cols = []
        for idx, h in enumerate(norm):
            try:
                y = int(h)
                if 2011 <= y <= 2100:
                    year_cols.append((idx, y))
            except ValueError:
                pass

        for rec in r:
            if len(rec) < 3:
                continue
            surname = rec[surname_idx].strip()
            given = rec[given_idx].strip()
            if not surname or not given:
                continue
            person = f"{surname}, {given}"
            if canon(person) not in allowed:
                continue
            mhi = 1.0 if canon(person) in FOCUSED_MHI else 0.0
            for idx, year in year_cols:
                if idx >= len(rec):
                    continue
                raw = rec[idx].strip()
                if not raw:
                    continue
                salary = float(raw.replace("$", "").replace(",", ""))
                rows.append({
                    "person": person,
                    "year": year,
                    "salary": salary,
                    "mhi": mhi,
                })
    return rows


def pooled_cluster_robust(rows):
    min_year = min(r["year"] for r in rows)
    X = []
    y = []
    clusters = []
    for r in rows:
        yc = float(r["year"] - min_year)
        m = r["mhi"]
        X.append([1.0, yc, m, yc * m])
        y.append(r["salary"])
        clusters.append(r["person"])

    Xt = transpose(X)
    XtX = matmul(Xt, X)
    XtX_inv = invert(XtX)
    Xty = [sum(Xt[i][j] * y[j] for j in range(len(y))) for i in range(len(Xt))]
    beta = matvec(XtX_inv, Xty)

    resid = []
    for i, row in enumerate(X):
        fit = sum(row[j] * beta[j] for j in range(4))
        resid.append(y[i] - fit)

    by_cluster = {}
    for i, c in enumerate(clusters):
        by_cluster.setdefault(c, []).append(i)

    k = 4
    meat = [[0.0] * k for _ in range(k)]
    for idxs in by_cluster.values():
        score = [0.0] * k
        for i in idxs:
            for j in range(k):
                score[j] += X[i][j] * resid[i]
        add_in_place(meat, outer(score, score))

    n = float(len(X))
    g = float(len(by_cluster))
    kf = float(k)
    correction = (g / (g - 1.0)) * ((n - 1.0) / (n - kf))
    cov = matmul(matmul(XtX_inv, meat), XtX_inv)
    for i in range(k):
        for j in range(k):
            cov[i][j] *= correction

    return beta, cov, min_year


def quadform(x, cov):
    tmp = [sum(cov[i][j] * x[j] for j in range(len(x))) for i in range(len(x))]
    return sum(x[i] * tmp[i] for i in range(len(x)))


def write_plot_data(rows, beta, cov, min_year):
    OUT.mkdir(parents=True, exist_ok=True)

    mhi_rows = [r for r in rows if r["mhi"] == 1.0]
    non_rows = [r for r in rows if r["mhi"] == 0.0]

    with (OUT / "plot_scatter_mhi.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "salary", "faculty"])
        for r in mhi_rows:
            w.writerow([r["year"], f"{r['salary']:.2f}", r["person"]])

    with (OUT / "plot_scatter_nonmhi.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "salary", "faculty"])
        for r in non_rows:
            w.writerow([r["year"], f"{r['salary']:.2f}", r["person"]])

    min_y = min(r["year"] for r in rows)
    max_y = max(r["year"] for r in rows)

    def trend_row(year, m):
        yc = float(year - min_year)
        x = [1.0, yc, m, yc * m]
        fit = sum(x[i] * beta[i] for i in range(4))
        se = sqrt(max(quadform(x, cov), 0.0))
        return [year, f"{fit:.3f}", f"{(fit - 1.96 * se):.3f}", f"{(fit + 1.96 * se):.3f}"]

    with (OUT / "plot_trend_nonmhi.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "fit", "ci_low", "ci_high"])
        for yr in range(min_y, max_y + 1):
            w.writerow(trend_row(yr, 0.0))

    with (OUT / "plot_trend_mhi.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "fit", "ci_low", "ci_high"])
        for yr in range(min_y, max_y + 1):
            w.writerow(trend_row(yr, 1.0))


def _median(values: list[float]) -> float:
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        raise ValueError("Cannot compute median of empty list")
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def _write_histogram_pair(mhi_adj: list[float], non_adj: list[float], stem: str, bin_width: float) -> None:
    all_adj = mhi_adj + non_adj
    if not all_adj:
        return

    min_v = min(all_adj)
    max_v = max(all_adj)
    start = floor(min_v / bin_width) * bin_width
    end = ceil(max_v / bin_width) * bin_width
    if end <= start:
        end = start + bin_width

    n_bins = int(round((end - start) / bin_width))
    edges = [start + i * bin_width for i in range(n_bins + 1)]

    def bin_counts(values):
        counts = [0] * n_bins
        for v in values:
            idx = int((v - start) // bin_width)
            if idx < 0:
                idx = 0
            if idx >= n_bins:
                idx = n_bins - 1
            counts[idx] += 1
        total = float(len(values)) if values else 1.0
        out = []
        for i in range(n_bins):
            left = edges[i]
            right = edges[i + 1]
            mid = (left + right) / 2.0
            c = counts[i]
            out.append([f"{left:.2f}", f"{right:.2f}", f"{mid:.2f}", c, f"{(c / total):.6f}"])
        return out

    with (OUT / f"plot_hist_year_adj_{stem}_mhi.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bin_left", "bin_right", "bin_mid", "count", "share"])
        for row in bin_counts(mhi_adj):
            w.writerow(row)

    with (OUT / f"plot_hist_year_adj_{stem}_nonmhi.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bin_left", "bin_right", "bin_mid", "count", "share"])
        for row in bin_counts(non_adj):
            w.writerow(row)


def write_year_adjusted_hist_data(rows, bin_width: float = 5000.0):
    # Year-adjust each salary by subtracting that year's pooled center
    # (mean for sensitivity, median for the main figure).
    by_year = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r["salary"])

    year_means = {yr: (sum(vals) / float(len(vals))) for yr, vals in by_year.items()}
    year_medians = {yr: _median(vals) for yr, vals in by_year.items()}

    def adjusted(center_by_year):
        mhi_adj = []
        non_adj = []
        for r in rows:
            v = r["salary"] - center_by_year[r["year"]]
            if r["mhi"] == 1.0:
                mhi_adj.append(v)
            else:
                non_adj.append(v)
        return mhi_adj, non_adj

    median_mhi, median_non = adjusted(year_medians)
    mean_mhi, mean_non = adjusted(year_means)

    _write_histogram_pair(median_mhi, median_non, stem="median", bin_width=bin_width)
    _write_histogram_pair(mean_mhi, mean_non, stem="mean", bin_width=bin_width)

    def summarize(values):
        eps = 1e-9
        below = sum(1 for v in values if v < -eps)
        above = sum(1 for v in values if v > eps)
        equal = len(values) - below - above
        return below, above, equal, len(values)

    median_below, median_above, median_equal, median_total = summarize(median_mhi)
    mean_below, mean_above, mean_equal, mean_total = summarize(mean_mhi)

    with (OUT / "plot_hist_year_adj_mhi_counts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "mhi_below_center", "mhi_above_center", "mhi_equal_center", "mhi_total"])
        w.writerow(["median", median_below, median_above, median_equal, median_total])
        w.writerow(["mean", mean_below, mean_above, mean_equal, mean_total])

    return {
        "median": {"below": median_below, "above": median_above, "equal": median_equal, "total": median_total},
        "mean": {"below": mean_below, "above": mean_above, "equal": mean_equal, "total": mean_total},
    }


def write_yearly_percentile_cdf(rows):
    # For each year: rank salaries ascending and convert rank to percentile rank/n.
    by_year = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r)

    mhi_percentiles = []
    non_percentiles = []
    mhi_below_year_median = 0
    mhi_total = 0
    non_below_year_median = 0
    non_total = 0
    binary_obs = []

    for year_rows in by_year.values():
        ordered = sorted(year_rows, key=lambda x: (x["salary"], x["person"]))
        n = len(ordered)
        if n == 0:
            continue
        year_median = _median([r["salary"] for r in ordered])

        for i, r in enumerate(ordered, start=1):
            pct = i / float(n)
            below_p50 = 1 if pct < 0.5 else 0
            if r["mhi"] == 1.0:
                mhi_percentiles.append(pct * 100.0)
                mhi_total += 1
                if r["salary"] < year_median:
                    mhi_below_year_median += 1
            else:
                non_percentiles.append(pct * 100.0)
                non_total += 1
                if r["salary"] < year_median:
                    non_below_year_median += 1
            binary_obs.append(
                {
                    "person": r["person"],
                    "mhi": 1 if r["mhi"] == 1.0 else 0,
                    "below_p50": below_p50,
                }
            )

    def write_group_cdf(values, path):
        vals = sorted(values)
        total = len(vals)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["salary_percentile", "cum_prop"])
            w.writerow(["0.00", "0.000000"])
            if total == 0:
                w.writerow(["100.00", "1.000000"])
                return
            cum = 0
            i = 0
            while i < total:
                x = vals[i]
                j = i
                while j < total and abs(vals[j] - x) < 1e-12:
                    j += 1
                cum = j
                w.writerow([f"{x:.6f}", f"{(cum / float(total)):.6f}"])
                i = j
            if vals[-1] < 100.0 - 1e-12:
                w.writerow(["100.00", "1.000000"])

    write_group_cdf(mhi_percentiles, OUT / "plot_percentile_cdf_mhi.csv")
    write_group_cdf(non_percentiles, OUT / "plot_percentile_cdf_nonmhi.csv")

    def summarize_percentiles(values):
        n = len(values)
        if n == 0:
            return {"n": 0, "mean": 0.0, "median": 0.0, "below_p50_n": 0, "below_p50_pct": 0.0}
        below_p50_n = sum(1 for v in values if v < 50.0)
        return {
            "n": n,
            "mean": sum(values) / float(n),
            "median": _median(values),
            "below_p50_n": below_p50_n,
            "below_p50_pct": 100.0 * below_p50_n / float(n),
        }

    mhi_stats = summarize_percentiles(mhi_percentiles)
    non_stats = summarize_percentiles(non_percentiles)

    mhi_below_year_median_pct = (100.0 * mhi_below_year_median / float(mhi_total)) if mhi_total else 0.0
    non_below_year_median_pct = (100.0 * non_below_year_median / float(non_total)) if non_total else 0.0

    mhi_below_p50_n = mhi_stats["below_p50_n"]
    non_below_p50_n = non_stats["below_p50_n"]
    mhi_n = mhi_stats["n"]
    non_n = non_stats["n"]
    observed_diff = (mhi_below_p50_n / float(mhi_n)) - (non_below_p50_n / float(non_n))

    pooled = (mhi_below_p50_n + non_below_p50_n) / float(mhi_n + non_n)
    z_se = sqrt(max(pooled * (1.0 - pooled) * ((1.0 / mhi_n) + (1.0 / non_n)), 0.0))
    z_stat = (observed_diff / z_se) if z_se > 0 else 0.0
    z_one_sided = 1.0 - _normal_cdf(z_stat)
    z_two_sided = 2.0 * min(_normal_cdf(z_stat), 1.0 - _normal_cdf(z_stat))

    by_person = {}
    for ob in binary_obs:
        p = ob["person"]
        rec = by_person.setdefault(p, {"mhi": ob["mhi"], "n_obs": 0, "below_n": 0})
        rec["n_obs"] += 1
        rec["below_n"] += ob["below_p50"]

    people = list(by_person.keys())
    mhi_people_count = sum(1 for p in people if by_person[p]["mhi"] == 1)

    person_stats = []
    mhi_rates = []
    non_rates = []
    for p in people:
        rec = by_person[p]
        person_stats.append((p, rec["n_obs"], rec["below_n"]))
        rate = rec["below_n"] / float(rec["n_obs"])
        if rec["mhi"] == 1:
            mhi_rates.append(rate)
        else:
            non_rates.append(rate)

    observed_faculty_diff = (sum(mhi_rates) / float(len(mhi_rates))) - (sum(non_rates) / float(len(non_rates)))

    n_permutations = 50000
    rnd = random.Random(12345)

    ge_w_one = 0
    ge_w_two = 0
    ge_f_one = 0
    ge_f_two = 0

    for _ in range(n_permutations):
        chosen = set(rnd.sample(people, mhi_people_count))

        m_obs = 0
        m_below = 0
        n_obs = 0
        n_below = 0
        m_fac_rates = []
        n_fac_rates = []

        for p, n_i, b_i in person_stats:
            rate_i = b_i / float(n_i)
            if p in chosen:
                m_obs += n_i
                m_below += b_i
                m_fac_rates.append(rate_i)
            else:
                n_obs += n_i
                n_below += b_i
                n_fac_rates.append(rate_i)

        d_weighted = (m_below / float(m_obs)) - (n_below / float(n_obs))
        d_faculty = (sum(m_fac_rates) / float(len(m_fac_rates))) - (sum(n_fac_rates) / float(len(n_fac_rates)))

        if d_weighted >= observed_diff - 1e-15:
            ge_w_one += 1
        if abs(d_weighted) >= abs(observed_diff) - 1e-15:
            ge_w_two += 1
        if d_faculty >= observed_faculty_diff - 1e-15:
            ge_f_one += 1
        if abs(d_faculty) >= abs(observed_faculty_diff) - 1e-15:
            ge_f_two += 1

    weighted_p_one = (ge_w_one + 1.0) / float(n_permutations + 1)
    weighted_p_two = (ge_w_two + 1.0) / float(n_permutations + 1)
    faculty_p_one = (ge_f_one + 1.0) / float(n_permutations + 1)
    faculty_p_two = (ge_f_two + 1.0) / float(n_permutations + 1)

    with (OUT / "plot_percentile_binary_tests.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "test",
                "estimand",
                "observed_diff_pp",
                "p_one_sided",
                "p_two_sided",
                "n_permutations",
                "mhi_below_p50_pct",
                "nonmhi_below_p50_pct",
            ]
        )
        w.writerow(
            [
                "Naive two-proportion z",
                "Person-year weighted rate difference",
                f"{100.0 * observed_diff:.2f}",
                f"{z_one_sided:.6f}",
                f"{z_two_sided:.6f}",
                "",
                f"{mhi_stats['below_p50_pct']:.2f}",
                f"{non_stats['below_p50_pct']:.2f}",
            ]
        )
        w.writerow(
            [
                "Cluster permutation (weighted)",
                "Person-year weighted rate difference",
                f"{100.0 * observed_diff:.2f}",
                f"{weighted_p_one:.6f}",
                f"{weighted_p_two:.6f}",
                n_permutations,
                f"{mhi_stats['below_p50_pct']:.2f}",
                f"{non_stats['below_p50_pct']:.2f}",
            ]
        )
        w.writerow(
            [
                "Cluster permutation (faculty mean)",
                "Faculty-mean rate difference",
                f"{100.0 * observed_faculty_diff:.2f}",
                f"{faculty_p_one:.6f}",
                f"{faculty_p_two:.6f}",
                n_permutations,
                f"{mhi_stats['below_p50_pct']:.2f}",
                f"{non_stats['below_p50_pct']:.2f}",
            ]
        )

    with (OUT / "plot_percentile_cdf_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "group",
                "n_obs",
                "mean_percentile",
                "median_percentile",
                "below_p50_n",
                "below_p50_pct",
                "below_yearly_median_n",
                "below_yearly_median_pct",
            ]
        )
        w.writerow(
            [
                "MHI",
                mhi_stats["n"],
                f"{mhi_stats['mean']:.2f}",
                f"{mhi_stats['median']:.2f}",
                mhi_stats["below_p50_n"],
                f"{mhi_stats['below_p50_pct']:.2f}",
                mhi_below_year_median,
                f"{mhi_below_year_median_pct:.2f}",
            ]
        )
        w.writerow(
            [
                "Non-MHI",
                non_stats["n"],
                f"{non_stats['mean']:.2f}",
                f"{non_stats['median']:.2f}",
                non_stats["below_p50_n"],
                f"{non_stats['below_p50_pct']:.2f}",
                non_below_year_median,
                f"{non_below_year_median_pct:.2f}",
            ]
        )

    return {
        "mhi": {
            "n": mhi_stats["n"],
            "mean_percentile": mhi_stats["mean"],
            "median_percentile": mhi_stats["median"],
            "below_p50_n": mhi_stats["below_p50_n"],
            "below_p50_pct": mhi_stats["below_p50_pct"],
            "below_year_median_n": mhi_below_year_median,
            "below_year_median_pct": mhi_below_year_median_pct,
        },
        "nonmhi": {
            "n": non_stats["n"],
            "mean_percentile": non_stats["mean"],
            "median_percentile": non_stats["median"],
            "below_p50_n": non_stats["below_p50_n"],
            "below_p50_pct": non_stats["below_p50_pct"],
            "below_year_median_n": non_below_year_median,
            "below_year_median_pct": non_below_year_median_pct,
        },
        "binary_tests": {
            "observed_diff_pp": 100.0 * observed_diff,
            "naive_two_sided_p": z_two_sided,
            "weighted_perm_two_sided_p": weighted_p_two,
            "faculty_perm_two_sided_p": faculty_p_two,
            "n_permutations": n_permutations,
        },
    }


if __name__ == "__main__":
    rows = read_long_rows()
    beta, cov, min_year = pooled_cluster_robust(rows)
    write_plot_data(rows, beta, cov, min_year)
    counts = write_year_adjusted_hist_data(rows)
    cdf_summary = write_yearly_percentile_cdf(rows)
    if counts:
        print(
            "MHI person-years vs same-year median: "
            f"below={counts['median']['below']}, "
            f"above={counts['median']['above']}, "
            f"equal={counts['median']['equal']}, "
            f"total={counts['median']['total']}"
        )
    if cdf_summary:
        print(
            "Percentile summary (pooled): "
            f"MHI mean={cdf_summary['mhi']['mean_percentile']:.2f}, "
            f"median={cdf_summary['mhi']['median_percentile']:.2f}, "
            f"<50={cdf_summary['mhi']['below_p50_pct']:.2f}% "
            f"({cdf_summary['mhi']['below_p50_n']}/{cdf_summary['mhi']['n']}); "
            f"Non-MHI mean={cdf_summary['nonmhi']['mean_percentile']:.2f}, "
            f"median={cdf_summary['nonmhi']['median_percentile']:.2f}, "
            f"<50={cdf_summary['nonmhi']['below_p50_pct']:.2f}% "
            f"({cdf_summary['nonmhi']['below_p50_n']}/{cdf_summary['nonmhi']['n']})"
        )
        print(
            "Binary test p-values (two-sided): "
            f"naive={cdf_summary['binary_tests']['naive_two_sided_p']:.6f}, "
            f"cluster_weighted_perm={cdf_summary['binary_tests']['weighted_perm_two_sided_p']:.6f}, "
            f"cluster_faculty_mean_perm={cdf_summary['binary_tests']['faculty_perm_two_sided_p']:.6f}"
        )
    print(f"Wrote PGFPlots figure data for {len(rows)} observations.")
