#!/usr/bin/env python3
"""
Build exploratory self-defined expertise factors from local CV text.

Private output (person-level): data/private_self_defined_factors.csv
Public-safe aggregate table: analysis_output/exploratory_self_defined_factor_summary.csv
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
MHI_LIST_PATH = ROOT / "SalaryData" / "MHI Faculty List.swift"
CV_DIRECTORY = ROOT / "Faculty CVs"
PRIVATE_OUTPUT_PATH = ROOT / "data" / "private_self_defined_factors.csv"
SUMMARY_OUTPUT_PATH = ROOT / "analysis_output" / "exploratory_self_defined_factor_summary.csv"

GIVEN_NAME_ALIASES = {
    "DAVID": {"DAVE"},
    "JAMES": {"JIM"},
    "CHRISTOPHER": {"CHRIS"},
    "GEOFFREY": {"GEOFF"},
    "PHILIP": {"PHIL"},
}

RESEARCH_HEADING_PATTERN = re.compile(
    r"(?i)\b(research interests?|areas? of expertise|expertise|speciali[sz]ation|keywords?|research focus|research program)\b"
)
STOP_PATTERN = re.compile(
    r"(?i)\b(publications?|selected publications?|peer-?reviewed|grants?|funding|awards?|teaching|service|references)\b"
)

FACTOR_DEFINITIONS: List[Tuple[str, str, re.Pattern[str], str]] = [
    (
        "epidemiology_biostatistics",
        "Epidemiology / Biostatistics",
        re.compile(r"(?i)\b(epidemiolog(?:y|ical)|biostat(?:istics|istical)?|population health)\b"),
        "epidemiology, biostatistics, population health",
    ),
    (
        "health_informatics_data",
        "Health Informatics / Data",
        re.compile(r"(?i)\b(health informatics|informatics|digital health|data science|machine learning|artificial intelligence|information systems?)\b"),
        "informatics, digital health, data science, ML/AI",
    ),
    (
        "health_services_policy",
        "Health Services / Policy",
        re.compile(r"(?i)\b(health services?|health policy|policy|implementation science|health systems?|program evaluation|knowledge translation)\b"),
        "health services, policy, implementation, evaluation",
    ),
    (
        "global_population_health",
        "Global / International Health",
        re.compile(r"(?i)\b(global health|international health|international development|low- and middle-income|lmic|one health)\b"),
        "global/international health and development",
    ),
    (
        "mental_behavioral",
        "Mental / Behavioral Health",
        re.compile(r"(?i)\b(psycholog(?:y|ical)|behavior(?:al|al)?|mental health|cognitive)\b"),
        "psychology, behavior, mental health",
    ),
    (
        "aging_gerontology",
        "Aging / Gerontology",
        re.compile(r"(?i)\b(aging|ageing|gerontology|older adults?|dementia)\b"),
        "aging, gerontology, dementia",
    ),
    (
        "substance_tobacco",
        "Substance Use / Tobacco",
        re.compile(r"(?i)\b(tobacco|nicotine|vaping|substance use|addiction|opioid|alcohol)\b"),
        "tobacco, vaping, addiction, substance use",
    ),
    (
        "environmental_occupational",
        "Environmental / Occupational Health",
        re.compile(r"(?i)\b(environmental health|occupational health|toxicolog(?:y|ical)|exposure|workplace)\b"),
        "environmental and occupational health",
    ),
    (
        "rehabilitation_disability",
        "Rehabilitation / Disability",
        re.compile(r"(?i)\b(rehabilitation|disabilit(?:y|ies)|assistive|occupational therapy|physical therapy|kinesiology)\b"),
        "rehabilitation, disability, therapy",
    ),
    (
        "nutrition_diet",
        "Nutrition / Diet",
        re.compile(r"(?i)\b(nutrition|diet(?:ary)?|food insecurity|nutritional)\b"),
        "nutrition and diet",
    ),
]


def canonical_tokens(text: str) -> List[str]:
    return re.findall(r"[A-Z]+", text.upper())


def canonical_name(text: str) -> str:
    trimmed = text.strip().upper()
    return re.sub(r"\s+", " ", trimmed)


def parse_swift_name_list(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r'"([^"\n]+,\s*[^"\n]+)"', text)


def parse_filename_name_tokens(path: Path) -> List[str]:
    stem = path.stem.replace("_", " ")
    stem = re.sub(r"(?i)\bCV\b.*$", "", stem).strip(" ,-")
    return canonical_tokens(stem)


def edit_distance_leq_one(lhs: str, rhs: str) -> bool:
    if lhs == rhs:
        return True
    if abs(len(lhs) - len(rhs)) > 1:
        return False

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


def extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    pieces: List[str] = []
    for page in doc:
        pieces.append(page.get_text())
    text = "\n".join(pieces)
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", text)


def normalize_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw in text.splitlines():
        cleaned = re.sub(r"\s+", " ", raw).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def build_research_context(lines: List[str]) -> str:
    prefix: List[str] = []
    for line in lines[:400]:
        if STOP_PATTERN.search(line):
            break
        prefix.append(line)

    contextual_lines: List[str] = []
    carry = 0
    for line in prefix:
        if RESEARCH_HEADING_PATTERN.search(line):
            contextual_lines.append(line)
            carry = 22
            continue
        if carry > 0:
            contextual_lines.append(line)
            carry -= 1

    selected = contextual_lines if len(contextual_lines) >= 20 else prefix[:220]
    return "\n".join(selected)


def text_quality_score(text: str) -> float:
    if not text:
        return 0.0
    weird = sum(1 for c in text if not (c.isalnum() or c.isspace() or c in " ,.;:()/-+&"))
    return 1.0 - (weird / max(len(text), 1))


def factor_flags(context_text: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key, _label, pattern, _hint in FACTOR_DEFINITIONS:
        out[key] = 1 if pattern.search(context_text) else 0
    return out


def write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not CV_DIRECTORY.exists():
        raise SystemExit(f"CV directory not found: {CV_DIRECTORY}")

    salary_names = parse_swift_name_list(SPHS_LIST_PATH)
    mhi_names = {canonical_name(name) for name in parse_swift_name_list(MHI_LIST_PATH)}

    cv_files = sorted(CV_DIRECTORY.glob("*.pdf"))
    cv_entries = [(path, parse_filename_name_tokens(path)) for path in cv_files]

    person_rows: List[Dict[str, str]] = []
    for salary_name in salary_names:
        cv_path = choose_cv_for_salary_name(salary_name, cv_entries)
        is_mhi = "1" if canonical_name(salary_name) in mhi_names else "0"

        if cv_path is None:
            row = {
                "salary_name": salary_name,
                "is_mhi": is_mhi,
                "cv_file": "",
                "parse_status": "no_cv_match",
                "text_quality": "0.000",
            }
            for key, _label, _pattern, _hint in FACTOR_DEFINITIONS:
                row[key] = ""
            person_rows.append(row)
            continue

        try:
            text = extract_pdf_text(cv_path)
            lines = normalize_lines(text)
            context = build_research_context(lines)
            quality = text_quality_score(context)
            flags = factor_flags(context)
            parse_status = "ok" if quality >= 0.70 else "low_quality_text"
        except Exception as exc:
            quality = 0.0
            flags = {key: 0 for key, _label, _pattern, _hint in FACTOR_DEFINITIONS}
            parse_status = f"parse_error_{type(exc).__name__}"

        row = {
            "salary_name": salary_name,
            "is_mhi": is_mhi,
            "cv_file": cv_path.name,
            "parse_status": parse_status,
            "text_quality": f"{quality:.3f}",
        }
        for key in flags:
            row[key] = str(flags[key])
        person_rows.append(row)

    private_fieldnames = [
        "salary_name",
        "is_mhi",
        "cv_file",
        "parse_status",
        "text_quality",
    ] + [key for key, _label, _pattern, _hint in FACTOR_DEFINITIONS]
    write_csv(PRIVATE_OUTPUT_PATH, private_fieldnames, person_rows)

    total_faculty = len(person_rows)
    matched_rows = [r for r in person_rows if r["cv_file"]]
    parsed_rows = [r for r in matched_rows if r["parse_status"] == "ok"]

    summary_rows: List[Dict[str, str]] = []
    for key, label, _pattern, hint in FACTOR_DEFINITIONS:
        hits_all = [r for r in parsed_rows if r.get(key) == "1"]
        hits_mhi = [r for r in hits_all if r["is_mhi"] == "1"]
        hits_non_mhi = [r for r in hits_all if r["is_mhi"] == "0"]

        main_effect_candidate = "yes" if len(hits_all) >= 5 else "no"
        interaction_candidate = "yes" if (len(hits_all) >= 8 and len(hits_mhi) >= 2 and len(hits_non_mhi) >= 2) else "no"
        if main_effect_candidate == "no":
            note = "Too sparse overall."
        elif interaction_candidate == "no":
            note = "Reasonable as control; weak for MHI interaction."
        else:
            note = "Usable for control and interaction exploration."

        summary_rows.append(
            {
                "factor_key": key,
                "factor_label": label,
                "matched_faculty": str(len(hits_all)),
                "matched_mhi": str(len(hits_mhi)),
                "matched_non_mhi": str(len(hits_non_mhi)),
                "coverage_total_pct": f"{(100.0 * len(hits_all) / max(total_faculty, 1)):.1f}",
                "coverage_parsed_pct": f"{(100.0 * len(hits_all) / max(len(parsed_rows), 1)):.1f}",
                "main_effect_candidate": main_effect_candidate,
                "mhi_interaction_candidate": interaction_candidate,
                "recommendation_note": note,
                "keyword_hint": hint,
            }
        )

    summary_rows.sort(key=lambda r: int(r["matched_faculty"]), reverse=True)

    summary_fieldnames = [
        "factor_key",
        "factor_label",
        "matched_faculty",
        "matched_mhi",
        "matched_non_mhi",
        "coverage_total_pct",
        "coverage_parsed_pct",
        "main_effect_candidate",
        "mhi_interaction_candidate",
        "recommendation_note",
        "keyword_hint",
    ]
    write_csv(SUMMARY_OUTPUT_PATH, summary_fieldnames, summary_rows)

    print(f"Wrote person-level factors: {PRIVATE_OUTPUT_PATH}")
    print(f"Wrote exploratory factor summary: {SUMMARY_OUTPUT_PATH}")
    print(
        "Coverage stats: "
        f"total_faculty={total_faculty}, cv_matched={len(matched_rows)}, parsed_ok={len(parsed_rows)}"
    )


if __name__ == "__main__":
    main()
