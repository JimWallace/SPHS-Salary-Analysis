#!/usr/bin/env python3
"""Create a one-row-per-faculty crosswalk to local CV files."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
SPHS_LIST_PATH = ROOT / "SalaryData" / "SPHS Faculty List.swift"
CV_DIR = ROOT / "Faculty CVs"
OUT = ROOT / "analysis_output" / "faculty_cv_crosswalk.csv"

GIVEN_ALIASES = {
    "DAVID": {"DAVID", "DAVE"},
    "JAMES": {"JAMES", "JIM"},
    "GEOFFREY": {"GEOFFREY", "GEOFF"},
    "CHRISTOPHER": {"CHRISTOPHER", "CHRIS"},
    "JOSE": {"JOSE", "JOSEPH"},
}

SURNAME_EQUIVALENTS = {
    "BIELOW": {"BIELOW", "BIGELOW"},
    "BIGELOW": {"BIELOW", "BIGELOW"},
}


def parse_swift_names(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r'"([^"\n]+,\s*[^"\n]+)"', text)


def tokens(text: str) -> List[str]:
    return re.findall(r"[A-Z]+", text.upper())


def given_token_compatible(canonical_primary: str, observed_token: str) -> bool:
    if not canonical_primary or not observed_token:
        return False
    c = canonical_primary
    o = observed_token
    if c == o:
        return True
    if len(c) == 1 and o.startswith(c):
        return True
    if len(o) == 1 and c.startswith(o):
        return True
    alias_group = GIVEN_ALIASES.get(c, {c})
    if o in alias_group:
        return True
    return False


def faculty_parts(name: str) -> Tuple[str, str, Set[str], List[str]]:
    surname, given = [p.strip() for p in name.split(",", 1)]
    s_tokens = set(tokens(surname))
    g_tokens = tokens(given)
    return surname, given, s_tokens, g_tokens


def cv_name_from_filename(path: Path) -> str:
    stem = path.stem
    # Remove common suffix tokens used in this folder naming convention.
    stem = re.sub(r"\bCV\b.*$", "", stem, flags=re.IGNORECASE).strip(" _,-")
    stem = stem.replace("_", " ")
    return stem


def match_cv_for_faculty(faculty_name: str, cv_files: List[Path]) -> Tuple[str, str, str]:
    _, _, s_tokens, g_tokens = faculty_parts(faculty_name)
    if not g_tokens:
        return ("missing", "", "")
    primary_given = g_tokens[0]
    expanded_surname_tokens = set(s_tokens)
    for token in list(s_tokens):
        expanded_surname_tokens |= SURNAME_EQUIVALENTS.get(token, {token})

    candidates: List[Tuple[int, Path]] = []

    for cv in cv_files:
        cv_name = cv_name_from_filename(cv)
        cv_tokens = tokens(cv_name)
        if len(cv_tokens) < 2:
            continue
        cv_set = set(cv_tokens)

        # Given-name compatibility and surname overlap.
        given_ok = any(given_token_compatible(primary_given, t) for t in cv_tokens)
        if not given_ok:
            continue
        if expanded_surname_tokens.isdisjoint(cv_set):
            continue

        # Score exact last-token surname + first-token surname to break ties.
        score = 0
        s_list = list(s_tokens)
        if cv_tokens[-1] in s_tokens:
            score += 2
        if cv_tokens[0] in s_tokens:
            score += 1
        # Prefer filenames that explicitly include comma format or more tokens.
        if "," in cv.name:
            score += 1
        score += min(len(cv_tokens), 5)
        candidates.append((score, cv))

    if not candidates:
        return ("missing", "", "")

    candidates.sort(key=lambda t: t[0], reverse=True)
    best_score = candidates[0][0]
    best = [c for c in candidates if c[0] == best_score]

    if len(best) > 1:
        names = " | ".join(sorted(c[1].name for c in best))
        return ("ambiguous", names, "")

    chosen = best[0][1]
    return ("matched", chosen.name, str(chosen.resolve()))


def main() -> None:
    faculty_names = sorted(parse_swift_names(SPHS_LIST_PATH))
    cv_files = sorted(CV_DIR.glob("*.pdf"))

    rows: List[Dict[str, str]] = []
    for faculty in faculty_names:
        status, filename, path = match_cv_for_faculty(faculty, cv_files)
        rows.append(
            {
                "faculty_name": faculty,
                "cv_match_status": status,
                "cv_filename": filename,
                "cv_path": path,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["faculty_name", "cv_match_status", "cv_filename", "cv_path"])
        writer.writeheader()
        writer.writerows(rows)

    matched = sum(1 for r in rows if r["cv_match_status"] == "matched")
    missing = sum(1 for r in rows if r["cv_match_status"] == "missing")
    ambiguous = sum(1 for r in rows if r["cv_match_status"] == "ambiguous")
    print(f"Wrote CV crosswalk: {OUT}")
    print(f"Matched={matched} Missing={missing} Ambiguous={ambiguous}")


if __name__ == "__main__":
    main()
