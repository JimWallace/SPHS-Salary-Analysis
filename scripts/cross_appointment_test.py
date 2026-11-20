#!/usr/bin/env python3
"""Pre-registered test: do cross-appointed University of Waterloo faculty receive smaller annual raises
than faculty in the same home unit who are not cross-appointed?

Frozen with docs/preregistration_cross_appointment.md. Do not change the analysis after the
registration release; record any change as a deviation.

Usage:
  python3 scripts/cross_appointment_test.py --test A
      Retrospective test: raises 2016-2025.
  python3 scripts/cross_appointment_test.py --test B --disclosure-2026 PATH/2026.html
      Prospective test: the 2025->2026 raise, using the 2026 disclosure published by 31 March 2027.
  python3 scripts/cross_appointment_test.py --test A --synthetic --out DIR
      Code check only: replaces every salary with simulated values (no real outcome is computed).
  python3 scripts/cross_appointment_test.py --describe
      Sample description only (counts; no outcome).

Inputs (gitignored, frozen; SHA-256 recorded in docs/registration_manifest.csv and checked at run time):
- data/private/uw_people.csv, data/private/uw_panel_long.csv  (scripts/build_uw_panel.py)

Output: output/cross_appointment_test_<A|B>.md (aggregates only; groups under 3 people suppressed).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PEOPLE = ROOT / "data" / "private" / "uw_people.csv"
PANEL = ROOT / "data" / "private" / "uw_panel_long.csv"
MANIFEST = ROOT / "docs" / "registration_manifest.csv"
EXCLUDED_HOME = {"Public Health Sciences"}  # the unit that generated the hypothesis
MIN_UNIT_YEAR = 5
MIN_CELL = 3
REPS = 10_000
BOOT = 2_000
SEED = 20261120
TENURE_TRACK = {"assistant", "associate", "full"}


# ---------------------------------------------------------------------------
# Frozen inputs
# ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_manifest() -> list[str]:
    """Compare input files with the hashes recorded at registration. Returns deviation notes."""
    if not MANIFEST.exists():
        raise SystemExit(f"Missing {MANIFEST}: inputs were not registered.")
    notes = []
    with MANIFEST.open() as f:
        for row in csv.DictReader(f):
            path = ROOT / row["path"]
            if not path.exists():
                notes.append(f"{row['path']}: missing")
            elif sha256(path) != row["sha256"]:
                notes.append(f"{row['path']}: differs from the registered version")
    return notes


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_people() -> pd.DataFrame:
    p = pd.read_csv(PEOPLE).fillna("")
    p = p[(p["status"] == "ok") & (p["home_unit"] != "") & (~p["home_unit"].isin(EXCLUDED_HOME))].copy()
    p["xa"] = ((p["xa_listing"] == 1) | (p["xa_profile"] == 1)).astype(int)
    p["xa_listing_only_def"] = (p["xa_listing"] == 1).astype(int)
    p["xa_profile_only_def"] = (p["xa_profile"] == 1).astype(int)
    p["joint"] = p["xa_text"].str.contains(r"\bjoint(?:ly)? appoint", case=False, regex=True).astype(int)
    return p


def load_panel(disclosure_2026: Path | None) -> pd.DataFrame:
    panel = pd.read_csv(PANEL)
    if disclosure_2026 is not None:
        spec = importlib.util.spec_from_file_location("tp", ROOT / "scripts" / "build_disclosure_title_panels.py")
        tp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tp)
        rows = []
        for d in tp.parse_year(disclosure_2026):
            rank = tp.title_rank(d["title"])
            if rank in {"other"}:
                continue
            key = "|".join((tp.norm(d["surname"]), tp.first_token(d["given"])))
            rows.append({"key": key, "year": 2026, "salary": d["salary"], "title": d["title"], "rank": rank})
        new = pd.DataFrame(rows)
        dup = new.groupby("key").size()
        new = new[new["key"].isin(dup[dup == 1].index) & new["key"].isin(set(panel["key"]))]
        panel = pd.concat([panel, new], ignore_index=True)
    return panel


def synthesize(panel: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Replace salaries with a random walk per person: for code checks only."""
    out = panel.sort_values(["key", "year"]).copy()
    vals = []
    for _, g in out.groupby("key", sort=False):
        start = rng.uniform(100_000, 180_000)
        steps = rng.normal(6_000, 3_000, size=len(g))
        vals.extend(start + np.cumsum(steps) - steps[0])
    out["salary"] = vals
    return out


