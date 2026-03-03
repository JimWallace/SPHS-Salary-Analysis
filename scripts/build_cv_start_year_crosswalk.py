#!/usr/bin/env python3
"""Extract likely UW start years from faculty CVs and compare to first disclosure year."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'pymupdf'. Install locally with: python3 -m pip install --user pymupdf"
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
SPHS_LIST_PATH = ROOT / "SalaryData" / "SPHS Faculty List.swift"
CV_DIRECTORY = ROOT / "Faculty CVs"
DISCLOSURE_TABLE = ROOT / "analysis_output" / "disclosure_completeness_table.csv"
OUT = ROOT / "analysis_output" / "cv_start_year_crosswalk.csv"

GIVEN_NAME_ALIASES = {
    "DAVID": {"DAVE"},
    "JAMES": {"JIM"},
    "CHRISTOPHER": {"CHRIS"},
    "GEOFFREY": {"GEOFF"},
    "PHILIP": {"PHIL"},
}

YEAR_RANGE_RE = re.compile(r"\b((?:19|20)\d{2})\s*[-–]\s*(?:((?:19|20)\d{2})|PRESENT|CURRENT)\b", re.I)
YEAR_SINGLE_RE = re.compile(r"\b((?:19|20)\d{2})\b")
UW_RE = re.compile(r"\bUniversity of Waterloo\b", re.I)
TITLE_RE = re.compile(r"\b(assistant professor|associate professor|professor|lecturer|postdoctoral|post-doc|chair|research professor)\b", re.I)
EMPLOYMENT_RE = re.compile(r"\b(employment history|employment|academic appointments|appointments)\b", re.I)


def canonical_tokens(text: str) -> List[str]:
    return re.findall(r"[A-Z]+", text.upper())


def parse_swift_names(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r'"([^"\n]+,\s*[^"\n]+)"', text)


def parse_filename_tokens(path: Path) -> List[str]:
    stem = path.stem.replace("_", " ")
    stem = re.sub(r"(?i)\bCV\b.*$", "", stem).strip(" ,-")
    return canonical_tokens(stem)


def edit_distance_leq_one(lhs: str, rhs: str) -> bool:
    if lhs == rhs:
        return True
    if abs(len(lhs) - len(rhs)) > 1:
        return False
    i = j = edits = 0
    while i < len(lhs) and j < len(rhs):
        if lhs[i] == rhs[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(lhs) == len(rhs):
            i += 1
            j += 1
        elif len(lhs) > len(rhs):
            i += 1
        else:
            j += 1
    if i < len(lhs) or j < len(rhs):
        edits += 1
    return edits <= 1


def given_name_candidates(primary_given: str) -> List[str]:
    if not primary_given:
        return []
    candidates = {primary_given}
    if primary_given in GIVEN_NAME_ALIASES:
        candidates |= GIVEN_NAME_ALIASES[primary_given]
    for formal, aliases in GIVEN_NAME_ALIASES.items():
        if primary_given in aliases:
            candidates.add(formal)
            candidates |= aliases
    return sorted(candidates)


def choose_cv_for_salary_name(salary_name: str, cv_entries: List[Tuple[Path, List[str]]]) -> Optional[Path]:
    surname_raw, given_raw = [part.strip() for part in salary_name.split(",", 1)]
    surname_tokens = canonical_tokens(surname_raw)
    given_tokens = canonical_tokens(given_raw)
    given_primary = given_tokens[0] if given_tokens else ""
    given_candidates = set(given_name_candidates(given_primary))
    if not given_candidates and given_primary:
        given_candidates = {given_primary}

    strong: List[Path] = []
    weak: List[Path] = []

    for path, tokens in cv_entries:
        token_set = set(tokens)
        surname_ok = bool(surname_tokens) and all(tok in token_set for tok in surname_tokens)
        given_ok = bool(given_candidates) and any(c in token_set for c in given_candidates)
        surname_last_ok = bool(surname_tokens) and surname_tokens[-1] in token_set
        surname_fuzzy_ok = len(surname_tokens) == 1 and any(edit_distance_leq_one(surname_tokens[0], c) for c in token_set)

        if surname_ok and given_ok:
            strong.append(path)
        elif (surname_last_ok or surname_fuzzy_ok) and given_ok:
            weak.append(path)

    if len(strong) == 1:
        return strong[0]
    if len(strong) > 1:
        return sorted(strong, key=lambda p: len(p.name))[0]
    if len(weak) == 1:
        return weak[0]
    if len(weak) > 1:
        return sorted(weak, key=lambda p: len(p.name))[0]
    return None


def extract_pdf_lines(pdf_path: Path) -> List[str]:
    doc = fitz.open(pdf_path)
    parts: List[str] = []
    for page in doc:
        parts.append(page.get_text())
    text = "\n".join(parts)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", text)
    lines = []
    for raw in text.splitlines():
        cleaned = re.sub(r"\s+", " ", raw).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def extract_cv_start_year(lines: List[str]) -> Tuple[Optional[int], str, str]:
    candidates: List[Tuple[int, int, str]] = []  # (year, score, snippet)

    for i, line in enumerate(lines):
        window = " ".join(lines[max(0, i - 2): min(len(lines), i + 3)])
        uw_match = UW_RE.search(window)
        if not uw_match:
            continue
        # Only consider years in the UW-specific suffix to avoid picking earlier,
        # unrelated years from other institutions in the same merged window.
        uw_suffix = window[uw_match.start():]

        score = 0
        if TITLE_RE.search(uw_suffix):
            score += 2
        if EMPLOYMENT_RE.search(" ".join(lines[max(0, i - 8): i + 1])):
            score += 2
        if "school of public health" in uw_suffix.lower():
            score += 1

        for m in YEAR_RANGE_RE.finditer(uw_suffix):
            year = int(m.group(1))
            if 1990 <= year <= 2030:
                candidates.append((year, score + 2, uw_suffix[:240]))

        if not YEAR_RANGE_RE.search(uw_suffix):
            for m in YEAR_SINGLE_RE.finditer(uw_suffix):
                year = int(m.group(1))
                if 1990 <= year <= 2030:
                    candidates.append((year, score, uw_suffix[:240]))

    if not candidates:
        return (None, "none", "No UW appointment-like year pattern found in CV text")

    # Prefer higher score, then earliest year among strong snippets.
    max_score = max(s for _, s, _ in candidates)
    strong = [c for c in candidates if c[1] == max_score]
    year, score, snippet = sorted(strong, key=lambda t: t[0])[0]

    if score >= 5:
        conf = "high"
    elif score >= 3:
        conf = "medium"
    else:
        conf = "low"

    note = f"Matched UW appointment context; score={score}; snippet={snippet}"
    return (year, conf, note)


def main() -> None:
    salary_names = parse_swift_names(SPHS_LIST_PATH)
    cv_files = sorted(CV_DIRECTORY.glob("*.pdf"))
    cv_entries = [(p, parse_filename_tokens(p)) for p in cv_files]

    first_disclosure: Dict[str, str] = {}
    if DISCLOSURE_TABLE.exists():
        with DISCLOSURE_TABLE.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                first_disclosure[r["faculty_name"]] = r.get("first_disclosure_year", "")

    rows: List[Dict[str, str]] = []
    for name in salary_names:
        cv_path = choose_cv_for_salary_name(name, cv_entries)
        if cv_path is None:
            rows.append(
                {
                    "salary_name": name,
                    "cv_file": "",
                    "cv_start_year": "",
                    "cv_start_confidence": "none",
                    "first_disclosure_year": first_disclosure.get(name, ""),
                    "disclosure_minus_cv_years": "",
                    "method_note": "No unique matching CV filename found",
                }
            )
            continue

        try:
            lines = extract_pdf_lines(cv_path)
            year, conf, note = extract_cv_start_year(lines)
        except Exception as exc:
            year, conf, note = None, "none", f"CV parse error: {type(exc).__name__}"

        first_disc = first_disclosure.get(name, "")
        gap = ""
        if year is not None and first_disc.isdigit():
            gap = str(int(first_disc) - year)

        rows.append(
            {
                "salary_name": name,
                "cv_file": cv_path.name,
                "cv_start_year": str(year) if year is not None else "",
                "cv_start_confidence": conf,
                "first_disclosure_year": first_disc,
                "disclosure_minus_cv_years": gap,
                "method_note": note,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "salary_name",
                "cv_file",
                "cv_start_year",
                "cv_start_confidence",
                "first_disclosure_year",
                "disclosure_minus_cv_years",
                "method_note",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    with_year = sum(1 for r in rows if r["cv_start_year"])
    high = sum(1 for r in rows if r["cv_start_confidence"] == "high")
    med = sum(1 for r in rows if r["cv_start_confidence"] == "medium")
    low = sum(1 for r in rows if r["cv_start_confidence"] == "low")
    print(f"Wrote CV start-year crosswalk: {OUT}")
    print(f"Coverage: {with_year}/{len(rows)} (high={high}, medium={med}, low={low})")


if __name__ == "__main__":
    main()
