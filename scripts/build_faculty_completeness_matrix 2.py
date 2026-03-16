#!/usr/bin/env python3
"""Build combined faculty completeness matrix (disclosure + public + CV)."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCLOSURE = ROOT / "analysis_output" / "disclosure_completeness_table.csv"
PUBLIC = ROOT / "analysis_output" / "disclosure_public_crosscheck.csv"
CV = ROOT / "analysis_output" / "faculty_cv_crosswalk.csv"
OUT = ROOT / "analysis_output" / "faculty_completeness_matrix.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    disc_rows = read_csv(DISCLOSURE)
    pub_rows = read_csv(PUBLIC)
    cv_rows = read_csv(CV)

    pub_by = {r.get("faculty_name", ""): r for r in pub_rows}
    cv_by = {r.get("faculty_name", ""): r for r in cv_rows}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "faculty_name",
                "first_disclosure_year",
                "last_disclosure_year",
                "disclosure_year_count",
                "missing_internal_years",
                "public_match_status",
                "public_name",
                "cv_match_status",
                "cv_filename",
            ],
        )
        writer.writeheader()

        for row in sorted(disc_rows, key=lambda r: r.get("faculty_name", "")):
            name = row.get("faculty_name", "")
            pub = pub_by.get(name, {})
            cv = cv_by.get(name, {})
            writer.writerow(
                {
                    "faculty_name": name,
                    "first_disclosure_year": row.get("first_disclosure_year", ""),
                    "last_disclosure_year": row.get("last_disclosure_year", ""),
                    "disclosure_year_count": row.get("disclosure_year_count", ""),
                    "missing_internal_years": row.get("missing_internal_years", ""),
                    "public_match_status": pub.get("public_match_status", ""),
                    "public_name": pub.get("public_name", ""),
                    "cv_match_status": cv.get("cv_match_status", ""),
                    "cv_filename": cv.get("cv_filename", ""),
                }
            )

    print(f"Wrote faculty completeness matrix: {OUT}")


if __name__ == "__main__":
    main()