def raises(panel: pd.DataFrame, people: pd.DataFrame, years: range) -> pd.DataFrame:
    """Annual raises with the registered exclusions and home unit-year residuals."""
    rows = []
    keep = set(people["key"])
    for key, g in panel[panel["key"].isin(keep)].sort_values("year").groupby("key"):
        g = g.set_index("year")
        first = g.index.min()
        change = {y for y in g.index if (y - 1) in g.index and g.at[y, "rank"] != g.at[y - 1, "rank"]}
        for y in g.index:
            if y not in years or (y - 1) not in g.index:
                continue
            if (y - 1) == first or y in change or (y - 1) in change:
                continue
            rows.append({"key": key, "year": int(y), "rank": g.at[y, "rank"],
                         "raise": float(g.at[y, "salary"] - g.at[y - 1, "salary"]),
                         "raise_pct": float((g.at[y, "salary"] / g.at[y - 1, "salary"] - 1) * 100)})
    r = pd.DataFrame(rows)
    r = r.merge(people[["key", "home_unit", "home_faculty", "xa", "xa_listing_only_def",
                        "xa_profile_only_def", "joint"]], on="key")
    size = r.groupby(["home_unit", "year"])["key"].transform("size")
    r = r[size >= MIN_UNIT_YEAR].copy()
    for col in ("raise", "raise_pct"):
        r[f"resid_{col}"] = r[col] - r.groupby(["home_unit", "year"])[col].transform("median")
    return r


# ---------------------------------------------------------------------------
# Estimators
# ---------------------------------------------------------------------------

def person_means(r: pd.DataFrame, y: str, expo: str) -> pd.DataFrame:
    return r.groupby("key").agg(m=(y, "mean"), x=(expo, "first"), unit=("home_unit", "first"))


def diff(pm: pd.DataFrame, x: np.ndarray | None = None) -> float:
    x = pm["x"].to_numpy() if x is None else x
    m = pm["m"].to_numpy()
    if x.sum() == 0 or x.sum() == len(x):
        return float("nan")
    return float(m[x == 1].mean() - m[x == 0].mean())


def perm_within_unit(pm: pd.DataFrame, rng: np.random.Generator, reps: int = REPS) -> tuple[float, float]:
    obs = diff(pm)
    x = pm["x"].to_numpy().copy()
    groups = [np.flatnonzero(pm["unit"].to_numpy() == u) for u in pm["unit"].unique()]
    null = np.empty(reps)
    for i in range(reps):
        xs = x.copy()
        for idx in groups:
            xs[idx] = rng.permutation(xs[idx])
        null[i] = diff(pm, xs)
    p_lower = (1 + np.sum(null <= obs + 1e-9)) / (reps + 1)
    return obs, float(p_lower)


def bootstrap_ci(pm: pd.DataFrame, rng: np.random.Generator, reps: int = BOOT) -> tuple[float, float]:
    by_unit = [pm[pm["unit"] == u] for u in pm["unit"].unique()]
    est = []
    for _ in range(reps):
        sample = pd.concat([g.iloc[rng.integers(0, len(g), len(g))] for g in by_unit])
        est.append(diff(sample))
    est = np.array(est)
    est = est[~np.isnan(est)]
    return float(np.quantile(est, 0.025)), float(np.quantile(est, 0.975))


def fe_regression(r: pd.DataFrame, y: str, expo: str) -> tuple[float, float]:
    """Person-year OLS with year and home-unit fixed effects; CR1 standard error clustered by person."""
    X = np.column_stack([r[expo].to_numpy(float),
                         pd.get_dummies(r["year"]).to_numpy(float),
                         pd.get_dummies(r["home_unit"], drop_first=True).to_numpy(float)])
    yy = r[y].to_numpy(float)
    XtX = np.linalg.pinv(X.T @ X)
    b = XtX @ X.T @ yy
    u = yy - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    keys = r["key"].to_numpy()
    G = 0
    for k in np.unique(keys):
        idx = keys == k
        s = X[idx].T @ u[idx]
        meat += np.outer(s, s)
        G += 1
    n, rank = len(yy), np.linalg.matrix_rank(X)
    V = (G / (G - 1)) * ((n - 1) / (n - rank)) * XtX @ meat @ XtX
    return float(b[0]), float(math.sqrt(max(V[0, 0], 0)))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def money(x: float) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{'-' if x < 0 else ''}${abs(x):,.0f}"


def describe(people: pd.DataFrame) -> list[str]:
    L = ["| Faculty | People | Cross-appointed |", "|---|---|---|"]
    for fac, g in people.groupby("home_faculty"):
        L.append(f"| {fac} | {len(g)} | {int(g['xa'].sum())} |")
    L.append(f"| **All** | {len(people)} | {int(people['xa'].sum())} |")
    return L


