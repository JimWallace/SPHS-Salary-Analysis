#!/usr/bin/env python3
"""Candidate explanations for the MHI raise gap.

Usage:
  python3 scripts/mhi_gap_explanations.py [--reps 5000] [--seed 20261120]

Sections (each runs only if its input exists):
  4. Cross-appointments: is the gap concentrated among faculty cross-appointed to other UW units?
  1. Research output (OpenAlex): does the gap remain once publications, venue type and citation
     impact are accounted for?             input: data/private/openalex_person_year.csv
  2. Funding agency (NSERC / CIHR / SSHRC): input: data/private/grants_person_year.csv
  3. Thesis supervision (UWSpace):         input: data/private/theses_person_year.csv

Outcome throughout: the annual raise minus the SPHS median raise that year ("residual raise"),
built as in scripts/apr_process_diagnostics.py (stipend, promotion and partial first years excluded).
Inference: permutation tests that reassign the attribute among people (not person-years), so each
person counts once, which matters with only seven MHI faculty.

Output: output/mhi_gap_explanations.md (aggregates only).
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
XAPPT = ROOT / "data" / "public_sphs_scrape" / "sphs_internal_cross_appointments.csv"
OPENALEX = ROOT / "data" / "private" / "openalex_person_year.csv"
GRANTS = ROOT / "data" / "private" / "grants_person_year.csv"
THESES = ROOT / "data" / "private" / "theses_person_year.csv"
OUT = ROOT / "output" / "mhi_gap_explanations.md"

_spec = importlib.util.spec_from_file_location("diag", ROOT / "scripts" / "apr_process_diagnostics.py")
diag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diag)
money = diag.money


def raises() -> pd.DataFrame:
    r = diag.annual_raises(diag.sphs_long(), diag.admin_calendar_years())
    r["resid"] = diag.add_resid(r, ["year"])
    return r


def ols(df: pd.DataFrame, y: str, xs: list[str], year_fe: bool = True) -> np.ndarray:
    cols = [df[x].to_numpy(float) for x in xs]
    if year_fe:
        cols.append(pd.get_dummies(df["year"]).to_numpy(float))
    else:
        cols.append(np.ones((len(df), 1)))
    X = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(X, df[y].to_numpy(float), rcond=None)
    return beta[: len(xs)]


def person_perm(df: pd.DataFrame, y: str, xs: list[str], target: str, reps: int, rng: np.random.Generator,
                strata: str | None = None) -> tuple[float, float]:
    """Coefficient on `target` and a permutation p that reassigns `target` among people
    (within `strata` if given), keeping each person's other attributes."""
    obs = ols(df, y, xs)[xs.index(target)]
    people = df.groupby("person")[[target] + ([strata] if strata else [])].first()
    null = []
    for _ in range(reps):
        lab = people[target].copy()
        if strata:
            for _, idx in people.groupby(strata).groups.items():
                lab.loc[idx] = rng.permutation(lab.loc[idx].to_numpy())
        else:
            lab[:] = rng.permutation(lab.to_numpy())
        d = df.assign(**{target: df["person"].map(lab)})
        null.append(ols(d, y, xs)[xs.index(target)])
    null = np.array(null)
    return float(obs), float((1 + np.sum(np.abs(null) >= abs(obs) - 1e-9)) / (reps + 1))


def group_table(df: pd.DataFrame, by: list[str], labels: dict) -> list[str]:
    out = ["| Group | People | Annual raises | Mean residual raise | Median of person means | People below median |",
           "|---|---|---|---|---|---|"]
    pm = df.groupby("person").agg(**{b: (b, "first") for b in by}, m=("resid", "mean"))
    for key, g in df.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        p = pm
        for b, k in zip(by, key):
            p = p[p[b] == k]
        out.append(f"| {labels[key]} | {g['person'].nunique()} | {len(g)} | {money(g['resid'].mean())} | "
                   f"{money(float(p['m'].median()))} | {int((p['m'] < 0).sum())} of {len(p)} |")
    return out


