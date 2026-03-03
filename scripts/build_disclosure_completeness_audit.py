#!/usr/bin/env python3
"""Build a full disclosure completeness table for SPHS faculty and cross-check with public listing.

Outputs:
- analysis_output/disclosure_completeness_table.csv
- analysis_output/disclosure_completeness_summary.csv
- analysis_output/disclosure_public_crosscheck.csv
"""

from __future__ import annotations

import csv
import html
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
SPHS_LIST_PATH = ROOT / "SalaryData" / "SPHS Faculty List.swift"
PUBLIC_ROSTER_PATH = ROOT / "data" / "public_sphs_scrape" / "faculty_roster_with_groups.csv"

OUT_TABLE = ROOT / "analysis_output" / "disclosure_completeness_table.csv"
OUT_SUMMARY = ROOT / "analysis_output" / "disclosure_completeness_summary.csv"
OUT_PUBLIC = ROOT / "analysis_output" / "disclosure_public_crosscheck.csv"

DISCLOSURE_BASE = "https://uwaterloo.ca/about/accountability/salary-disclosure-{}"


@dataclass
class FacultyRef:
    canonical: str
    raw_name: str
    surname_raw: str
    given_raw: str
    surname_tokens: Set[str]
    given_tokens: List[str]


def tokens(text: str) -> List[str]:
    return re.findall(r"[A-Z]+", text.upper())


def parse_swift_names(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r'"([^"\n]+,\s*[^"\n]+)"', text)


def make_faculty_ref(name: str) -> FacultyRef:
    surname, given = [part.strip() for part in name.split(",", 1)]
    surname_tokens = set(tokens(surname))
    given_tokens = tokens(given)
    canonical = f"{surname.upper()}, {given.upper()}"
    return FacultyRef(
        canonical=canonical,
        raw_name=name,
        surname_raw=surname,
        given_raw=given,
        surname_tokens=surname_tokens,
        given_tokens=given_tokens,
    )


def clean_text(fragment: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", fragment)
    unescaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def parse_disclosure_rows(page_html: str) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, flags=re.IGNORECASE | re.DOTALL):
        cells = [clean_text(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.IGNORECASE | re.DOTALL)]
        if len(cells) < 5:
            continue
        surname, given, salary = cells[0], cells[1], cells[3]
        if not surname or not given:
            continue
        if surname.lower() == "surname" and given.lower().startswith("given"):
            continue
        rows.append((surname, given, salary))
    return rows


def given_compatible(list_given: List[str], row_given: List[str]) -> bool:
    if not list_given or not row_given:
        return False
    lg = list_given[0]
    rg = row_given[0]
    if lg == rg:
        return True
    if len(lg) == 1 and rg.startswith(lg):
        return True
    if len(rg) == 1 and lg.startswith(rg):
        return True
    return False


