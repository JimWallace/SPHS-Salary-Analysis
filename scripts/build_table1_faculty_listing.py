#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROSTER_PATH = ROOT / "data" / "public_sphs_scrape" / "faculty_roster_with_groups.csv"
COMPLETENESS_PATH = ROOT / "analysis_output" / "faculty_completeness_matrix.csv"
VERIFICATION_PATH = ROOT / "analysis_output" / "appendix_analysis_verification_matrix.csv"
CV_CROSSWALK_PATH = ROOT / "analysis_output" / "cv_start_year_crosswalk.csv"
OUTPUT_PATH = ROOT / "analysis_output" / "table1_faculty_listing.csv"


def normalize_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def load_completeness() -> dict[str, dict[str, str]]:
    by_public_name: dict[str, dict[str, str]] = {}
    with COMPLETENESS_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            public_name = (row.get("public_name") or "").strip()
            if public_name:
                by_public_name[normalize_name(public_name)] = row
    return by_public_name


def load_verification() -> dict[str, tuple[str, str]]:
    by_faculty_name: dict[str, tuple[str, str]] = {}
    with VERIFICATION_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            faculty_name = (row.get("Faculty") or "").strip()
            by_faculty_name[normalize_name(faculty_name)] = (
                (row.get("MHI Classification") or "").strip(),
                (row.get("Start Year") or "").strip(),
            )
    return by_faculty_name


def load_cv_crosswalk() -> dict[str, dict[str, str]]:
    by_salary_name: dict[str, dict[str, str]] = {}
    with CV_CROSSWALK_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            salary_name = (row.get("salary_name") or "").strip()
            if salary_name:
                by_salary_name[normalize_name(salary_name)] = row
    return by_salary_name


def infer_start_display(
    faculty_salary_name: str, first_disclosure_year: str, cv_row: dict[str, str] | None
) -> str:
    if cv_row:
        cv_year = (cv_row.get("cv_start_year") or "").strip()
        confidence = (cv_row.get("cv_start_confidence") or "").strip().lower()
        method_note = (cv_row.get("method_note") or "").strip().lower()
        # Treat high/medium confidence CV years and manual overrides as known.
        if cv_year and (
            confidence in {"high", "medium"} or method_note.startswith("manual override")
        ):
            return cv_year

    if first_disclosure_year:
        return f"<{first_disclosure_year}"

    return ""


def build_table_rows() -> list[dict[str, str]]:
    completeness = load_completeness()
    verification = load_verification()
    crosswalk = load_cv_crosswalk()

    rows: list[dict[str, str]] = []
    with ROSTER_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            public_name = (row.get("faculty_name") or "").strip()
            matched = completeness.get(normalize_name(public_name))

            mhi_classification = ""
            start_year_display = ""
            if matched:
                faculty_salary_name = (matched.get("faculty_name") or "").strip()
                faculty_key = normalize_name(faculty_salary_name)
                mhi_classification, _ = verification.get(faculty_key, ("", ""))
                first_disclosure_year = (matched.get("first_disclosure_year") or "").strip()
                cv_row = crosswalk.get(faculty_key)
                start_year_display = infer_start_display(
                    faculty_salary_name, first_disclosure_year, cv_row
                )

            rows.append(
                {
                    "Faculty": public_name,
                    "MHI Classification": mhi_classification,
                    "Start Year": start_year_display,
                }
            )

    rows.sort(key=lambda item: item["Faculty"])
    return rows


def main() -> None:
    rows = build_table_rows()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Faculty", "MHI Classification", "Start Year"],
        )
        writer.writeheader()
        writer.writerows(rows)

    missing_classification = sum(1 for row in rows if not row["MHI Classification"])
    print(f"Wrote Table 1 faculty listing: {OUTPUT_PATH} ({len(rows)} rows)")
    print(
        "Rows missing SPHS salary-panel mapping "
        f"(blank MHI/Start Year): {missing_classification}"
    )


if __name__ == "__main__":
    main()
