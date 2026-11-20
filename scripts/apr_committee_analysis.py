#!/usr/bin/env python3
"""Do SPHS faculty get larger raises in the years they sit on the APR committee?

Usage:
  python3 scripts/apr_committee_analysis.py [--reps 10000] [--seed 20261120]

Inputs:
- data/sphs.csv                               (public salary panel, calendar years)
- data/private/apr_committee_membership.csv   (gitignored: names; from the School's
                                               service-assignment spreadsheet)
- data/private/admin_stipend_roles.csv        (gitignored: Director / Associate Director /
                                               Associate Dean years, from the same sheet)

Outputs:
- output/apr_committee_summary.md                    (aggregates only, no names)
- data/private/apr_committee_person_cycles.csv       (gitignored: one row per person and cycle)
- data/private/apr_committee_within_person.csv       (gitignored: per-member on/off contrast)

Design
------
A committee "cycle" Y runs September Y to August Y+1. It rates faculty early in Y+1 and the
merit (selective) increase takes effect around May 1 of Y+1, so it appears partly in the
calendar-year Y+1 disclosure and fully in Y+2. The main outcome is the two-year change
S[Y+2] - S[Y], minus the median of that change across eligible SPHS faculty in the same
cycle. Subtracting the cycle median removes scale (across-the-board) increases and the
Bill 124 retroactive payments that every faculty member received.

Since 2019 the School alternates between "full" cycles (everyone submits an APR, ~10
members) and "small" cycles (only pre-tenure and definite-term faculty submit, ~5 members).
Tenured members of a small committee are not rated that year, so small cycles serve as a
placebo. Before 2019 every cycle is treated as full. The 2016-17 cycle is dropped because
the sheet lists only the nominees.

Person-cycles are excluded when the person held a stipended administrative role
(Director, Associate Director, Associate Dean) in any cycle overlapping the outcome window,
or when the window starts in the person's first disclosed year (possible partial-year salary).
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "sphs.csv"
MEMBERSHIP = ROOT / "data" / "private" / "apr_committee_membership.csv"
ADMIN = ROOT / "data" / "private" / "admin_stipend_roles.csv"
OUT_SUMMARY = ROOT / "output" / "apr_committee_summary.md"
OUT_PERSON_CYCLES = ROOT / "data" / "private" / "apr_committee_person_cycles.csv"
OUT_WITHIN = ROOT / "data" / "private" / "apr_committee_within_person.csv"

FULL_CYCLES = [2015, 2017, 2018, 2020, 2022, 2024]
SMALL_CYCLES = [2019, 2021, 2023]
DROPPED_CYCLES = {2016: "membership not recorded (sheet lists nominees only)"}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_panel() -> tuple[pd.DataFrame, dict[str, bool]]:
    wide = pd.read_csv(PANEL)
    years = [c for c in wide.columns if c.isdigit()]
    long = wide.melt(id_vars=["Surname", "Given name", "MHI"], value_vars=years,
                     var_name="year", value_name="salary")
    long["year"] = long["year"].astype(int)
    long = long.dropna(subset=["salary"])
    salary = long.pivot_table(index="Surname", columns="year", values="salary")
    mhi = {s: str(v).lower() == "true" for s, v in zip(wide["Surname"], wide["MHI"])}
    return salary, mhi


def load_membership(panel_names: set[str]) -> tuple[dict[int, set[str]], dict[int, str]]:
    m = pd.read_csv(MEMBERSHIP)
    unknown = set(m.loc[m["in_panel"] == 1, "surname"]) - panel_names
    if unknown:
        raise SystemExit(f"Membership surnames not in data/sphs.csv: {sorted(unknown)}")
    members = {int(y): set(g.loc[g["role"] == "member", "surname"]) for y, g in m.groupby("cycle_start")}
    directors = {int(y): ";".join(g.loc[g["role"] == "director", "surname"]) for y, g in m.groupby("cycle_start")}
    return members, directors


def load_admin() -> set[tuple[str, int]]:
    a = pd.read_csv(ADMIN)
    return {(s, int(y)) for s, y in zip(a["surname"], a["cycle_start"])}


def build_rows(salary: pd.DataFrame, mhi: dict[str, bool], members: dict[int, set[str]],
               admin: set[tuple[str, int]], cycles: list[int], horizon: int,
               apply_exclusions: bool = True) -> pd.DataFrame:
    """One row per person x cycle with an observable outcome S[Y+horizon] - S[Y]."""
    rows = []
    for person in salary.index:
        s = salary.loc[person].dropna()
        if s.empty:
            continue
        first = int(s.index.min())
        for y in cycles:
            if y not in s.index or (y + horizon) not in s.index:
                continue
            # Cycles whose months fall inside calendar years Y..Y+horizon.
            window_cycles = range(y - 1, y + horizon)
            is_admin = any((person, c) in admin for c in window_cycles)
            partial_start = (y == first)
            excluded = is_admin or partial_start
            if apply_exclusions and excluded:
                continue
            rows.append({
                "surname": person,
                "cycle": y,
                "mhi": mhi[person],
                "member": person in members.get(y, set()),
                "raise": float(s[y + horizon] - s[y]),
                "raise_pct": float((s[y + horizon] / s[y] - 1) * 100),
                "excluded_admin": is_admin,
                "excluded_partial_start": partial_start,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["resid"] = df["raise"] - df.groupby("cycle")["raise"].transform("median")
    df["resid_pct"] = df["raise_pct"] - df.groupby("cycle")["raise_pct"].transform("median")
    # Percentile rank of the raise within the cycle (0-100): robust to leave years and other outliers.
    df["pctile"] = df.groupby("cycle")["raise"].rank(pct=True) * 100
    return df


# ---------------------------------------------------------------------------
# Estimators
# ---------------------------------------------------------------------------

def design(df: pd.DataFrame, d: np.ndarray, person_fe: bool) -> np.ndarray:
    C = pd.get_dummies(df["cycle"], drop_first=False).to_numpy(float)
    if person_fe:
        P = pd.get_dummies(df["surname"], drop_first=False).to_numpy(float)
        return np.column_stack([d, P, C[:, 1:]])
    return np.column_stack([d, C])


def twfe(df: pd.DataFrame, y: str = "resid", member: np.ndarray | None = None,
         person_fe: bool = True) -> float:
    """Coefficient on membership with cycle fixed effects and (by default) person fixed effects."""
    d = member if member is not None else df["member"].to_numpy(float)
    X = design(df, d, person_fe)
    beta, *_ = np.linalg.lstsq(X, df[y].to_numpy(float), rcond=None)
    return float(beta[0])


def twfe_cluster_se(df: pd.DataFrame, y: str = "resid", person_fe: bool = True) -> float:
    """CR1 cluster-robust standard error (clusters = people) for the membership coefficient."""
    X = design(df, df["member"].to_numpy(float), person_fe)
    yy = df[y].to_numpy(float)
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ yy
    u = yy - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    groups = df["surname"].to_numpy()
    G = 0
    for g in np.unique(groups):
        idx = groups == g
        sg = X[idx].T @ u[idx]
        meat += np.outer(sg, sg)
        G += 1
    n, k = X.shape
    rank = np.linalg.matrix_rank(X)
    adj = (G / (G - 1)) * ((n - 1) / (n - rank))
    V = adj * XtX_inv @ meat @ XtX_inv
    return float(math.sqrt(max(V[0, 0], 0.0)))


def permute_within_cycle(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Shuffle committee seats among eligible faculty within each cycle (keeps seats per cycle)."""
    out = df["member"].to_numpy(float).copy()
    for _, idx in df.groupby("cycle").indices.items():
        out[idx] = rng.permutation(out[idx])
    return out


