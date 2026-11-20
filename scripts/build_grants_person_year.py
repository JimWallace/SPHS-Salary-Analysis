#!/usr/bin/env python3
"""Match SPHS faculty to NSERC and SSHRC award records (lead applicant), by fiscal year.

Usage:
  python3 scripts/build_grants_person_year.py --dir DIR

DIR holds the agencies' open-data award files, named NSERC_<fy>.csv and SSHRC_<fy>.csv
(from open.canada.ca: "NSERC's Awards Data" and "SSHRC's Expenditures File"). CIHR files,
if present as CIHR_<fy>.xlsx, are read too.

Matching: University of Waterloo records whose "Surname, Given" name matches an SPHS panel
surname and first given name. Student scholarships and fellowships are dropped (they would
belong to students who share a faculty member's name).

Outputs (gitignored, names):
- data/private/grants_person_year.csv   person, fiscal_year, agency, amount, n_awards
- data/private/grants_match_review.csv  every matched record, with department and program, for checking
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "sphs.csv"
OUT = ROOT / "data" / "private" / "grants_person_year.csv"
OUT_REVIEW = ROOT / "data" / "private" / "grants_match_review.csv"
STUDENT = re.compile(r"scholarship|fellowship|doctoral|master|undergraduate|postgraduate|USRA|CGS|PGS|Vanier|Banting",
                     re.I)


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z' -]", " ", text).upper().split())


def first_given(text: str) -> str:
    toks = [t for t in norm(text).split() if len(t) > 1]
    return toks[0] if toks else ""


def panel_keys() -> dict[tuple[str, str], str]:
    keys = {}
    with PANEL.open() as f:
        for r in csv.DictReader(f):
            sur = norm(r["Surname"])
            given = first_given(r["Given name"])
            keys[(sur, given)] = r["Surname"]
            # Double-barrelled surnames: also accept the last part (e.g. TAIT NEUFELD -> NEUFELD).
            for part in sur.split():
                if len(part) > 3:
                    keys.setdefault((part, given), r["Surname"])
    return keys


def read_csv_any(path: Path):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with path.open(encoding=enc, newline="") as f:
                rows = list(csv.DictReader(f))
            return rows
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Cannot decode {path}")


def pick(row: dict, *names: str) -> str:
    for n in names:
        for k in row:
            if k and k.strip().lower().startswith(n.lower()):
                return (row[k] or "").strip()
    return ""


def match_name(name: str, keys: dict) -> str | None:
    if "," not in name:
        return None
    sur, given = name.split(",", 1)
    return keys.get((norm(sur), first_given(given)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, required=True)
    args = ap.parse_args()
    keys = panel_keys()
    agg = defaultdict(lambda: [0.0, set()])
    review = []

    for path in sorted(args.dir.glob("NSERC_*.csv")):
        for row in read_csv_any(path):
            inst = pick(row, "Institution")
            if "waterloo" not in inst.lower() or "wilfrid" in inst.lower():
                continue
            person = match_name(pick(row, "Name"), keys)
            program = pick(row, "ProgramNameEN", "ProgramNaneEN")  # the 2011 file misspells the header
            if not person or STUDENT.search(program) or "training" in pick(row, "GroupEN").lower():
                continue
            fy = int(pick(row, "FiscalYear"))
            amt = float(re.sub(r"[^0-9.]", "", pick(row, "AwardAmount")) or 0)
            agg[(person, fy, "NSERC")][0] += amt
            agg[(person, fy, "NSERC")][1].add(pick(row, "ApplicationID"))
            review.append({"person": person, "agency": "NSERC", "fiscal_year": fy, "amount": amt,
                           "name_in_record": pick(row, "Name"), "department": pick(row, "Department"),
                           "program": program})

    for path in sorted(args.dir.glob("SSHRC_*.csv")):
        for row in read_csv_any(path):
            inst = pick(row, "Institution")
            if "university of waterloo" not in inst.lower():
                continue
            role = pick(row, "role", "Role")
            if role and not role.lower().startswith("applicant"):
                continue
            person = match_name(pick(row, "Name"), keys)
            program = pick(row, "ProgramNameEN", "Program")
            if not person or STUDENT.search(program):
                continue
            fy = int(float(pick(row, "FiscalYear", "Fiscal_Year")))
            amt = float(re.sub(r"[^0-9.]", "", pick(row, "AwardAmount", "Amount")) or 0)
            key = pick(row, "File_Number", "cle")
            agg[(person, fy, "SSHRC")][0] += amt
            agg[(person, fy, "SSHRC")][1].add(key)
            review.append({"person": person, "agency": "SSHRC", "fiscal_year": fy, "amount": amt,
                           "name_in_record": pick(row, "Name"), "department": "", "program": program})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["person", "fiscal_year", "agency", "amount", "n_awards"])
        for (person, fy, ag), (amt, ids) in sorted(agg.items()):
            w.writerow([person, fy, ag, round(amt, 2), len(ids)])
    with OUT_REVIEW.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(review[0].keys()))
        w.writeheader()
        w.writerows(review)
    people = {p for p, _, _ in agg}
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(agg)} person-year-agency rows, {len(people)} people")


if __name__ == "__main__":
    main()
