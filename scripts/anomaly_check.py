#!/usr/bin/env python3
"""Independent checks on the anomaly screen outputs.

Usage:
  python3 scripts/anomaly_check.py

1. Hand check: recomputes the subject's fitted salary in every specification as the sum of
   (model-matrix value x coefficient) from analysis_output/anomaly_subject_design.csv, and compares it
   with analysis_output/anomaly_subject_results.csv.
2. Independent refit: rebuilds the design matrix for the two main specifications in Python (own
   factor coding, numpy least squares) on the same people (data/private/anomaly_model_samples.csv) and
   compares the subject's prediction and the adjusted R^2 with R's.
3. Name audit: no colleague's name may appear in any public output (analysis_output/, output/,
   docs/, the report source and its PDF text). Prints file and line only, never the name.

Exits non-zero if any check fails.
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

import anomaly_common as ac
import promotion_cohort as pc

ROOT = ac.ROOT
OUT = ac.OUT_DIR
TOL = 1.0  # dollars


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def hand_check() -> list[str]:
    errors = []
    design = read(OUT / "anomaly_subject_design.csv")
    results = {r["spec"]: float(r["fitted"]) for r in read(OUT / "anomaly_subject_results.csv")}
    for spec, fitted in results.items():
        rows = [r for r in design if r["spec"] == spec]
        total = sum(float(r["x"]) * float(r["coef"]) for r in rows if r["coef"] not in ("", "NA"))
        status = "ok" if abs(total - fitted) <= TOL else "MISMATCH"
        print(f"  hand check {spec:22s} R {fitted:12,.2f}  sum(x*b) {total:12,.2f}  {status}")
        if status != "ok":
            errors.append(f"hand check {spec}")
    return errors


def dummies(values: list[str], ref: str) -> tuple[list[str], np.ndarray]:
    levels = sorted(set(values) - {ref})
    return levels, np.array([[1.0 if v == lev else 0.0 for lev in levels] for v in values]).reshape(len(values), -1)


def refit(spec: str, stage: int) -> list[str]:
    inputs = {r["person_id"]: r for r in read(ac.PRIVATE / "anomaly_inputs.csv")}
    sample = [r for r in read(ac.PRIVATE / "anomaly_model_samples.csv") if r["spec"] == spec]
    subject = next(r for r in inputs.values() if r["is_subject"] == "1")
    people = [inputs[r["person_id"]] for r in sample] + [subject]
    y = np.array([float(r["salary"]) for r in sample])
    yrs = np.array([2025 - int(p["hire_year"]) for p in people], dtype=float)
    lag = np.array([float(p["lag"]) for p in people])
    cols = [np.ones(len(people)), lag, yrs, yrs ** 2]
    if stage == 1:
        cats = [("highest_degree", "Doctoral"), ("current_rank", "Assistant"), ("rank_at_hire", "Assistant")]
    else:
        groups = [p["academic_group_s2"] for p in people]
        counts = {g: groups[:-1].count(g) for g in set(groups)}
        for p in people:
            if counts.get(p["academic_group_s2"], 0) < 3 and p["academic_group_s2"] != "Health":
                p["academic_group_s2"] = "Other"
        cats = [("academic_group_s2", "Health")]
    for field, ref in cats:
        values = [p[field] for p in people]
        present = set(values[:-1])
        ref = ref if ref in present else max(present, key=values[:-1].count)
        _, m = dummies(values, ref)
        if m.size:
            cols.append(m)
    X = np.column_stack(cols)
    # Lag x rank-at-hire, if R kept it: R's coefficient names say so.
    coef_terms = {r["term"] for r in read(OUT / "anomaly_coefficients.csv") if r["spec"] == spec}
    if any(t.startswith("lag:rank_at_hire") for t in coef_terms):
        values = [p["rank_at_hire"] for p in people]
        _, m = dummies(values, "Assistant")
        X = np.column_stack([X, m * lag[:, None]])
    Xo, xs = X[:-1], X[-1]
    keep = np.linalg.matrix_rank(Xo) == Xo.shape[1]
    b, *_ = np.linalg.lstsq(Xo, y, rcond=None)
    pred = float(xs @ b)
    resid = y - Xo @ b
    n, k = Xo.shape
    rank = np.linalg.matrix_rank(Xo)
    r2 = 1 - resid @ resid / ((y - y.mean()) @ (y - y.mean()))
    adj = 1 - (1 - r2) * (n - 1) / (n - rank)
    r_res = next(r for r in read(OUT / "anomaly_subject_results.csv") if r["spec"] == spec)
    r_fit = next(r for r in read(OUT / "anomaly_fit_summary.csv") if r["spec"] == spec)
    ok = abs(pred - float(r_res["fitted"])) <= TOL and abs(adj - float(r_fit["adj_r2"])) < 1e-6
    print(f"  refit {spec:10s} numpy {pred:12,.2f} vs R {float(r_res['fitted']):12,.2f}; adj R2 {adj:.6f} vs "
          f"{float(r_fit['adj_r2']):.6f}; full rank {keep}  {'ok' if ok else 'MISMATCH'}")
    return [] if ok else [f"refit {spec}"]


def name_audit() -> list[str]:
    """Full names ("Given Surname", "Surname, Given") and distinctive surnames of everyone in the inputs
    and the Health roster, other than the subject."""
    people = read(ac.PRIVATE / "anomaly_inputs.csv")
    targets = {r["person_id"]: r for r in read(ac.PRIVATE / "anomaly_targets.csv")}
    roster = read(ac.PRIVATE / "health_roster.csv")
    names: set[str] = set()
    surnames: set[str] = set()
    for p in people:
        if p["is_subject"] == "1":
            continue
        t = targets[p["person_id"]]
        sur, giv = t["disc_surname"].title(), t["disc_given"].split()[0].title()
        names |= {f"{giv} {sur}", f"{sur}, {giv}"}
        for s in t["disc_surname"].split():
            if len(s) >= 6:
                surnames.add(s.title())
        names.add(t["display_name"])
    for r in roster:
        names.add(r["name"])
    surnames -= {"Wallace"}
    files = [p for d in ("analysis_output", "output", "docs") for p in (ROOT / d).glob("**/*")
             if p.is_file() and "anomaly" in p.name]
    files += [ROOT / "anomaly_report.tex"]
    pdf = ROOT / "anomaly_report.pdf"
    texts = []
    for f in files:
        if f.exists():
            texts.append((f, f.read_text(encoding="utf-8", errors="replace")))
    if pdf.exists():
        texts.append((pdf, subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout))
    hits = 0
    for f, text in texts:
        for i, line in enumerate(text.splitlines(), 1):
            for n in names:
                if n and n in line:
                    print(f"  NAME HIT (full name) {f.relative_to(ROOT)}:{i}")
                    hits += 1
            for s in surnames:
                if re.search(rf"\b{re.escape(s)}\b", line):
                    print(f"  NAME HIT (surname) {f.relative_to(ROOT)}:{i}")
                    hits += 1
    print(f"  name audit: {len(texts)} files, {len(names)} names and {len(surnames)} surnames checked, {hits} hits")
    return ["name audit"] if hits else []


def main() -> None:
    errors = []
    print("1. Hand check of the subject's fitted values")
    errors += hand_check()
    print("2. Independent refit (numpy)")
    errors += refit("S1_main", 1) + refit("S2_main", 2)
    print("3. Name audit of public outputs")
    errors += name_audit()
    if errors:
        sys.exit("FAILED: " + ", ".join(errors))
    print("All checks passed.")


if __name__ == "__main__":
    main()
