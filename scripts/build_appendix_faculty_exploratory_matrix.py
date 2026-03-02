#!/usr/bin/env python3
"""
Build one faculty-level exploratory matrix for report appendix.

Output:
- analysis_output/appendix_faculty_exploratory_matrix.csv
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SPHS_LIST_PATH = ROOT / "SalaryData" / "SPHS Faculty List.swift"
MHI_LIST_PATH = ROOT / "SalaryData" / "MHI Faculty List.swift"
TERMINAL_PATH = ROOT / "data" / "private_terminal_degree_domain.csv"
SELF_PATH = ROOT / "data" / "private_self_defined_factors.csv"
PUBLIC_ROSTER_PATH = ROOT / "data" / "public_sphs_scrape" / "faculty_roster_with_groups.csv"
OUTPUT_PATH = ROOT / "analysis_output" / "appendix_faculty_exploratory_matrix.csv"

PUBLIC_GROUP_COLUMNS = {
    "Researchers": "g_researchers",
    "Chronic disease prevention and management researcher": "g_cdpm",
    "Health policy and health systems researcher": "g_health_policy",
    "Health and aging researcher": "g_health_aging",
    "Health and environment researcher": "g_health_environment",
    "Food and water safety; security and governance researcher": "g_food_water",
    "Health informatics researcher": "g_hi",
    "Global health researcher": "g_global_health",
    "Health neuroscience and cognitive epidemiology researcher": "g_neuro_cog_epi",
    "Healthy workplaces researcher": "g_healthy_workplaces",
}

SELF_FACTOR_COLUMNS = [
    "health_services_policy",
    "mental_behavioral",
    "epidemiology_biostatistics",
    "aging_gerontology",
    "rehabilitation_disability",
    "substance_tobacco",
    "environmental_occupational",
    "nutrition_diet",
    "health_informatics_data",
    "global_population_health",
]


def parse_swift_names(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r'"([^"\n]+,\s*[^"\n]+)"', text)


def canonical_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip().upper())


def name_key_from_salary(name: str) -> Optional[Tuple[str, str]]:
    if "," not in name:
        return None
    surname, given = [part.strip() for part in name.split(",", 1)]
    s_tokens = re.findall(r"[A-Z]+", surname.upper())
    g_tokens = re.findall(r"[A-Z]+", given.upper())
    if not s_tokens or not g_tokens:
        return None
    return (g_tokens[0], s_tokens[-1])


def name_key_from_public(name: str) -> Optional[Tuple[str, str]]:
    tokens = re.findall(r"[A-Z]+", name.upper())
    if len(tokens) < 2:
        return None
    return (tokens[0], tokens[-1])


def reason_code(method_note: str) -> str:
    lower = method_note.lower()
    if "no unique matching cv" in lower:
        return "no-cv-match"
    if "no doctoral degree line" in lower:
        return "no-doctoral-line"
    if "not machine-readable" in lower:
        return "unreadable-text"
    if "ambiguous" in lower:
        return "ambiguous-domain"
    if "parse error" in lower:
        return "parse-error"
    if not method_note.strip():
        return ""
    return "other"


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_group_tag(tag: str) -> str:
    return tag.replace(",", ";")


def build_public_lookup(rows: List[Dict[str, str]]) -> Dict[Tuple[str, str], Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in rows:
        key = name_key_from_public(row.get("faculty_name", ""))
        if key is None:
            continue
        tags = [t.strip() for t in row.get("group_tags", "").split(";") if t.strip()]
        norm_tags = [normalize_group_tag(t) for t in tags]
        entry = {
            "public_name": row.get("faculty_name", ""),
            "public_profile_url": row.get("profile_url", ""),
            "public_cross_appointment": row.get("cross_appointment", "0") or "0",
            "public_group_count": row.get("group_count", "0") or "0",
            "public_group_tags": " | ".join(norm_tags),
            "public_listed": "1",
        }
        for group_label, col in PUBLIC_GROUP_COLUMNS.items():
            entry[col] = "1" if group_label in norm_tags else "0"
        out[key] = entry
    return out


def main() -> None:
    salary_names = parse_swift_names(SPHS_LIST_PATH)
    mhi_names = {canonical_name(name) for name in parse_swift_names(MHI_LIST_PATH)}

    terminal_rows = read_csv(TERMINAL_PATH)
    terminal_by_name = {canonical_name(r["salary_name"]): r for r in terminal_rows if r.get("salary_name")}

    self_rows = read_csv(SELF_PATH)
    self_by_name = {canonical_name(r["salary_name"]): r for r in self_rows if r.get("salary_name")}

    public_rows = read_csv(PUBLIC_ROSTER_PATH)
    public_by_key = build_public_lookup(public_rows)

    out_rows: List[Dict[str, str]] = []
    for salary_name in salary_names:
        canonical = canonical_name(salary_name)
        row: Dict[str, str] = {
            "faculty_name": salary_name.replace(",", " |"),
            "mhi": "1" if canonical in mhi_names else "0",
        }

        t = terminal_by_name.get(canonical, {})
        row["term_domain"] = t.get("domain", "").replace("_", "-")
        row["term_non_health"] = t.get("is_non_health_terminal", "")
        row["term_reason_code"] = reason_code(t.get("method_note", ""))

        s = self_by_name.get(canonical, {})
        row["self_parse_status"] = s.get("parse_status", "").replace("_", "-")
        row["self_text_quality"] = s.get("text_quality", "")
        for factor in SELF_FACTOR_COLUMNS:
            row[f"sf_{factor}"] = s.get(factor, "")

        default_public = {
            "public_name": "",
            "public_profile_url": "",
            "public_cross_appointment": "0",
            "public_group_count": "0",
            "public_group_tags": "",
            "public_listed": "0",
        }
        for _, col in PUBLIC_GROUP_COLUMNS.items():
            default_public[col] = "0"

        key = name_key_from_salary(salary_name)
        p = public_by_key.get(key, default_public) if key else default_public
        row.update(p)

        out_rows.append(row)

    fieldnames = [
        "faculty_name",
        "mhi",
        "term_domain",
        "term_non_health",
        "term_reason_code",
        "self_parse_status",
        "self_text_quality",
    ] + [f"sf_{factor}" for factor in SELF_FACTOR_COLUMNS] + [
        "public_listed",
        "public_cross_appointment",
        "public_group_count",
        "public_name",
        "public_profile_url",
        "public_group_tags",
        "g_researchers",
        "g_cdpm",
        "g_health_policy",
        "g_health_aging",
        "g_health_environment",
        "g_food_water",
        "g_hi",
        "g_global_health",
        "g_neuro_cog_epi",
        "g_healthy_workplaces",
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote appendix faculty exploratory matrix: {OUTPUT_PATH} ({len(out_rows)} rows)")


if __name__ == "__main__":
    main()