def edit_distance_at_most_one(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False

    i = 0
    j = 0
    edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(a) > len(b):
            i += 1
        elif len(b) > len(a):
            j += 1
        else:
            i += 1
            j += 1

    if i < len(a) or j < len(b):
        edits += 1
    return edits <= 1


def surname_compatible(list_surname: Set[str], row_surname: Set[str]) -> bool:
    if list_surname & row_surname:
        return True
    for ls in list_surname:
        for rs in row_surname:
            if edit_distance_at_most_one(ls, rs):
                return True
    return False


def match_faculty(row_surname: str, row_given: str, faculty_refs: List[FacultyRef]) -> Optional[FacultyRef]:
    row_s_tokens = set(tokens(row_surname))
    row_g_tokens = tokens(row_given)
    if not row_s_tokens or not row_g_tokens:
        return None

    candidates: List[FacultyRef] = []
    for f in faculty_refs:
        if not given_compatible(f.given_tokens, row_g_tokens):
            continue
        if not surname_compatible(f.surname_tokens, row_s_tokens):
            continue
        candidates.append(f)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Tie-break: exact surname token match on first or last token if possible.
    row_s_list = tokens(row_surname)
    row_last = row_s_list[-1] if row_s_list else ""
    row_first = row_s_list[0] if row_s_list else ""
    ranked: List[Tuple[int, FacultyRef]] = []
    for f in candidates:
        f_s_list = tokens(f.surname_raw)
        score = 0
        if f_s_list:
            if row_last == f_s_list[-1]:
                score += 2
            if row_first == f_s_list[0]:
                score += 1
        ranked.append((score, f))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if len(ranked) == 1 or ranked[0][0] > ranked[1][0]:
        return ranked[0][1]
    return None


def fetch(url: str) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def parse_salary_amount(raw: str) -> str:
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return ""
    try:
        return f"{float(cleaned):.2f}"
    except ValueError:
        return cleaned


def public_name_to_tokens(name: str) -> Tuple[Set[str], List[str]]:
    t = tokens(name)
    return set(t), t


def match_public_name(f: FacultyRef, public_names: List[str]) -> Tuple[str, str]:
    matches: List[str] = []
    for p in public_names:
        p_set, p_list = public_name_to_tokens(p)
        if not p_list:
            continue
        if not given_compatible(f.given_tokens, p_list):
            continue
        if not (f.surname_tokens & p_set):
            continue
        matches.append(p)

    if not matches:
        return ("0", "")
    if len(matches) == 1:
        return ("1", matches[0])
    return ("ambiguous", " | ".join(sorted(matches)))


def main() -> None:
    faculty_refs = [make_faculty_ref(name) for name in parse_swift_names(SPHS_LIST_PATH)]
    faculty_by_canonical = {f.canonical: f for f in faculty_refs}

    current_year = date.today().year
    years: List[int] = []
    salary_by_faculty_year: Dict[str, Dict[int, str]] = {f.canonical: {} for f in faculty_refs}

    # Include all currently expected disclosure years (typically current year - 1).
    for year in range(2011, current_year):
        html_doc = fetch(DISCLOSURE_BASE.format(year))
        if html_doc is None:
            continue
        years.append(year)

        for row_surname, row_given, row_salary in parse_disclosure_rows(html_doc):
            faculty = match_faculty(row_surname, row_given, faculty_refs)
            if faculty is None:
                continue
            salary_value = parse_salary_amount(row_salary)
            if salary_value:
                salary_by_faculty_year[faculty.canonical][year] = salary_value

    years = sorted(set(years))

    rows: List[Dict[str, str]] = []
    for canonical in sorted(faculty_by_canonical.keys()):
        values = salary_by_faculty_year[canonical]
        observed_years = sorted(values.keys())
        first_year = str(observed_years[0]) if observed_years else ""
        last_year = str(observed_years[-1]) if observed_years else ""
        year_count = str(len(observed_years))

        missing_internal = []
        if len(observed_years) >= 2:
            for y in range(observed_years[0], observed_years[-1] + 1):
                if y not in values:
                    missing_internal.append(str(y))

        out = {
            "faculty_name": canonical,
            "first_disclosure_year": first_year,
            "last_disclosure_year": last_year,
            "disclosure_year_count": year_count,
            "missing_internal_years": ";".join(missing_internal),
        }

        for y in years:
            out[str(y)] = values.get(y, "")
        rows.append(out)

    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["faculty_name", "first_disclosure_year", "last_disclosure_year", "disclosure_year_count", "missing_internal_years"] + [str(y) for y in years]
    with OUT_TABLE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "faculty_in_list": str(len(faculty_refs)),
        "disclosure_years_scraped": ";".join(str(y) for y in years),
        "faculty_with_any_disclosure": str(sum(1 for r in rows if r["disclosure_year_count"] != "0")),
        "faculty_with_no_disclosure": str(sum(1 for r in rows if r["disclosure_year_count"] == "0")),
        "faculty_with_internal_gaps": str(sum(1 for r in rows if r["missing_internal_years"])),
    }
    with OUT_SUMMARY.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value"])
        writer.writeheader()
        for k, v in summary.items():
            writer.writerow({"metric": k, "value": v})

    public_rows: List[Dict[str, str]] = []
    public_names: List[str] = []
    if PUBLIC_ROSTER_PATH.exists():
        with PUBLIC_ROSTER_PATH.open(encoding="utf-8") as f:
            public_rows = list(csv.DictReader(f))
            public_names = [row.get("faculty_name", "").strip() for row in public_rows if row.get("faculty_name")]

    public_map = {row.get("faculty_name", "").strip(): row for row in public_rows if row.get("faculty_name")}

    cross_rows: List[Dict[str, str]] = []
    for canonical in sorted(faculty_by_canonical.keys()):
        f = faculty_by_canonical[canonical]
        status, public_name = match_public_name(f, public_names)
        public_profile = public_map.get(public_name, {}).get("profile_url", "") if status == "1" else ""
        cross_rows.append(
            {
                "faculty_name": canonical,
                "public_match_status": status,
                "public_name": public_name,
                "public_profile_url": public_profile,
                "first_disclosure_year": next((r["first_disclosure_year"] for r in rows if r["faculty_name"] == canonical), ""),
                "last_disclosure_year": next((r["last_disclosure_year"] for r in rows if r["faculty_name"] == canonical), ""),
                "disclosure_year_count": next((r["disclosure_year_count"] for r in rows if r["faculty_name"] == canonical), ""),
                "missing_internal_years": next((r["missing_internal_years"] for r in rows if r["faculty_name"] == canonical), ""),
            }
        )

    with OUT_PUBLIC.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "faculty_name",
                "public_match_status",
                "public_name",
                "public_profile_url",
                "first_disclosure_year",
                "last_disclosure_year",
                "disclosure_year_count",
                "missing_internal_years",
            ],
        )
        writer.writeheader()
        writer.writerows(cross_rows)

    print(f"Wrote disclosure table: {OUT_TABLE}")
    print(f"Wrote disclosure summary: {OUT_SUMMARY}")
    print(f"Wrote public cross-check: {OUT_PUBLIC}")


if __name__ == "__main__":
    main()
