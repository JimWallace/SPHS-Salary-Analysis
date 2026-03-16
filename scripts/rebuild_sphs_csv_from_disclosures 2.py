#!/usr/bin/env python3
"""Rebuild data/sphs.csv from disclosure completeness table."""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "analysis_output" / "disclosure_completeness_table.csv"
SPHS_LIST = ROOT / "SalaryData" / "SPHS Faculty List.swift"
COHORTS = ROOT / "SalaryData" / "CohortDefinitions.swift"
OUT = ROOT / "data" / "sphs.csv"


def parse_names(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r'"([^"\n]+,\s*[^"\n]+)"', text)


def parse_primary_mhi(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"let\s+FocusedMHIFacultyNamesSince2013:\s*\[String\]\s*=\s*\[(.*?)\]", text, flags=re.S)
    if not m:
        return set()
    body = m.group(1)
    names = re.findall(r'"([^"\n]+,\s*[^"\n]+)"', body)
    return {" ".join(n.strip().upper().split()) for n in names}


def canon(name: str) -> str:
    return " ".join(name.strip().upper().split())


def main() -> None:
    rows = list(csv.DictReader(TABLE.open(encoding="utf-8")))
    by_name = {canon(r["faculty_name"]): r for r in rows}

    faculty_order = parse_names(SPHS_LIST)
    primary_mhi = parse_primary_mhi(COHORTS)

    year_cols = [c for c in (rows[0].keys() if rows else []) if c and c.isdigit()]
    year_cols = sorted(year_cols, key=int)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Surname", "Given name", "MHI"] + year_cols)

        for full in faculty_order:
            key = canon(full)
            table_row = by_name.get(key, {})
            surname, given = [p.strip() for p in full.split(",", 1)]
            mhi = "true" if key in primary_mhi else "false"
            salaries = [(table_row.get(y, "") or "").strip() for y in year_cols]
            writer.writerow([surname, given, mhi] + salaries)

    print(f"Wrote rebuilt SPHS salary table: {OUT}")


if __name__ == "__main__":
    main()
