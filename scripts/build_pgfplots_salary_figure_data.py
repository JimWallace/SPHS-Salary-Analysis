#!/usr/bin/env python3
import csv
import re
from math import sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "sphs.csv"
OUT = ROOT / "analysis_output"
SPHS_LIST = ROOT / "SalaryData" / "SPHS Faculty List.swift"

FOCUSED_MHI = {
    "CHAURASIA, ASHOK",
    "CHEN, HELEN H.",
    "LEE, JOON",
    "LEE, JOON H.",
    "LUO, HAO",
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


if __name__ == "__main__":
    rows = read_long_rows()
    beta, cov, min_year = pooled_cluster_robust(rows)
    write_plot_data(rows, beta, cov, min_year)
    print(f"Wrote PGFPlots figure data for {len(rows)} observations.")