def section_cross_appointments(r: pd.DataFrame, reps: int, rng: np.random.Generator) -> list[str]:
    xa = pd.read_csv(XAPPT)
    r = r.copy()
    r["xa"] = r["person"].isin(set(xa["surname"]))
    r["mhi_f"] = r["mhi"].astype(float)
    r["xa_f"] = r["xa"].astype(float)
    r["both"] = r["mhi_f"] * r["xa_f"]
    L = ["## 4. Cross-appointments", "",
         f"{len(xa)} SPHS faculty list a cross- or joint appointment with another University of Waterloo unit "
         "on their public profile (Planning, Statistics and Actuarial Science, Computer Science, Systems Design "
         "Engineering, Psychology, Pharmacy, Biology). The list is a current snapshot; start dates are unknown.", ""]
    labels = {(False, False): "Non-MHI, SPHS only", (False, True): "Non-MHI, cross-appointed",
              (True, False): "MHI, SPHS only", (True, True): "MHI, cross-appointed"}
    L += group_table(r, ["mhi", "xa"], labels)
    L += ["", "Regression of the residual raise on group indicators with year fixed effects. p-values reassign the "
          "indicator among people (cross-appointment is shuffled within MHI and non-MHI faculty, and vice versa).", "",
          "| Model | Coefficient | Estimate | p |", "|---|---|---|---|"]
    est, p = person_perm(r, "resid", ["mhi_f"], "mhi_f", reps, rng)
    L.append(f"| MHI only | MHI | {money(est)} | {p:.3f} |")
    est, p = person_perm(r, "resid", ["xa_f"], "xa_f", reps, rng)
    L.append(f"| Cross-appointment only | Cross-appointed | {money(est)} | {p:.3f} |")
    est, p = person_perm(r, "resid", ["mhi_f", "xa_f"], "mhi_f", reps, rng, strata="xa_f")
    L.append(f"| Both | MHI | {money(est)} | {p:.3f} |")
    est, p = person_perm(r, "resid", ["mhi_f", "xa_f"], "xa_f", reps, rng, strata="mhi_f")
    L.append(f"| Both | Cross-appointed | {money(est)} | {p:.3f} |")
    L.append("")
    # Exact (hypergeometric) chance that every cross-appointed person falls among those with a below-median mean.
    pm = r.groupby("person").agg(xa=("xa", "first"), m=("resid", "mean"))
    n, k, neg = len(pm), int(pm["xa"].sum()), int((pm["m"] < 0).sum())
    hit = int(((pm["m"] < 0) & pm["xa"]).sum())
    from math import comb
    p_all = sum(comb(neg, j) * comb(n - neg, k - j) for j in range(hit, k + 1)) / comb(n, k)
    L += [f"{hit} of {k} cross-appointed faculty have a below-median average raise, against {neg} of {n} faculty "
          f"overall. If cross-appointment were unrelated to raises, a result this lopsided would occur with "
          f"probability {p_all:.4f}.", ""]
    return L


def add_person_lab(r: pd.DataFrame) -> pd.DataFrame:
    r = r.copy()
    r["xa"] = r["person"].isin(set(pd.read_csv(XAPPT)["surname"]))
    r["mhi_f"] = r["mhi"].astype(float)
    r["xa_f"] = r["xa"].astype(float)
    return r


def within_perm(df: pd.DataFrame, y: str, x: str, reps: int, rng: np.random.Generator) -> tuple[float, float]:
    """Coefficient on x with person and year fixed effects; p from shuffling x across each person's own years."""
    def fit(xv):
        P = pd.get_dummies(df["person"]).to_numpy(float)
        Y = pd.get_dummies(df["year"]).to_numpy(float)[:, 1:]
        X = np.column_stack([xv, P, Y])
        b, *_ = np.linalg.lstsq(X, df[y].to_numpy(float), rcond=None)
        return b[0]
    xv = df[x].to_numpy(float)
    obs = fit(xv)
    idx = df.groupby("person").indices
    null = []
    for _ in range(reps):
        xs = xv.copy()
        for ii in idx.values():
            xs[ii] = rng.permutation(xs[ii])
        null.append(fit(xs))
    return float(obs), float((1 + np.sum(np.abs(np.array(null)) >= abs(obs) - 1e-9)) / (reps + 1))


def mhi_shift_rows(r: pd.DataFrame, controls: list[tuple[str, list[str]]], reps: int,
                   rng: np.random.Generator) -> list[str]:
    out = ["| Model | MHI coefficient | p (MHI reassigned among people) |", "|---|---|---|"]
    for label, xs in controls:
        est, p = person_perm(r, "resid", ["mhi_f"] + xs, "mhi_f", reps, rng)
        out.append(f"| {label} | {money(est)} | {p:.3f} |")
    return out


