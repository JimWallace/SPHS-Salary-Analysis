#!/usr/bin/env python3
"""
Build terminal degree domain classifications from local faculty CV files.

Input directory (private, not tracked): Faculty CVs/
Output (private, not tracked): data/private_terminal_degree_domain.csv
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'pymupdf'. Install locally with: python3 -m pip install --user pymupdf"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
SPHS_LIST_PATH = ROOT / "SalaryData" / "SPHS Faculty List.swift"
CV_DIRECTORY = ROOT / "Faculty CVs"
OUTPUT_PATH = ROOT / "data" / "private_terminal_degree_domain.csv"

DOCTORAL_PATTERN = re.compile(
    r"(?i)\b(ph\.?\s*d\.?|doctor of philosophy|doctor of|dphil|drph|scd|edd|md)\b"
)

HEALTH_DOMAIN_KEYWORDS = [
    "health",
    "public health",
    "medicine",
    "medical",
    "nursing",
    "epidemiology",
    "biostat",
    "kinesiology",
    "rehabilitation",
    "clinical",
    "health sciences",
    "nutrition",
    "toxicology",
    "pathology",
    "gerontology",
    "occupational therapy",
    "speech and hearing",
    "laboratory medicine",
    "population medicine",
]

NON_HEALTH_HINTS = [
    "statistics",
    "sociology",
    "psychology",
    "engineering",
    "information systems",
    "anthropology",
    "women",
    "neuroscience",
    "political",
    "geomatics",
    "social work",
    "computer science",
    "mathematics",
]

EDUCATION_HEADINGS = [
    "DEGREES RECEIVED",
    "DEGREES",
    "EDUCATION",
    "ACADEMIC BACKGROUND",
    "ACADEMIC CREDENTIALS",
    "QUALIFICATIONS",
]

GIVEN_NAME_ALIASES = {
    "DAVID": {"DAVE"},
    "JAMES": {"JIM"},
    "CHRISTOPHER": {"CHRIS"},
    "GEOFFREY": {"GEOFF"},
    "PHILIP": {"PHIL"},
}


def canonical_tokens(text: str) -> List[str]:
    return re.findall(r"[A-Z]+", text.upper())


def parse_sphs_salary_names(swift_text: str) -> List[str]:
    return re.findall(r'"([^"\n]+,\s*[^"\n]+)"', swift_text)


def parse_filename_name_tokens(path: Path) -> List[str]:
    stem = path.stem.replace("_", " ")
    stem = re.sub(r"(?i)\bCV\b.*$", "", stem).strip(" ,-")
    return canonical_tokens(stem)


def edit_distance_leq_one(lhs: str, rhs: str) -> bool:
    if lhs == rhs:
        return True
    if abs(len(lhs) - len(rhs)) > 1:
        return False

    # Two-pointer check for Levenshtein distance <= 1.
    i = 0
    j = 0
    edits = 0
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


def extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    pieces: List[str] = []
    for page in doc:
        pieces.append(page.get_text())
    text = "\n".join(pieces)
    # Remove control chars that break pattern matching in some PDFs.
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", text)
    return text


def normalize_lines(text: str) -> List[str]:
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def find_section_start(lines: List[str]) -> Optional[int]:
    for i, line in enumerate(lines):
        upper = line.upper()
        if any(heading in upper for heading in EDUCATION_HEADINGS):
            return i
    return None


def choose_terminal_snippet(lines: List[str]) -> Optional[str]:
    def find_candidate(candidates: Iterable[str]) -> Optional[str]:
        candidate_list = list(candidates)
        for idx, line in enumerate(candidate_list):
            if not DOCTORAL_PATTERN.search(line):
                continue
            parts = [line]
            for j in range(1, 3):
                if idx + j >= len(candidate_list):
                    break
                nxt = candidate_list[idx + j]
                if len(nxt) > 120:
                    break
                if re.search(r"(?i)^(employment|awards|publications|research|teaching|contact)", nxt):
                    break
                parts.append(nxt)
            snippet = " ".join(parts)
            snippet = re.sub(r"\s+", " ", snippet).strip()
            return snippet[:320]
        return None

    section_start = find_section_start(lines)
    if section_start is not None:
        section = lines[section_start : section_start + 140]
        snippet = find_candidate(section)
        if snippet:
            return snippet

    return find_candidate(lines)


def is_readable_terminal_line(text: str) -> bool:
    if not text:
        return False
    allowed_chars = " ,.;:()/-+&"
    weird_count = sum(1 for char in text if not (char.isalnum() or char.isspace() or char in allowed_chars))
    weird_ratio = weird_count / max(len(text), 1)
    word_count = len(re.findall(r"[A-Za-z]{3,}", text))
    return weird_ratio <= 0.20 and word_count >= 3


def classify_domain(terminal_line: Optional[str]) -> Tuple[str, str]:
    if not terminal_line:
        return "unknown", "No doctoral degree line detected in parsed CV text"
    if not is_readable_terminal_line(terminal_line):
        return "unknown", "Extracted doctoral line is not machine-readable enough to classify"

    lower = terminal_line.lower()
    if any(keyword in lower for keyword in HEALTH_DOMAIN_KEYWORDS):
        return "health", "Health-domain keyword detected in terminal degree line"

    if any(keyword in lower for keyword in NON_HEALTH_HINTS):
        return "non_health", "Non-health discipline keyword detected in terminal degree line"

    if DOCTORAL_PATTERN.search(terminal_line):
        return "unknown", "Doctoral degree found but domain is ambiguous from available CV text"

    return "unknown", "Unable to classify terminal degree domain"


def choose_cv_for_salary_name(
    salary_name: str, cv_entries: List[Tuple[Path, List[str]]]
) -> Optional[Path]:
    surname_raw, given_raw = [part.strip() for part in salary_name.split(",", 1)]
    surname_tokens = canonical_tokens(surname_raw)
    given_tokens = canonical_tokens(given_raw)
    given_primary = given_tokens[0] if given_tokens else ""
    given_candidates = set(given_name_candidates(given_primary))
    if not given_candidates and given_primary:
        given_candidates = {given_primary}

    strong_matches: List[Path] = []
    weak_matches: List[Path] = []

    for path, tokens in cv_entries:
        token_set = set(tokens)
        surname_ok = bool(surname_tokens) and all(tok in token_set for tok in surname_tokens)
        given_ok = bool(given_candidates) and any(candidate in token_set for candidate in given_candidates)

        # Fallback for compound surnames in salary list (e.g., TAIT NEUFELD).
        surname_last_ok = bool(surname_tokens) and surname_tokens[-1] in token_set
        surname_fuzzy_ok = (
            len(surname_tokens) == 1
            and any(edit_distance_leq_one(surname_tokens[0], candidate) for candidate in token_set)
        )

        if surname_ok and given_ok:
            strong_matches.append(path)
        elif (surname_last_ok or surname_fuzzy_ok) and given_ok:
            weak_matches.append(path)

    if len(strong_matches) == 1:
        return strong_matches[0]
    if len(strong_matches) > 1:
        return sorted(strong_matches, key=lambda p: len(p.name))[0]

    if len(weak_matches) == 1:
        return weak_matches[0]
    if len(weak_matches) > 1:
        return sorted(weak_matches, key=lambda p: len(p.name))[0]

    return None


def main() -> None:
    if not CV_DIRECTORY.exists():
        raise SystemExit(f"CV directory not found: {CV_DIRECTORY}")

    swift_text = SPHS_LIST_PATH.read_text(encoding="utf-8")
    salary_names = parse_sphs_salary_names(swift_text)

    cv_files = sorted(CV_DIRECTORY.glob("*.pdf"))
    cv_entries = [(path, parse_filename_name_tokens(path)) for path in cv_files]

    rows: List[Dict[str, str]] = []
    for salary_name in salary_names:
        cv_path = choose_cv_for_salary_name(salary_name, cv_entries)
        if cv_path is None:
            rows.append(
                {
                    "salary_name": salary_name,
                    "cv_file": "",
                    "terminal_degree_line": "",
                    "domain": "unknown",
                    "is_non_health_terminal": "",
                    "method_note": "No unique matching CV filename found",
                }
            )
            continue

        try:
            text = extract_pdf_text(cv_path)
            lines = normalize_lines(text)
            terminal_line = choose_terminal_snippet(lines)
            domain, note = classify_domain(terminal_line)
        except Exception as exc:
            terminal_line = None
            domain = "unknown"
            note = f"CV parse error: {type(exc).__name__}"

        is_non_health = "1" if domain == "non_health" else ("0" if domain == "health" else "")
        rows.append(
            {
                "salary_name": salary_name,
                "cv_file": cv_path.name,
                "terminal_degree_line": terminal_line or "",
                "domain": domain,
                "is_non_health_terminal": is_non_health,
                "method_note": note,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "salary_name",
                "cv_file",
                "terminal_degree_line",
                "domain",
                "is_non_health_terminal",
                "method_note",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    known = sum(1 for row in rows if row["is_non_health_terminal"] in {"0", "1"})
    non_health = sum(1 for row in rows if row["is_non_health_terminal"] == "1")
    health = sum(1 for row in rows if row["is_non_health_terminal"] == "0")
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    print(f"Known terminal-domain classifications: {known} (non-health={non_health}, health={health})")


if __name__ == "__main__":
    main()