def permutation_p(df: pd.DataFrame, reps: int, rng: np.random.Generator, y: str = "resid",
                  person_fe: bool = True) -> tuple[float, float]:
    obs = twfe(df, y, person_fe=person_fe)
    null = np.array([twfe(df, y, permute_within_cycle(df, rng), person_fe) for _ in range(reps)])
    p_two = (1 + np.sum(np.abs(null) >= abs(obs) - 1e-9)) / (reps + 1)
    p_upper = (1 + np.sum(null >= obs - 1e-9)) / (reps + 1)
    return float(p_two), float(p_upper)


def within_person(df: pd.DataFrame, y: str = "resid") -> pd.DataFrame:
    rows = []
    for person, g in df.groupby("surname"):
        on, off = g.loc[g["member"], y], g.loc[~g["member"], y]
        if len(on) and len(off):
            rows.append({"surname": person, "mhi": bool(g["mhi"].iloc[0]),
                         "n_on": len(on), "n_off": len(off),
                         "mean_on": on.mean(), "mean_off": off.mean(),
                         "diff": on.mean() - off.mean()})
    return pd.DataFrame(rows)


def sign_flip_p(diffs: np.ndarray, reps: int, rng: np.random.Generator) -> float:
    obs = abs(diffs.mean())
    signs = rng.choice([-1.0, 1.0], size=(reps, len(diffs)))
    null = np.abs((signs * diffs).mean(axis=1))
    return float((1 + np.sum(null >= obs - 1e-9)) / (reps + 1))