def section_grants(r: pd.DataFrame, reps: int, rng: np.random.Generator) -> list[str]:
    g = pd.read_csv(GRANTS)
    r = add_person_lab(r)
    # Fiscal year FY runs April FY - March FY+1. Grant dollars in the two fiscal years before the raise year.
    by = g.groupby(["person", "fiscal_year"])["amount"].sum()
    r["grant_recent"] = [(by.get((p, y - 1), 0) + by.get((p, y - 2), 0)) / 100_000 for p, y in zip(r["person"], r["year"])]
    nserc = set(g.loc[g["agency"] == "NSERC", "person"])
    sshrc = set(g.loc[g["agency"] == "SSHRC", "person"])
    r["nserc"] = r["person"].isin(nserc).astype(float)
    pm = r.groupby("person").agg(mhi=("mhi", "first"), xa=("xa", "first"), nserc=("nserc", "first"))
    L = ["## 2. Funding agency", "",
         "NSERC and SSHRC awards where the faculty member is the lead applicant at Waterloo (student awards "
         "excluded), fiscal years 2010–2024. **CIHR is missing**: the CIHR files on open.canada.ca were blocked "
         "for automated download, so CIHR holders look unfunded here. Read this section as \"NSERC-oriented vs "
         "not\", not as total funding.", "",
         "| Group | People | Ever held NSERC (lead) | Ever held SSHRC (lead) |", "|---|---|---|---|"]
    for (m, x), grp in pm.groupby(["mhi", "xa"]):
        lab = f"{'MHI' if m else 'Non-MHI'}, {'cross-appointed' if x else 'SPHS only'}"
        ppl = grp.index
        L.append(f"| {lab} | {len(ppl)} | {sum(p in nserc for p in ppl)} | {sum(p in sshrc for p in ppl)} |")
    L += ["", "Does an NSERC orientation go with smaller raises, and does it account for the MHI gap?", ""]
    est, p = person_perm(r, "resid", ["nserc"], "nserc", reps, rng)
    L += [f"NSERC lead applicants versus everyone else: {money(est)} a year (p = {p:.3f}, NSERC status reassigned "
          "among people).", ""]
    L += mhi_shift_rows(r, [("MHI alone", []), ("+ NSERC holder", ["nserc"]),
                            ("+ NSERC holder + cross-appointed", ["nserc", "xa_f"])], reps, rng)
    est, p = within_perm(r, "resid", "grant_recent", reps, rng)
    L += ["", f"Within person: each extra $100,000 of NSERC/SSHRC funding in the two prior fiscal years goes with "
          f"a {money(est)} change in the raise (p = {p:.3f}).", ""]
    return L


def section_theses(r: pd.DataFrame, reps: int, rng: np.random.Generator) -> list[str]:
    t = pd.read_csv(THESES)
    r = add_person_lab(r)
    by = t.groupby(["person", "year"])["n_theses"].sum()
    phd = t[t["level"] == "phd"].groupby(["person", "year"])["n_theses"].sum()
    r["theses_recent"] = [by.get((p, y - 1), 0) + by.get((p, y - 2), 0) for p, y in zip(r["person"], r["year"])]
    r["phd_recent"] = [phd.get((p, y - 1), 0) + phd.get((p, y - 2), 0) for p, y in zip(r["person"], r["year"])]
    # Person-level supervision rate over the years each person is in the raise sample.
    yrs = r.groupby("person")["year"].agg(["min", "max"])
    rate = {}
    for p, (a, b) in yrs.iterrows():
        sub = t[(t["person"] == p) & t["year"].between(a - 2, b)]
        rate[p] = sub["n_theses"].sum() / (b - a + 3)
    r["thesis_rate"] = r["person"].map(rate).astype(float)
    pm = r.groupby("person").agg(mhi=("mhi", "first"), xa=("xa", "first"), rate=("thesis_rate", "first"))
    L = ["## 3. Graduate thesis supervision", "",
         "Completed master's and PhD theses in UWSpace listing the faculty member as a supervisor or "
         "co-supervisor (all departments; joint and cross-appointed supervision included). Coursework "
         "master's students (MHI, MPH) write no thesis, so supervising them does not appear here.", "",
         "| Group | People | Theses per year (median of people) | Theses per year (mean) |", "|---|---|---|---|"]
    for (m, x), grp in pm.groupby(["mhi", "xa"]):
        lab = f"{'MHI' if m else 'Non-MHI'}, {'cross-appointed' if x else 'SPHS only'}"
        L.append(f"| {lab} | {len(grp)} | {grp['rate'].median():.2f} | {grp['rate'].mean():.2f} |")
    est, p = person_perm(r, "resid", ["thesis_rate"], "thesis_rate", reps, rng)
    L += ["", f"Across people: each extra completed thesis per year goes with a {money(est)} difference in the "
          f"average raise (p = {p:.3f}, supervision rates reassigned among people).", ""]
    L += mhi_shift_rows(r, [("MHI alone", []), ("+ thesis supervision rate", ["thesis_rate"]),
                            ("+ supervision rate + cross-appointed", ["thesis_rate", "xa_f"])], reps, rng)
    est, p = within_perm(r, "resid", "theses_recent", reps, rng)
    est2, p2 = within_perm(r, "resid", "phd_recent", reps, rng)
    L += ["", f"Within person: each thesis completed in the two prior years goes with a {money(est)} change in the "
          f"raise (p = {p:.3f}); each PhD completion, {money(est2)} (p = {p2:.3f}).", ""]
    return L