def run(test: str, r: pd.DataFrame, rng: np.random.Generator, notes: list[str], synthetic: bool) -> list[str]:
    title = {"A": "Test A (retrospective, raises 2016–2025)", "B": "Test B (prospective, 2025→2026 raise)"}[test]
    L = [f"# Cross-appointment and annual raises: {title}", ""]
    if synthetic:
        L += ["**SYNTHETIC RUN — salaries are simulated. These numbers mean nothing; this file only checks that the "
              "code runs.**", ""]
    L += ["Pre-registered in `docs/preregistration_cross_appointment.md`. SPHS-home faculty excluded.", ""]
    L += ["**Deviations from the registered inputs:** " + ("; ".join(notes) if notes else "none."), ""]

    pm = person_means(r, "resid_raise", "xa")
    n1, n0 = int(pm["x"].sum()), int((pm["x"] == 0).sum())
    L += [f"Sample: {len(r)} annual raises; {len(pm)} people ({n1} cross-appointed, {n0} not); "
          f"{r['home_unit'].nunique()} home units.", ""]

    est, p = perm_within_unit(pm, rng)
    lo, hi = bootstrap_ci(pm, rng)
    L += ["## Primary test", "",
          "Difference in mean residual raise (cross-appointed minus not), people weighted equally; residual = "
          "raise minus the median raise in the same home unit and year.", "",
          "| Estimate | 95% interval (stratified bootstrap) | One-sided p (within-unit permutation) | Supports H1 at 0.05? |",
          "|---|---|---|---|",
          f"| {money(est)} a year | {money(lo)} to {money(hi)} | {p:.4f} | {'yes' if p < 0.05 else 'no'} |", ""]

    L += ["## Secondary analyses (reported regardless of result)", "",
          "| Analysis | Estimate | Detail |", "|---|---|---|"]
    b, se = fe_regression(r, "resid_raise", "xa")
    L.append(f"| Person-year regression, year and home-unit fixed effects | {money(b)} | ±{money(1.96 * se)} (95%, clustered by person) |")
    for label, expo in [("Listing-based definition only", "xa_listing_only_def"),
                        ("Profile-statement definition only", "xa_profile_only_def")]:
        e, pp = perm_within_unit(person_means(r, "resid_raise", expo), rng, REPS // 2)
        L.append(f"| {label} | {money(e)} | one-sided p = {pp:.3f} |")
    j = r[(r["xa"] == 0) | (r["joint"] == 1)]
    c = r[(r["xa"] == 0) | ((r["xa"] == 1) & (r["joint"] == 0))]
    for label, sub in [("Joint appointments vs not cross-appointed", j), ("Cross- (not joint) vs not cross-appointed", c)]:
        pmx = person_means(sub, "resid_raise", "xa")
        if pmx["x"].sum() >= MIN_CELL:
            e, pp = perm_within_unit(pmx, rng, REPS // 2)
            L.append(f"| {label} | {money(e)} | {int(pmx['x'].sum())} people; one-sided p = {pp:.3f} |")
        else:
            L.append(f"| {label} | – | fewer than {MIN_CELL} people |")
    tt = r[r["rank"].isin(TENURE_TRACK)]
    e, pp = perm_within_unit(person_means(tt, "resid_raise", "xa"), rng, REPS // 2)
    L.append(f"| Tenured / tenure-track ranks only | {money(e)} | one-sided p = {pp:.3f} |")
    e, pp = perm_within_unit(person_means(r, "resid_raise_pct", "xa"), rng, REPS // 2)
    L.append(f"| Percentage raises | {e:+.2f} percentage points | one-sided p = {pp:.3f} |")
    L += ["", "| Faculty | Cross-appointed people | Estimate | One-sided p |", "|---|---|---|---|"]
    for fac, sub in r.groupby("home_faculty"):
        pmf = person_means(sub, "resid_raise", "xa")
        k = int(pmf["x"].sum())
        if k < MIN_CELL or k == len(pmf):
            L.append(f"| {fac} | fewer than {MIN_CELL} | – | – |")
            continue
        e, pp = perm_within_unit(pmf, rng, REPS // 5)
        L.append(f"| {fac} | {k} | {money(e)} | {pp:.3f} |")
    L.append("")
    return L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", choices=["A", "B"])
    ap.add_argument("--disclosure-2026", type=Path)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "output")
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)
    people = load_people()

    if args.describe:
        print("\n".join(describe(people)))
        return
    if args.test is None:
        raise SystemExit("Choose --test A or --test B (or --describe).")
    if args.test == "B" and args.disclosure_2026 is None:
        raise SystemExit("Test B needs --disclosure-2026 (published by 31 March 2027).")
    if not args.synthetic and args.out.resolve() != (ROOT / "output").resolve():
        raise SystemExit("Real runs write to output/ only.")
    if args.synthetic and args.out.resolve() == (ROOT / "output").resolve():
        raise SystemExit("Synthetic runs must not write to output/; pass --out to a scratch directory.")

    notes = check_manifest()
    panel = load_panel(args.disclosure_2026 if args.test == "B" else None)
    if args.synthetic:
        panel = synthesize(panel, rng)
    years = range(2016, 2026) if args.test == "A" else range(2026, 2027)
    r = raises(panel, people, years)
    L = run(args.test, r, rng, notes, args.synthetic)
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"cross_appointment_test_{args.test}{'_SYNTHETIC' if args.synthetic else ''}.md"
    out.write_text("\n".join(L) + "\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