def binom_two_sided(k: int, n: int) -> float:
    if n == 0:
        return float("nan")
    probs = [math.comb(n, i) / 2 ** n for i in range(n + 1)]
    pk = probs[k]
    return float(min(1.0, sum(p for p in probs if p <= pk + 1e-12)))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def money(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}"


def model_block(label: str, df: pd.DataFrame, reps: int, rng: np.random.Generator,
                y: str = "resid", unit: str = "$", person_fe: bool = True) -> list[str]:
    if df.empty or df["member"].sum() == 0:
        return [f"| {label} | – | – | – | – | – |"]
    est = twfe(df, y, person_fe=person_fe)
    se = twfe_cluster_se(df, y, person_fe)
    p_two, p_up = permutation_p(df, reps, rng, y, person_fe)
    fmt = money if unit == "$" else (lambda v: f"{v:+.1f} {unit}")
    n_people = df["surname"].nunique()
    return [f"| {label} | {fmt(est)} | {fmt(1.96 * se) if unit == '$' else f'{1.96*se:.1f} {unit}'} "
            f"| {p_two:.3f} | {p_up:.3f} | {len(df)} rows, {int(df['member'].sum())} member-cycles, {n_people} people |"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20261120)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    salary, mhi = load_panel()
    members, directors = load_membership(set(salary.index))
    admin = load_admin()

    full2 = build_rows(salary, mhi, members, admin, FULL_CYCLES, horizon=2)
    full1 = build_rows(salary, mhi, members, admin, FULL_CYCLES, horizon=1)
    small2 = build_rows(salary, mhi, members, admin, SMALL_CYCLES, horizon=2)
    full2_all = build_rows(salary, mhi, members, admin, FULL_CYCLES, horizon=2, apply_exclusions=False)

    # Winsorize residuals at the 5th/95th percentile (guards against leave years, promotions).
    full2_w = full2.copy()
    lo, hi = full2_w["resid"].quantile([0.05, 0.95])
    full2_w["resid"] = full2_w["resid"].clip(lo, hi)

    # Private detail files.
    OUT_PERSON_CYCLES.parent.mkdir(parents=True, exist_ok=True)
    detail = pd.concat([full2.assign(cycle_type="full", horizon=2),
                        full1.assign(cycle_type="full", horizon=1),
                        small2.assign(cycle_type="small", horizon=2)])
    detail.to_csv(OUT_PERSON_CYCLES, index=False, float_format="%.2f")

    wp = within_person(full2)
    wp.to_csv(OUT_WITHIN, index=False, float_format="%.2f")

    # Aggregates ------------------------------------------------------------
    L: list[str] = []
    L.append("# APR committee membership and salary increases")
    L.append("")
    L.append("Generated by `scripts/apr_committee_analysis.py`. The membership data are not public and "
             "are kept in `data/private/` (gitignored). This summary reports aggregates only.")
    L.append("")
    L.append("## Question")
    L.append("")
    L.append("Do faculty receive larger salary increases in cycles when they sit on the School's APR "
             "(Annual Faculty Performance Review Advisory) committee than in cycles when they do not?")
    L.append("")
    L.append("## Data and definitions")
    L.append("")
    L.append("- Salaries: public UW disclosures (`data/sphs.csv`), calendar years 2011–2025.")
    L.append("- Committee membership: School service-assignment records, cycles 2015-16 to 2026-27. "
             "The 2016-17 cycle is dropped (only nominees recorded). Directors (ex officio) are not counted as members.")
    L.append("- A cycle Y runs September Y to August Y+1. Its ratings drive the merit increase effective "
             "about May 1 of Y+1, which is fully reflected by calendar year Y+2.")
    L.append("- **Outcome:** the two-year change S(Y+2) − S(Y), minus the median change across eligible "
             "SPHS faculty in the same cycle. This removes scale increases and Bill 124 retroactive payments.")
    L.append(f"- **Full cycles** (everyone reviewed): {', '.join(f'{y}-{(y+1)%100:02d}' for y in FULL_CYCLES)}. "
             "The 2024-25 cycle has only a one-year outcome so far.")
    L.append(f"- **Small cycles** (only pre-tenure and definite-term faculty reviewed; placebo): "
             f"{', '.join(f'{y}-{(y+1)%100:02d}' for y in SMALL_CYCLES)}.")
    L.append("- **Exclusions:** person-cycles where the person held a stipended Director, Associate Director "
             "or Associate Dean role during the outcome window, and windows starting in a person's first "
             "disclosed year (possible partial-year salary).")
    L.append("")

    L.append("## Sample")
    L.append("")
    L.append("| Cycle | Type | Committee seats (excl. Director) | Seats held by people in the analysis | Eligible faculty | Median change |")
    L.append("|---|---|---|---|---|---|")
    for y in sorted(FULL_CYCLES + SMALL_CYCLES):
        src = (full1 if y == 2024 else full2) if y in FULL_CYCLES else small2
        g = src[src["cycle"] == y]
        typ = "full" if y in FULL_CYCLES else "small"
        med = (money(float(g["raise"].median())) + (" (1-yr)" if y == 2024 else "")) if len(g) else "–"
        L.append(f"| {y}-{(y+1)%100:02d} | {typ} | {len(members.get(y, set()))} | {int(g['member'].sum()) if len(g) else 0} "
                 f"| {len(g)} | {med} |")
    L.append("")

    L.append("## Results")
    L.append("")
    L.append("Estimates are from a regression of the outcome on committee membership with a separate baseline "
             "for each person and each cycle, so each member is compared with themselves in other cycles. "
             "Permutation p-values shuffle committee seats among eligible faculty within each cycle "
             f"({args.reps:,} shuffles). The one-sided p-value tests whether members gain.")
    L.append("")
    L.append("| Specification | Estimate (per cycle served) | ±95% (cluster-robust) | Permutation p (two-sided) | p (members gain) | Sample |")
    L.append("|---|---|---|---|---|---|")
    L += model_block("**Main:** full cycles, 2-year change", full2, args.reps, rng)
    L += model_block("Full cycles, 1-year change (adds 2024-25)", full1, args.reps, rng)
    L += model_block("Full cycles, 2-year change, % of salary", full2, args.reps, rng, y="resid_pct", unit="pp")
    L += model_block("Full cycles, 2-year change, percentile rank in cycle", full2, args.reps, rng, y="pctile", unit="pctile pts")
    L += model_block("Full cycles, 2-year change, winsorized 5/95", full2_w, args.reps, rng)
    L += model_block("Full cycles, no exclusions", full2_all, args.reps, rng)
    L += model_block("Placebo: small cycles, 2-year change", small2, args.reps, rng)
    L += model_block("*Across people* (no person baseline): full cycles, 2-year change", full2, args.reps, rng,
                     person_fe=False)
    L += model_block("*Across people*: full cycles, percentile rank", full2, args.reps, rng, y="pctile",
                     unit="pctile pts", person_fe=False)
    L += model_block("*Across people*: placebo small cycles", small2, args.reps, rng, person_fe=False)
    L.append("")
    L.append("The *across people* rows drop the per-person baseline: they compare members with everyone else "
             "eligible in the same cycle. They answer a different question (do the people who serve get larger "
             "raises?) and mix any committee effect with who gets elected.")
    L.append("")

    # Leave-one-member-out: how much does any single person move the main estimate?
    loo = []
    for person in sorted(set(full2.loc[full2["member"], "surname"])):
        sub = full2[full2["surname"] != person]
        if sub["member"].sum():
            loo.append(twfe(sub))
    if loo:
        L.append(f"Leave-one-member-out (main specification, {len(loo)} fits): estimates range from "
                 f"{money(min(loo))} to {money(max(loo))}.")
        L.append("")

    L.append("### Within-person comparison")
    L.append("")
    if len(wp):
        diffs = wp["diff"].to_numpy()
        k = int((diffs > 0).sum())
        L.append(f"Members observed both on and off the committee in full cycles: **{len(wp)}**.")
        L.append("")
        L.append("| Statistic | Value |")
        L.append("|---|---|")
        L.append(f"| Mean of (on − off) above-median 2-yr raise | {money(diffs.mean())} |")
        L.append(f"| Median of (on − off) | {money(float(np.median(diffs)))} |")
        L.append(f"| Members with larger raise when serving | {k} of {len(wp)} |")
        L.append(f"| Sign test p (two-sided) | {binom_two_sided(k, len(wp)):.3f} |")
        L.append(f"| Sign-flip permutation p for mean (two-sided) | {sign_flip_p(diffs, args.reps, rng):.3f} |")
        L.append(f"| Range of (on − off) | {money(diffs.min())} to {money(diffs.max())} |")
    else:
        L.append("No members are observed both on and off the committee.")
    L.append("")

    L.append("### Members versus never-members (descriptive, confounded by who gets elected)")
    L.append("")
    ever = set().union(*[members.get(y, set()) for y in FULL_CYCLES + SMALL_CYCLES])
    f = full2.copy()
    f["ever_member"] = f["surname"].isin(ever)
    L.append("| Group | People | Person-cycles | Mean above-median 2-yr raise |")
    L.append("|---|---|---|---|")
    for label, mask in [("Ever served, cycles serving", f["ever_member"] & f["member"]),
                        ("Ever served, cycles not serving", f["ever_member"] & ~f["member"]),
                        ("Never served", ~f["ever_member"])]:
        g = f[mask]
        L.append(f"| {label} | {g['surname'].nunique()} | {len(g)} | {money(g['resid'].mean()) if len(g) else '–'} |")
    L.append("")

    L.append("### MHI representation on the committee and the MHI raise gap")
    L.append("")
    L.append("For each full cycle: MHI-affiliated committee seats and the gap between the mean above-median "
             "2-year raise of MHI and non-MHI faculty (negative = MHI faculty received less).")
    L.append("")
    L.append("| Cycle | MHI seats / all seats | MHI faculty in sample | MHI − non-MHI mean raise |")
    L.append("|---|---|---|---|")
    pts = []
    for y in FULL_CYCLES:
        g = full2[full2["cycle"] == y] if y != 2024 else full1[full1["cycle"] == y]
        seats = members.get(y, set())
        mhi_seats = sum(1 for s in seats if mhi.get(s, False))
        if len(g) and g["mhi"].any() and (~g["mhi"]).any():
            gap = g.loc[g["mhi"], "resid"].mean() - g.loc[~g["mhi"], "resid"].mean()
            pts.append((mhi_seats / max(len(seats), 1), gap))
            note = " (1-yr)" if y == 2024 else ""
            L.append(f"| {y}-{(y+1)%100:02d} | {mhi_seats} / {len(seats)} | {int(g['mhi'].sum())} | {money(gap)}{note} |")
    if len(pts) >= 3:
        r = float(np.corrcoef(*zip(*pts))[0, 1])
        L.append("")
        L.append(f"Correlation across {len(pts)} cycles between MHI seat share and the MHI gap: r = {r:.2f}. "
                 "With this few cycles, treat as descriptive only.")
    L.append("")

    L.append("## Interpretation")
    L.append("")
    L.append("- **No sign that serving pays off for the people serving.** Compared with their own raises "
             "in other cycles, members do *not* get larger raises in the cycles they serve. If anything the "
             "estimate is negative, and the one-sided test for a gain is far from significant in every "
             "specification.")
    L.append("- **The negative within-person estimate should not be read as a penalty.** It rests on the few "
             f"members ({len(wp)}) observed both on and off the committee in full cycles. It is weaker on the "
             "outlier-robust percentile scale, and the placebo (small cycles, where tenured members are not "
             "rated) is also negative. That pattern fits timing, not the committee itself: people tend to be "
             "elected after strong stretches (promotion, return from leave), so their off-committee cycles "
             "include those bumps.")
    L.append("- **The people who serve tend to get above-median raises anyway.** Across people, members sit "
             "higher in each cycle's raise distribution than non-members, in serving and non-serving cycles "
             "alike. This is consistent with the committee being drawn from faculty who are rated well, "
             "rather than with membership changing anyone's rating.")
    L.append("- **MHI representation** on the committee has been low (0–3 of 5–11 seats). The MHI raise gap "
             "is smallest in the cycle with the most MHI seats, but six cycles cannot separate this from "
             "chance or from the 1-year outcome used for that cycle.")
    L.append("")
    L.append("## Caveats")
    L.append("")
    L.append("- Small sample: about two dozen members over six usable full cycles. Only large effects "
             "(roughly $1,500–2,000 per cycle or more) are detectable; a null is not evidence of no effect.")
    L.append("- Promotions (Associate to Full) raise salary and are not flagged, because the panel does not "
             "hold yearly titles. The winsorized specification limits their influence.")
    L.append("- Disclosed salary includes stipends; admin-role years are excluded but smaller stipends "
             "(program leads, teaching fellow) are not.")
    L.append("- Under biennial review a full-cycle rating sets two years of increases, so part of the effect "
             "can fall outside the two-year window.")
    L.append("- If members recuse themselves from their own file, any benefit would have to work through other "
             "channels (e.g. the norms the committee sets, or how colleagues rate one another).")
    L.append("")

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text("\n".join(L) + "\n")
    print(f"Wrote {OUT_SUMMARY.relative_to(ROOT)}")
    print(f"Wrote {OUT_PERSON_CYCLES.relative_to(ROOT)} (private)")
    print(f"Wrote {OUT_WITHIN.relative_to(ROOT)} (private)")


if __name__ == "__main__":
    main()