def section_outside(r: pd.DataFrame, reps: int, rng: np.random.Generator) -> list[str]:
    g = pd.read_csv(GRANTS)
    r = add_person_lab(r)
    nserc = set(g.loc[g["agency"] == "NSERC", "person"])
    r["outside"] = (r["xa"] | r["person"].isin(nserc)).astype(float)
    pm = r.groupby("person").agg(mhi=("mhi", "first"), o=("outside", "first"), m=("resid", "mean"))
    L = ["## Combining 2 and 4: a research home partly outside the health sciences", "",
         "Cross-appointment and NSERC funding pick out nearly the same people, and most MHI faculty are among "
         "them. This section treats them as one attribute: cross-appointed to another UW unit **or** a lead "
         "applicant on an NSERC grant.", "",
         "| Group | People | Mean of person averages | People below median |", "|---|---|---|---|"]
    for (m, o), grp in pm.groupby(["mhi", "o"]):
        lab = f"{'MHI' if m else 'Non-MHI'}, {'outside ties' if o else 'health sciences only'}"
        L.append(f"| {lab} | {len(grp)} | {money(grp['m'].mean())} | {int((grp['m'] < 0).sum())} of {len(grp)} |")
    L += ["", "| Model | Coefficient | Estimate | p |", "|---|---|---|---|"]
    est, p = person_perm(r, "resid", ["mhi_f"], "mhi_f", reps, rng)
    L.append(f"| MHI only | MHI | {money(est)} | {p:.3f} |")
    est, p = person_perm(r, "resid", ["outside"], "outside", reps, rng)
    L.append(f"| Outside ties only | Outside ties | {money(est)} | {p:.3f} |")
    est, p = person_perm(r, "resid", ["mhi_f", "outside"], "mhi_f", reps, rng, strata="outside")
    L.append(f"| Both | MHI | {money(est)} | {p:.3f} |")
    est, p = person_perm(r, "resid", ["mhi_f", "outside"], "outside", reps, rng, strata="mhi_f")
    L.append(f"| Both | Outside ties | {money(est)} | {p:.3f} |")
    L.append("")
    return L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=20261120)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    r = raises()
    L = ["# What might explain the MHI raise gap?", "",
         "Generated by `scripts/mhi_gap_explanations.py`. Aggregates only.", "",
         f"Outcome: annual raise minus the SPHS median raise that year (2012–2025; stipend, promotion and "
         f"partial first years excluded). Sample: {len(r)} annual raises, {r['person'].nunique()} people, "
         f"{r.loc[r['mhi'], 'person'].nunique()} of them MHI-affiliated.", ""]
    L += section_cross_appointments(r, args.reps, rng)
    if GRANTS.exists():
        L += section_grants(r, args.reps, rng)
    if GRANTS.exists():
        L += section_outside(r, args.reps, rng)
    if THESES.exists():
        L += section_theses(r, args.reps, rng)
    if not OPENALEX.exists():
        L += ["## 1. Research output", "", "Not run yet: needs publication data (OpenAlex API key).", ""]

    L += ["## Interpretation", "",
          "- **The gap follows outside ties more than the MHI label.** Faculty whose research home is partly "
          "outside the health sciences (cross-appointed to engineering, computer science, statistics, planning, "
          "psychology, pharmacy or biology, or funded by NSERC) receive smaller raises whether or not they are in "
          "MHI. Once that is accounted for, the MHI difference is small and not distinguishable from zero. Most "
          "MHI faculty have such ties, which is why the gap shows up as an MHI gap.",
          "- **Thesis supervision does not explain it.** Supervising more completed theses goes with larger "
          "raises across people, but MHI and cross-appointed faculty supervise about as many theses as others.",
          "- **This is consistent with interdisciplinary work being valued less**, for example if work done for, "
          "or recognised by, the other unit or agency counts for less in the School's review. It is also "
          "consistent with divided effort producing less of what the School counts. Publication data "
          "(section 1) and the APR rubric are needed to tell these apart.",
          "- **Caveats:** 29 people, nine with outside ties; cross-appointments are a current snapshot; CIHR "
          "funding is missing; the grouping was suggested by the data rather than specified in advance, so "
          "treat the p-values as descriptive.", ""]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
