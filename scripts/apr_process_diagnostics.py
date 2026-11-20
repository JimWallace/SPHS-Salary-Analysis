#!/usr/bin/env python3
"""Diagnostics on how the SPHS APR process plays out in salaries.

Usage:
  python3 scripts/apr_process_diagnostics.py [--reps 5000] [--seed 20261120]

Three analyses:
  A. Persistence: is a person's position in the raise distribution stable from year to year?
  B. Comparison with Kinesiology (KIN) and Recreation and Leisure Studies (RLS), the other
     Faculty of Health units, built the same way from the public disclosures.
  C. Research-area proximity to the APR committee: do faculty who share research groups with more
     of that cycle's committee members receive larger raises?

Inputs:
- data/sphs.csv, data/sphs_titles.csv                  (public)
- data/public_sphs_scrape/faculty_group_membership.csv  (public research-group tags, current listing)
- data/private/comparison_unit_panels.csv               (gitignored; scripts/build_disclosure_title_panels.py)
- data/private/apr_committee_membership.csv, data/private/admin_stipend_roles.csv (gitignored)

Outputs:
- output/apr_process_diagnostics.md                     (aggregates only, no names)
- data/private/apr_proximity_person_cycles.csv          (gitignored)
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "sphs.csv"
TITLES = ROOT / "data" / "sphs_titles.csv"
GROUPS = ROOT / "data" / "public_sphs_scrape" / "faculty_group_membership.csv"
UNITS = ROOT / "data" / "private" / "comparison_unit_panels.csv"
OUT = ROOT / "output" / "apr_process_diagnostics.md"
OUT_PROX = ROOT / "data" / "private" / "apr_proximity_person_cycles.csv"
GENERIC_TAGS = {"Researchers"}
# Before 2016 fewer than five faculty per unit are above the disclosure threshold in some years.
CROSS_START = 2016

_spec = importlib.util.spec_from_file_location("apr", ROOT / "scripts" / "apr_committee_analysis.py")
apr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apr)
money = apr.money


# ---------------------------------------------------------------------------
# Annual raise panels
# ---------------------------------------------------------------------------

def sphs_long() -> pd.DataFrame:
    wide = pd.read_csv(PANEL)
    years = [c for c in wide.columns if c.isdigit()]
    long = wide.melt(id_vars=["Surname", "MHI"], value_vars=years, var_name="year", value_name="salary")
    long = long.dropna(subset=["salary"]).rename(columns={"Surname": "person"})
    long["year"] = long["year"].astype(int)
    long["mhi"] = long["MHI"].astype(str).str.lower().eq("true")
    titles = pd.read_csv(TITLES).rename(columns={"Surname": "person"})[["person", "year", "rank"]]
    long = long.merge(titles, on=["person", "year"], how="left")
    long["unit"] = "SPHS"
    return long[["unit", "person", "year", "salary", "rank", "mhi"]]


def units_long() -> pd.DataFrame:
    u = pd.read_csv(UNITS)
    u["mhi"] = False
    return u[["unit", "person", "year", "salary", "rank", "mhi"]]


def annual_raises(long: pd.DataFrame, admin_years: set[tuple[str, int]] | None = None) -> pd.DataFrame:
    """Raise S[t] - S[t-1] for consecutive disclosed years, with exclusion flags.

    Excluded: the raise in a person's second disclosed year (first year may be partial), raises in the
    year of a rank change and the year after (promotion increases straddle two calendar years), and,
    when admin_years is given, years with a stipended administrative role in t-1 or t.
    """
    rows = []
    for (unit, person), g in long.sort_values("year").groupby(["unit", "person"]):
        g = g.set_index("year")
        first = g.index.min()
        rank_change_years = {y for y in g.index[1:] if (y - 1) in g.index and g.at[y, "rank"] != g.at[y - 1, "rank"]}
        for y in g.index:
            if (y - 1) not in g.index:
                continue
            excluded = (y - 1 == first) or (y in rank_change_years) or ((y - 1) in rank_change_years)
            if admin_years is not None:
                excluded |= (person, y) in admin_years or (person, y - 1) in admin_years
            rows.append({"unit": unit, "person": person, "year": int(y), "mhi": bool(g.at[y, "mhi"]),
                         "raise": float(g.at[y, "salary"] - g.at[y - 1, "salary"]),
                         "raise_pct": float((g.at[y, "salary"] / g.at[y - 1, "salary"] - 1) * 100),
                         "excluded": bool(excluded)})
    df = pd.DataFrame(rows)
    return df[~df["excluded"]].copy()


def admin_calendar_years() -> set[tuple[str, int]]:
    """Admin cycle c (Sept c - Aug c+1) touches calendar years c and c+1."""
    out = set()
    for person, c in apr.load_admin():
        out.add((person, c))
        out.add((person, c + 1))
    return out


def add_resid(df: pd.DataFrame, by: list[str], col: str = "raise") -> pd.Series:
    return df[col] - df.groupby(by)[col].transform("median")


# ---------------------------------------------------------------------------
# A. Persistence
# ---------------------------------------------------------------------------

def lag_corr(df: pd.DataFrame, lag: int, col: str = "resid") -> tuple[float, int]:
    a = df[["person", "year", col]]
    b = a.assign(year=a["year"] - lag)
    m = a.merge(b, on=["person", "year"], suffixes=("", "_lead"))
    if len(m) < 5:
        return float("nan"), len(m)
    return float(np.corrcoef(m[col], m[col + "_lead"])[0, 1]), len(m)


def early_late(df: pd.DataFrame, col: str = "resid", early=(2012, 2017), late=(2019, 2025)) -> tuple[float, int]:
    e = df[df["year"].between(*early)].groupby("person")[col].mean()
    l = df[df["year"].between(*late)].groupby("person")[col].mean()
    both = pd.concat([e, l], axis=1, join="inner")
    if len(both) < 5:
        return float("nan"), len(both)
    return float(both.rank().corr().iloc[0, 1]), len(both)


def icc(df: pd.DataFrame, col: str = "resid") -> float:
    """Share of residual-raise variance that lies between people (one-way random-effects ICC(1))."""
    g = df.groupby("person")[col]
    k = g.size()
    n, a = len(df), len(k)
    if a < 3:
        return float("nan")
    grand = df[col].mean()
    msb = (k * (g.mean() - grand) ** 2).sum() / (a - 1)
    msw = ((df[col] - g.transform("mean")) ** 2).sum() / (n - a)
    k0 = (n - (k ** 2).sum() / n) / (a - 1)
    return float((msb - msw) / (msb + (k0 - 1) * msw))


def shuffle_people(df: pd.DataFrame, rng: np.random.Generator, col: str = "resid") -> pd.DataFrame:
    """Null: within each year, reassign residuals at random among the people observed that year."""
    out = df.copy()
    vals = out[col].to_numpy().copy()
    for _, idx in out.groupby("year").indices.items():
        vals[idx] = rng.permutation(vals[idx])
    out[col] = vals
    return out


def persistence_block(df: pd.DataFrame, reps: int, rng: np.random.Generator, col: str = "resid",
                      windows: tuple = ((2012, 2017), (2019, 2025))) -> dict:
    stats = {
        "lag1": lag_corr(df, 1, col), "lag2": lag_corr(df, 2, col), "lag3": lag_corr(df, 3, col),
        "early_late": early_late(df, col, *windows), "icc": (icc(df, col), df["person"].nunique()),
    }
    nulls = {k: [] for k in stats}
    for _ in range(reps):
        s = shuffle_people(df, rng, col)
        nulls["lag1"].append(lag_corr(s, 1, col)[0])
        nulls["lag2"].append(lag_corr(s, 2, col)[0])
        nulls["lag3"].append(lag_corr(s, 3, col)[0])
        nulls["early_late"].append(early_late(s, col, *windows)[0])
        nulls["icc"].append(icc(s, col))
    out = {}
    for k, (v, n) in stats.items():
        null = np.array(nulls[k], dtype=float)
        null = null[~np.isnan(null)]
        p = (1 + np.sum(null >= v - 1e-12)) / (len(null) + 1) if not math.isnan(v) else float("nan")
        out[k] = (v, n, float(np.mean(null)) if len(null) else float("nan"), p)
    return out


# ---------------------------------------------------------------------------
# C. Research-area proximity
# ---------------------------------------------------------------------------

def load_tags(panel_surnames: list[str]) -> dict[str, set[str]]:
    by_name: dict[str, set[str]] = {}
    with GROUPS.open(newline="") as f:
        for r in csv.DictReader(f):
            tag = " ".join(r["group_tag"].split())
            if tag and tag not in GENERIC_TAGS:
                by_name.setdefault(r["faculty_name"], set()).add(tag)
    tags = {}
    for sur in panel_surnames:
        sur_tokens = set(apr_norm(sur).split())
        hits = [n for n in by_name if apr_norm(n).split()[-1] in sur_tokens]
        if len(hits) == 1:
            tags[sur] = by_name[hits[0]]
    return tags


def apr_norm(text: str) -> str:
    return " ".join("".join(ch if ch.isalpha() or ch in " -'" else " " for ch in text.upper()).split())


def proximity_rows(full2: pd.DataFrame, members: dict[int, set[str]], tags: dict[str, set[str]]) -> pd.DataFrame:
    rows = []
    for r in full2.itertuples():
        mine = tags.get(r.surname)
        seats = [m for m in members.get(r.cycle, set()) if m != r.surname and m in tags]
        if not mine or not seats:
            continue
        shared = [m for m in seats if tags[m] & mine]
        rows.append({"surname": r.surname, "cycle": r.cycle, "mhi": r.mhi, "member": r.member,
                     "resid": r.resid, "pctile": r.pctile,
                     "tagged_seats": len(seats), "shared_seats": len(shared),
                     "proximity": len(shared) / len(seats),
                     "informatics": "Health informatics researcher" in mine})
    return pd.DataFrame(rows)


def fe_coef(df: pd.DataFrame, x: np.ndarray, y: str, person_fe: bool, controls: list[str] | None = None) -> float:
    cols = [x] + [df[c].to_numpy(float) for c in (controls or [])]
    C = pd.get_dummies(df["cycle"]).to_numpy(float)
    if person_fe:
        P = pd.get_dummies(df["surname"]).to_numpy(float)
        X = np.column_stack(cols + [P, C[:, 1:]])
    else:
        X = np.column_stack(cols + [C])
    beta, *_ = np.linalg.lstsq(X, df[y].to_numpy(float), rcond=None)
    return float(beta[0])


def proximity_test(df: pd.DataFrame, y: str, person_fe: bool, reps: int, rng: np.random.Generator,
                   controls: list[str] | None = None) -> tuple[float, float]:
    x = df["proximity"].to_numpy(float)
    obs = fe_coef(df, x, y, person_fe, controls)
    null = []
    idx = df.groupby("cycle").indices
    for _ in range(reps):
        xs = x.copy()
        for _, ii in idx.items():
            xs[ii] = rng.permutation(xs[ii])
        null.append(fe_coef(df, xs, y, person_fe, controls))
    null = np.array(null)
    return obs, float((1 + np.sum(np.abs(null) >= abs(obs) - 1e-9)) / (reps + 1))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt_r(v: float) -> str:
    return "–" if math.isnan(v) else f"{v:+.2f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=20261120)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    sphs = sphs_long()
    units = units_long()
    admin_years = admin_calendar_years()

    L: list[str] = ["# How the APR process plays out in salaries: three diagnostics", "",
                    "Generated by `scripts/apr_process_diagnostics.py`. Aggregates only; named inputs and "
                    "per-person outputs are in `data/private/` (gitignored).", ""]
    L += ["## Data", "",
          "- Annual raise = disclosed salary in year t minus year t−1 (public UW disclosures, 2011–2025).",
          "- Excluded raises: a person's second disclosed year (the first may be a partial year), the year of a "
          "change in disclosed rank and the year after (promotion increases straddle two calendar years). "
          "For SPHS-only analyses, years with a stipended Director, Associate Director or Associate Dean role "
          "are also excluded.",
          "- **Residual raise** = raise minus the median raise in the same unit and year. It removes scale "
          "increases and one-off payments that everyone received (e.g. Bill 124 retroactive pay in 2023–24).",
          "- Disclosed titles show academic rank only, never administrative roles, so stipends for Chairs and "
          "Directors in KIN and RLS cannot be removed. Cross-unit comparisons therefore apply the same rules to "
          "all three units and rely on medians.", ""]

    # ---------------- A. Persistence -----------------------------------------
    s_raises = annual_raises(sphs, admin_years)
    s_raises["resid"] = add_resid(s_raises, ["year"])
    s_raises["resid_noMHI"] = s_raises["raise"] - s_raises.groupby(["year", "mhi"])["raise"].transform("median")
    pa = persistence_block(s_raises, args.reps, rng)
    pb = persistence_block(s_raises, args.reps, rng, col="resid_noMHI")

    L += ["## A. Do raises stick? (SPHS)", "",
          "If the process rates the same people high or low year after year, a person's residual raise should "
          "predict their residual raise in later years. The null (\"no persistence\") reassigns residuals at "
          "random among the faculty observed in each year; p is the share of shuffles at least as persistent.",
          "",
          f"Sample: {len(s_raises)} annual raises, {s_raises['person'].nunique()} people.", "",
          "| Measure | SPHS | Expected with no persistence | p | Same, after removing the MHI/non-MHI difference | p |",
          "|---|---|---|---|---|---|"]
    labels = {
        "lag1": "Correlation with next year's residual raise",
        "lag2": "Correlation two years later",
        "lag3": "Correlation three years later (no shared rating or raise-timing overlap)",
        "early_late": "Rank correlation: mean residual 2012–17 vs 2019–25",
        "icc": "Share of raise variation that is between people (ICC)",
    }
    for k, lab in labels.items():
        v, n, nm, p = pa[k]
        v2, _, _, p2 = pb[k]
        L.append(f"| {lab} | {fmt_r(v)} (n={n}) | {fmt_r(nm)} | {p:.3f} | {fmt_r(v2)} | {p2:.3f} |")
    L += ["",
          "Notes: a merit increase takes effect around May 1, so it is split across two calendar-year raises; "
          "this makes the one-year correlation partly mechanical. Since about 2019, tenured faculty are rated "
          "every second year and the rating sets two years of increases, which also links raises two years "
          "apart. The three-year correlation and the early-versus-late comparison avoid both overlaps.", ""]

    # ---------------- B. Cross-unit ------------------------------------------
    allu = pd.concat([sphs, units], ignore_index=True)
    a_raises = annual_raises(allu)  # same rules for every unit; no admin exclusions
    a_raises = a_raises[a_raises["year"] >= CROSS_START].copy()
    a_raises["resid_unit"] = add_resid(a_raises, ["unit", "year"])
    a_raises["resid_health"] = add_resid(a_raises, ["year"])  # vs pooled Health median

    L += ["## B. SPHS compared with Kinesiology and Recreation and Leisure Studies", "",
          "All three units are built the same way: currently listed faculty matched to the public "
          "disclosures, with the same exclusions (no administrative-stipend exclusions in any unit). "
          f"Years from {CROSS_START}: before then, some units have fewer than five faculty above the $100,000 "
          "disclosure threshold.", ""]
    L += ["| Unit | People | Annual raises | Median raise | Median raise, % | Spread within a year (median IQR) | Spread, % of salary |",
          "|---|---|---|---|---|---|---|"]
    for u, g in a_raises.groupby("unit"):
        iqr = g.groupby("year")["raise"].agg(lambda x: x.quantile(0.75) - x.quantile(0.25) if len(x) >= 4 else np.nan)
        iqr_pct = g.groupby("year")["raise_pct"].agg(lambda x: x.quantile(0.75) - x.quantile(0.25) if len(x) >= 4 else np.nan)
        L.append(f"| {u} | {g['person'].nunique()} | {len(g)} | {money(g['raise'].median())} | "
                 f"{g['raise_pct'].median():.1f}% | {money(float(iqr.median()))} | {iqr_pct.median():.1f} pp |")
    L.append("")

    iqr_by = a_raises.groupby(["year", "unit"])["raise_pct"].agg(lambda x: x.quantile(0.75) - x.quantile(0.25)).unstack()
    tighter = int(((iqr_by["SPHS"] < iqr_by["KIN"]) & (iqr_by["SPHS"] < iqr_by["RLS"])).sum())
    L += [f"SPHS has the narrowest within-year spread of raises (as % of salary) of the three units in "
          f"**{tighter} of {len(iqr_by)}** years.", ""]

    L += ["### Median annual raise by year", "",
          "Number of raises in parentheses.", "",
          "| Year | SPHS | KIN | RLS | SPHS − (KIN+RLS) median |", "|---|---|---|---|---|"]
    for y in sorted(a_raises["year"].unique()):
        g = a_raises[a_raises["year"] == y]
        med = {u: g.loc[g["unit"] == u, "raise"].median() for u in ["SPHS", "KIN", "RLS"]}
        other = g.loc[g["unit"].isin(["KIN", "RLS"]), "raise"].median()
        cnt = {u: int((g["unit"] == u).sum()) for u in ["SPHS", "KIN", "RLS"]}
        cells = [f"{money(med[u])} ({cnt[u]})" if not math.isnan(med[u]) else "–" for u in ["SPHS", "KIN", "RLS"]]
        diff = money(med["SPHS"] - other) if not (math.isnan(med["SPHS"]) or math.isnan(other)) else "–"
        L.append(f"| {y} | " + " | ".join(cells) + f" | {diff} |")
    L.append("")

    # Group positions against the pooled Health median, by period.
    a_raises["group"] = np.where(a_raises["unit"] != "SPHS", a_raises["unit"],
                                 np.where(a_raises["mhi"], "SPHS – MHI", "SPHS – non-MHI"))
    L += ["### Where each group sits relative to the Faculty of Health median raise", "",
          "Mean of (raise − median raise across all three units that year). Negative = below the Health median.",
          "", "| Group | 2016–2020 | 2021–2025 | All years (mean) | All years (median) | Annual raises |",
          "|---|---|---|---|---|---|"]
    for grp in ["SPHS – MHI", "SPHS – non-MHI", "KIN", "RLS"]:
        g = a_raises[a_raises["group"] == grp]
        e = g.loc[g["year"] <= 2020, "resid_health"].mean()
        l_ = g.loc[g["year"] >= 2021, "resid_health"].mean()
        L.append(f"| {grp} | {money(e)} | {money(l_)} | {money(g['resid_health'].mean())} | "
                 f"{money(g['resid_health'].median())} | {len(g)} |")
    L.append("")

    # Permutation: is the SPHS MHI group's position different from KIN+RLS faculty? Shuffle group labels
    # among people (person-level), within year structure kept.
    def group_gap(df: pd.DataFrame, labels: pd.Series) -> float:
        lab = df["person_key"].map(labels)
        return float(df.loc[lab == "SPHS – MHI", "resid_health"].mean() - df.loc[lab.isin(["KIN", "RLS"]), "resid_health"].mean())

    a_raises["person_key"] = a_raises["unit"] + "|" + a_raises["person"]
    person_group = a_raises.groupby("person_key")["group"].first()
    obs_gap = group_gap(a_raises, person_group)
    sub_keys = person_group[person_group.isin(["SPHS – MHI", "KIN", "RLS"])]
    null = []
    for _ in range(args.reps):
        shuffled = pd.Series(rng.permutation(sub_keys.to_numpy()), index=sub_keys.index)
        lab = person_group.copy()
        lab.loc[shuffled.index] = shuffled
        null.append(group_gap(a_raises, lab))
    p_gap = (1 + np.sum(np.abs(np.array(null)) >= abs(obs_gap) - 1e-9)) / (args.reps + 1)
    obs_non = float(a_raises.loc[a_raises["group"] == "SPHS – non-MHI", "resid_health"].mean()
                    - a_raises.loc[a_raises["unit"] != "SPHS", "resid_health"].mean())
    L += [f"MHI faculty versus KIN and RLS faculty: {money(obs_gap)} a year (faculty-level permutation p = {p_gap:.3f}). "
          f"Non-MHI SPHS faculty versus KIN and RLS: {money(obs_non)} a year.", ""]

    L += ["### Do raises stick in the other units too?", "",
          "Same persistence measures as section A, within each unit, from 2016 (no administrative-stipend "
          "exclusions in any unit, so the SPHS row differs from section A). Early vs late compares each "
          "person's mean residual raise in 2016–19 with 2021–25.", "",
          "| Unit | Three years later | Early vs late rank correlation | ICC |", "|---|---|---|---|"]
    for u in ["SPHS", "KIN", "RLS"]:
        g = a_raises[a_raises["unit"] == u].rename(columns={"resid_unit": "r"})
        pu = persistence_block(g, max(500, args.reps // 5), rng, col="r", windows=((2016, 2019), (2021, 2025)))
        cells = []
        for k in ["lag3", "early_late", "icc"]:
            v, n, nm, p = pu[k]
            cells.append(f"{fmt_r(v)} (p={p:.3f})")
        L.append(f"| {u} | " + " | ".join(cells) + " |")
    L.append("")

    # ---------------- C. Proximity --------------------------------------------
    salary, mhi = apr.load_panel()
    members, _ = apr.load_membership(set(salary.index))
    admin = apr.load_admin()
    full2 = apr.build_rows(salary, mhi, members, admin, apr.FULL_CYCLES, horizon=2,
                           rank_changes=apr.load_rank_changes())
    tags = load_tags(list(salary.index))
    prox = proximity_rows(full2, members, tags)
    prox.to_csv(OUT_PROX, index=False, float_format="%.3f")

    L += ["## C. Does sharing research areas with the committee help?", "",
          "For each person and full review cycle: the share of that cycle's committee members (excluding the "
          "person and the Director) who share at least one SPHS research-group tag with them. Tags come from "
          "the current public faculty listing, so they are a 2026 snapshot applied to all years. Outcome: the "
          "above-median two-year raise from the APR committee analysis (promotion windows and admin years "
          "excluded). p-values shuffle proximity among faculty within each cycle.", "",
          f"Sample: {len(prox)} person-cycles, {prox['surname'].nunique()} people with tags; "
          f"{len(tags)} of {len(salary.index)} SPHS faculty matched to tags.", ""]
    if len(prox):
        L += ["| Cycle | Committee seats with tags | Mean share of seats sharing a tag | Informatics-tagged faculty: mean share |",
              "|---|---|---|---|"]
        for c, g in prox.groupby("cycle"):
            inf = g.loc[g["informatics"], "proximity"].mean()
            L.append(f"| {c}-{(c+1)%100:02d} | {int(g['tagged_seats'].max())} | {g['proximity'].mean():.2f} | "
                     f"{'–' if math.isnan(inf) else f'{inf:.2f}'} |")
        L += ["", "| Specification | Effect of going from 0% to 100% of seats sharing a tag | p |", "|---|---|---|"]
        for lab, y, pfe, ctrl, unit in [
            ("Across people, dollars", "resid", False, None, "$"),
            ("Across people, dollars, controlling for own committee membership", "resid", False, ["member"], "$"),
            ("Across people, percentile rank", "pctile", False, None, "pct"),
            ("Within person (change in proximity across cycles), dollars", "resid", True, None, "$"),
            ("Within person, percentile rank", "pctile", True, None, "pct"),
        ]:
            d = prox.copy()
            d["member"] = d["member"].astype(float)
            est, p = proximity_test(d, y, pfe, args.reps // 2, rng, ctrl)
            L.append(f"| {lab} | {money(est) if unit == '$' else f'{est:+.1f} pctile pts'} | {p:.3f} |")
        inf_share = prox.loc[prox["informatics"], "proximity"].mean()
        oth_share = prox.loc[~prox["informatics"], "proximity"].mean()
        L += ["", f"Informatics-tagged faculty share tags with {inf_share:.0%} of committee seats on average, "
              f"versus {oth_share:.0%} for everyone else.", ""]

    L += ["## Interpretation", "",
          "- **Year to year, raises do not stick.** A person's above- or below-median raise in one year says "
          "almost nothing about the next few years; most year-to-year variation looks like timing and noise. "
          "Over longer stretches there is some stability: in Kinesiology, and in SPHS when administrative "
          "stipends are left in, people above the median in the earlier years tend to be above it later. With "
          "SPHS stipend years removed (section A) the long-run correlation is weaker and not significant, so part "
          "of that stability is stipends. Removing the MHI/non-MHI difference barely changes the SPHS results.",
          "- **SPHS compresses raises more than its sister units.** In most years the spread between high and low "
          "raises is narrower in SPHS than in Kinesiology or Recreation and Leisure Studies, while the typical "
          "raise is about the same. That is what a rating process with a tight target average would produce, "
          "though stipend changes in the other units (not visible in the disclosures) could also widen their spread.",
          "- **The MHI gap is specific to MHI, not to SPHS.** Non-MHI SPHS faculty receive raises close to the "
          "Faculty of Health median; MHI faculty sit about $1,000–2,000 a year below it, smaller than before 2021. "
          "With about five MHI faculty this difference from KIN and RLS is not statistically clear on its own.",
          "- **Research-area overlap with the committee shows no consistent benefit.** Across people the sign is "
          "negative; within person it is positive but not significant. Informatics faculty share research "
          "groups with about as many committee members as everyone else, so the MHI gap is not explained by a "
          "lack of research-area representation (as measured by group tags).", ""]
    L += ["## Caveats", "",
          "- Only currently listed faculty are included in all three units, so people who left (possibly "
          "because of poor raises) are missing.",
          "- Salaries below $100,000 are not disclosed, so early-career years are missing, more so before 2016.",
          "- Research-group tags are a current snapshot and coarse; they do not capture methods or venues.",
          "- Calendar-year salary mixes two merit years, which adds noise to one-year raises.", ""]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
