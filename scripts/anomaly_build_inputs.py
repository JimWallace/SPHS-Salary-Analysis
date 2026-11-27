#!/usr/bin/env python3
"""Build the one-row-per-person input table for the salary anomaly screen.

Usage:
  python3 scripts/anomaly_build_inputs.py

Inputs:
- data/private/anomaly_targets.csv          (anomaly_targets.py)
- data/private/anomaly_collect/batch_*.json (public-source collection; docs/anomaly_collection_protocol.md)
- data/private/anomaly_subject.json         (the subject's own row, self-reported)
- data/private/anomaly_overrides.csv        (optional manual corrections: person_id, field, value, note)
- data/private/health_roster.csv            (for coverage)
- archived salary disclosures (data/raw/manifest.csv)

Outputs:
- data/private/anomaly_inputs.csv       (gitignored, names) one row per person
- data/private/verification_log.csv     (gitignored, names) one row per person and collected field
- analysis_output/anomaly_input_summary.md  (no names) sample counts, coverage, missingness, flags
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

import anomaly_common as ac
import promotion_cohort as pc

TARGETS = ac.PRIVATE / "anomaly_targets.csv"
COLLECT_DIR = ac.PRIVATE / "anomaly_collect"
SUBJECT = ac.PRIVATE / "anomaly_subject.json"
OVERRIDES = ac.PRIVATE / "anomaly_overrides.csv"
ROSTER = ac.PRIVATE / "health_roster.csv"
OUT = ac.PRIVATE / "anomaly_inputs.csv"
OUT_LOG = ac.PRIVATE / "verification_log.csv"
OUT_SUMMARY = ac.OUT_DIR / "anomaly_input_summary.md"

SUBJECT_BASE_2025 = pc.VALIDATION[2025]["subject_annualized_base"]
REFERENCE_YEAR = 2025

# Scale (across-the-board) increases, faculty salary scale, from the 2024-2027 arbitration award as
# reported by the Provost: https://uwaterloo.ca/provost/news/faculty-salary-settlement-agreement
# ("2024-25: 4.7% ...", "2025-26: 3.6% ..."), retrieved 2026-11-27. Calendar-year pay blends four
# months at the old scale and eight at the new one, so scale-only growth from calendar 2024 to 2025 is
# (1/3 * 1.047 + 2/3 * 1.047 * 1.036) / (1/3 + 2/3 * 1.047).
SCALE_2024, SCALE_2025 = 0.047, 0.036
EXPECTED_SCALE_GROWTH_2025 = ((1 / 3) * (1 + SCALE_2024) + (2 / 3) * (1 + SCALE_2024) * (1 + SCALE_2025)) / (
    (1 / 3) + (2 / 3) * (1 + SCALE_2024))

# Working Group academic groups (Appendix, "Academic Groups"). Health is the reference.
GROUP_BY_UNIT = [
    (r"accounting|\bsaf\b", "SAF"),
    (r"economics", "Econ"),
    (r"computer science|cheriton", "CSCS"),
    (r"optometry", "SOVS"),
    (r"pharmacy", "Pharmacy"),
]
GROUP_BY_FACULTY = [
    (r"\bhealth\b|kinesiology|public health|recreation and leisure", "Health"),
    (r"\barts\b|psychology|history|english|philosophy|sociology|political science|anthropology|fine arts|"
     r"communication arts|classical|french|germanic|religious|sexuality|social development|stratford|"
     r"global business", "Arts"),
    (r"engineering|architecture|systems design|management science|chemical|civil|electrical|mechanical", "Eng"),
    (r"environment|geography|planning|\bseed\b|enterprise and development", "Env"),
    (r"math|statistics|actuarial|combinatorics|optimization|applied mathematics|pure mathematics", "Math"),
    (r"science|chemistry|physics|astronomy|biology|earth|environmental sciences", "Sci"),
]

DEGREES = {"doctoral": "Doctoral", "masters": "Masters", "bachelor": "Bachelor", "professional": "Professional",
           "graduate license": "Graduate License"}
RANK_SHORT = {"assistant professor": "Assistant", "associate professor": "Associate", "professor": "Professor",
              "lecturer": "Lecturer"}
ADMIN_ROLE = re.compile(r"\b(?:Dean|Chair|Director|Vice-President|Provost|President|Principal|Head)\b", re.I)
SENIOR_ADMIN_TITLE = re.compile(r"^(?:President|Vice-President|Provost|Dean)\b|, Dean\b|^Dean,", re.I)

FIELDS = [
    "person_id", "is_subject", "name_key", "in_health", "in_pool", "pool_year",
    "unit", "faculty", "academic_group", "academic_group_source",
    "current_rank", "current_title_2025", "rank_at_hire", "rank_at_hire_source",
    "hire_year", "hire_year_source", "first_disclosure_year",
    "highest_degree", "degree_year", "lag", "years_since_hire",
    "salary_2023", "salary_2024", "salary_2025", "salary_2025_paid", "salary_max_2024_2025",
    "admin_flag", "admin_detail", "senior_admin_title", "leave_flag", "leave_detail",
    "exclude_reason",
    "src_highest_degree", "src_degree_year", "src_hire_year", "src_rank_at_hire", "src_unit",
    "retrieved", "confidence_min", "checks", "manual_verification",
]


def load_collected() -> dict[str, dict]:
    out = {}
    for path in sorted(COLLECT_DIR.glob("batch_*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            out[row["person_id"]] = row
    return out


def load_overrides() -> dict[tuple[str, str], tuple[str, str]]:
    if not OVERRIDES.exists():
        return {}
    with OVERRIDES.open(encoding="utf-8") as f:
        return {(r["person_id"], r["field"]): (r["value"], r.get("note", "")) for r in csv.DictReader(f)}


def as_int(v) -> int | None:
    try:
        return int(str(v).strip()[:4]) if v not in (None, "", "null") else None
    except ValueError:
        return None


def norm_degree(v) -> str:
    return DEGREES.get(str(v or "").strip().lower(), "")


def norm_rank(v) -> str:
    s = str(v or "").strip().lower()
    if "teaching stream" in s or s.startswith("lecturer") or "lecturer" in s:
        return "Lecturer"
    for k in ("assistant professor", "associate professor", "professor"):
        if s.startswith(k):
            return RANK_SHORT[k]
    return ""


def rank_from_title(title: str) -> str:
    """Working Group rank category implied by a disclosed title ('' if not a rank)."""
    cls = pc.classify_title(title)
    if title.strip().startswith("Lecturer"):
        return "Lecturer"
    if cls.rank in ("Assistant", "Associate", "Professor"):
        return "Lecturer" if cls.stream == "teaching" else cls.rank
    return ""


def academic_group(unit_text: str, in_health: bool) -> tuple[str, str]:
    if in_health:
        return "Health", "Health listing"
    t = unit_text.lower()
    for pattern, group in GROUP_BY_UNIT:
        if re.search(pattern, t):
            return group, "collected home unit"
    m = re.search(r"\(([^)]+)\)", t)
    faculty_text = m.group(1) if m else t
    for text in (faculty_text, t):
        for pattern, group in GROUP_BY_FACULTY:
            if re.search(pattern, text):
                return group, "collected home unit"
    return "", "unknown"


def sources_for(rec: dict, field: str) -> list[dict]:
    return [s for s in rec.get("sources", []) if s.get("field") == field]


def main() -> None:
    with TARGETS.open(encoding="utf-8") as f:
        targets = list(csv.DictReader(f))
    collected = load_collected()
    subject_rec = json.loads(SUBJECT.read_text(encoding="utf-8"))
    overrides = load_overrides()
    by_name = {(r.surname, r.given): r for r in ac.year_records(2025)}

    rows, log = [], []
    for t in targets:
        pid = t["person_id"]
        is_subject = t["is_subject"] == "1"
        rec = subject_rec if is_subject else collected.get(pid, {})
        method = "self-report" if is_subject else ("public-source collection" if rec else "not collected")
        r2025 = by_name[(t["disc_surname"], t["disc_given"])]
        hist = ac.history(r2025)
        sal = {y: hist[y].paid if y in hist else None for y in (2023, 2024, 2025)}
        first_year = int(t["first_disclosure_year"])

        def val(field: str, raw):
            if (pid, field) in overrides:
                return overrides[(pid, field)][0], "manual override: " + overrides[(pid, field)][1]
            return raw, ""

        degree, deg_note = val("highest_degree", norm_degree(rec.get("highest_degree")))
        degree_year, dy_note = val("degree_year", as_int(rec.get("degree_year")))
        hire_year, hy_note = val("hire_year", as_int(rec.get("hire_year_uw")))
        rank_hire, rh_note = val("rank_at_hire", norm_rank(rec.get("rank_at_hire")))
        degree_year, hire_year = as_int(degree_year), as_int(hire_year)
        checks = []

        hire_src = "collected" if hire_year else ""
        if hire_year is None:
            hire_year, hire_src = first_year, "first disclosure (fallback; likely later than actual hire)"
        rank_src = "collected" if rank_hire else ""
        if not rank_hire:
            # Only with a collected hire year: a fallback hire year is the first disclosure year itself.
            if hire_src == "collected" and first_year - hire_year <= 1:
                rank_hire = rank_from_title(hist[first_year].title)
                rank_src = "first disclosure title (within 1 year of hire)" if rank_hire else ""
            if not rank_hire:
                rank_hire, rank_src = "", "unknown"
        if hy_note:
            hire_src = hy_note
        if rh_note:
            rank_src = rh_note

        if hire_year and hire_year > first_year:
            checks.append(f"hire year {hire_year} after first disclosure {first_year}")
        if degree_year and hire_year and degree_year > hire_year:
            checks.append("degree after hire (negative lag)")
        if rank_src == "collected" and first_year - hire_year <= 1:
            disc_rank = rank_from_title(hist[first_year].title)
            if disc_rank and disc_rank != rank_hire:
                checks.append(f"rank at hire {rank_hire} vs first disclosed title {disc_rank}")

        current_rank = rank_from_title(r2025.title) or norm_rank(t["listed_position"])
        unit_text = rec.get("home_unit") or ""
        group, group_src = academic_group(unit_text, t["in_health"] == "1")

        roles = [f"{a.get('role', '')} ({a.get('years', '')})" for a in rec.get("admin_roles", []) or []]
        title_admin = [h.title for y, h in hist.items() if y in (2024, 2025) and "admin" in h.cls.flags]
        listed_admin = t["listed_position"] if ADMIN_ROLE.search(t["listed_position"].split(",", 1)[-1]
                                                                  if ";" not in t["listed_position"]
                                                                  else t["listed_position"].split(";", 1)[1]) else ""
        admin_detail = "; ".join(filter(None, ["roles: " + ", ".join(roles) if roles else "",
                                               "disclosed title: " + " | ".join(title_admin) if title_admin else "",
                                               "listed: " + listed_admin if listed_admin else ""]))
        senior = bool(SENIOR_ADMIN_TITLE.search(r2025.title)) and not current_rank_from_title_only(r2025.title)

        salary_2025 = SUBJECT_BASE_2025 if is_subject else sal[2025]
        leave_detail = []
        if not is_subject and sal[2024] and sal[2025] < sal[2024] * EXPECTED_SCALE_GROWTH_2025:
            leave_detail.append(f"2025 below scale-only growth over 2024 ({sal[2025] / sal[2024] - 1:+.1%})")
        if not is_subject and sal[2023] and sal[2024] and sal[2024] < sal[2023]:
            leave_detail.append(f"2024 below 2023 ({sal[2024] / sal[2023] - 1:+.1%})")
        if rec.get("left_or_leave_note") and not is_subject:
            leave_detail.append("public note: " + rec["left_or_leave_note"])
        if is_subject:
            leave_detail.append("subject: annualized base used (2025 paid figure includes sabbatical)")

        exclude = []
        if hire_year and hire_year >= REFERENCE_YEAR:
            exclude.append("hired 2025 or later")
        if senior:
            exclude.append("senior administrator (disclosed title administrative only)")

        conf = rec.get("confidence", {}) or {}
        conf_levels = [conf.get(k) for k in ("highest_degree", "degree_year", "hire_year_uw", "rank_at_hire")]
        order = {"low": 0, "medium": 1, "high": 2}
        known = [c for c in conf_levels if c in order]
        confidence_min = min(known, key=order.get) if known else ""

        def src(field: str) -> str:
            return " | ".join(s.get("url", "") for s in sources_for(rec, field))

        retrieved = sorted({s.get("retrieved", "") for s in rec.get("sources", []) if s.get("retrieved")})
        lag = hire_year - degree_year if (hire_year and degree_year) else None
        row = {
            "person_id": pid, "is_subject": t["is_subject"],
            "name_key": f"{r2025.key[0]}|{r2025.key[1]}",
            "in_health": t["in_health"], "in_pool": t["in_pool"], "pool_year": t["pool_year"],
            "unit": t["unit"] or unit_text, "faculty": "Health" if t["in_health"] == "1" else unit_text,
            "academic_group": group, "academic_group_source": group_src,
            "current_rank": current_rank, "current_title_2025": r2025.title,
            "rank_at_hire": rank_hire, "rank_at_hire_source": rank_src,
            "hire_year": hire_year or "", "hire_year_source": hire_src, "first_disclosure_year": first_year,
            "highest_degree": degree, "degree_year": degree_year or "", "lag": "" if lag is None else lag,
            "years_since_hire": REFERENCE_YEAR - hire_year if hire_year else "",
            "salary_2023": sal[2023] or "", "salary_2024": sal[2024] or "",
            "salary_2025": f"{salary_2025:.2f}", "salary_2025_paid": sal[2025],
            "salary_max_2024_2025": f"{max(salary_2025, sal[2024] or 0):.2f}",
            "admin_flag": int(bool(admin_detail)), "admin_detail": admin_detail,
            "senior_admin_title": int(senior),
            "leave_flag": int(any(not d.startswith("subject") for d in leave_detail)),
            "leave_detail": "; ".join(leave_detail),
            "exclude_reason": "; ".join(exclude),
            "src_highest_degree": src("highest_degree"), "src_degree_year": src("degree_year"),
            "src_hire_year": src("hire_year_uw"), "src_rank_at_hire": src("rank_at_hire"),
            "src_unit": src("home_unit"), "retrieved": ";".join(retrieved),
            "confidence_min": confidence_min, "checks": "; ".join(checks), "manual_verification": "",
        }
        rows.append(row)

        for field, value, note in (("highest_degree", degree, deg_note), ("degree_year", degree_year, dy_note),
                                   ("hire_year_uw", hire_year if hire_src == "collected" else None, hy_note),
                                   ("rank_at_hire", rank_hire if rank_src == "collected" else None, rh_note),
                                   ("home_unit", unit_text, "")):
            srcs = sources_for(rec, field) or [{}]
            for s in srcs:
                log.append({
                    "person_id": pid, "field": field, "value": "" if value is None else value,
                    "method": note or method, "source_url": s.get("url", ""), "retrieved": s.get("retrieved", ""),
                    "quote": s.get("quote", ""), "confidence": conf.get(field, "") if field != "home_unit" else "",
                    "automated_checks": row["checks"], "manual_verification": "",
                })
        if hire_src.startswith("first disclosure"):
            log.append({"person_id": pid, "field": "hire_year_uw", "value": hire_year,
                        "method": "fallback: first salary disclosure year", "source_url": "data/raw/manifest.csv",
                        "retrieved": "", "quote": "", "confidence": "low", "automated_checks": row["checks"],
                        "manual_verification": ""})

    pc.write_csv(OUT, rows, FIELDS)
    pc.write_csv(OUT_LOG, log, list(log[0].keys()))
    write_summary(rows)
    print(f"Wrote {OUT.relative_to(ac.ROOT)} ({len(rows)} rows), {OUT_LOG.relative_to(ac.ROOT)} ({len(log)} rows), "
          f"{OUT_SUMMARY.relative_to(ac.ROOT)}")


def current_rank_from_title_only(title: str) -> bool:
    """True if the disclosed title names a faculty rank (so the person is a ranked faculty member
    whose title also carries an administrative role)."""
    return bool(rank_from_title(title))


def write_summary(rows: list[dict]) -> None:
    with ROSTER.open(encoding="utf-8") as f:
        roster = list(csv.DictReader(f))
    required = ["current_rank", "rank_at_hire", "hire_year", "highest_degree", "degree_year", "lag",
                "salary_2024", "salary_2025"]
    out = [
        "# Anomaly screen: input table summary (no names)",
        "",
        "Generated by `scripts/anomaly_build_inputs.py`. Counts only; the person-level table is in",
        "`data/private/` and is not published.",
        "",
        f"Scale-only growth used for the leave flag (calendar 2024 to 2025): {EXPECTED_SCALE_GROWTH_2025 - 1:.2%}.",
        "",
        "## Coverage of the Faculty of Health listings by the 2025 disclosure",
        "",
        "| Unit | Listed regular faculty | Matched to 2025 disclosure | Coverage |",
        "|---|---|---|---|",
    ]
    for unit in ("SPHS", "KHS", "RLS"):
        sub = [r for r in roster if r["unit"] == unit]
        m = sum(r["match_2025"] == "unique" for r in sub)
        out.append(f"| {unit} | {len(sub)} | {m} | {m / len(sub):.0%} |")
    m = sum(r["match_2025"] == "unique" for r in roster)
    out.append(f"| Total | {len(roster)} | {m} | {m / len(roster):.0%} |")

    for label, key in (("Stage 1: Faculty of Health", "in_health"), ("Stage 2: promotion pool", "in_pool")):
        sub = [r for r in rows if r[key] == "1"]
        out += ["", f"## {label} (n = {len(sub)}, including the subject)", "",
                "| Variable | Present | Missing | Source: collected | Source: fallback/derived |", "|---|---|---|---|---|"]
        for v in required:
            present = sum(str(r[v]) != "" for r in sub)
            src_field = {"hire_year": "hire_year_source", "rank_at_hire": "rank_at_hire_source"}.get(v)
            if src_field:
                coll = sum(r[src_field] == "collected" for r in sub)
                fb = sum(r[src_field] not in ("collected", "unknown", "") for r in sub)
            elif v in ("highest_degree", "degree_year"):
                coll, fb = present, 0
            else:
                coll, fb = 0, present
            out.append(f"| {v} | {present} | {len(sub) - present} | {coll} | {fb} |")
        complete = [r for r in sub if all(str(r[v]) != "" for v in required) and not r["exclude_reason"]]
        out += ["", f"Complete cases, not excluded: **{len(complete)}**", ""]
        out += ["| Count | Value |", "|---|---|"]
        for name, counter in (
            ("current_rank", Counter(r["current_rank"] or "unknown" for r in sub)),
            ("rank_at_hire", Counter(r["rank_at_hire"] or "unknown" for r in sub)),
            ("highest_degree", Counter(r["highest_degree"] or "unknown" for r in sub)),
            ("academic_group", Counter(r["academic_group"] or "unknown" for r in sub)),
            ("confidence (lowest field)", Counter(r["confidence_min"] or "none" for r in sub)),
        ):
            out.append(f"| **{name}** | |")
            out += [f"| {n} | {k} |" for k, n in sorted(counter.items(), key=lambda kv: -kv[1])]
        flags = [("admin_flag", sum(r["admin_flag"] == 1 for r in sub)),
                 ("leave_flag", sum(r["leave_flag"] == 1 for r in sub)),
                 ("senior administrator (excluded)", sum(r["senior_admin_title"] == 1 for r in sub)),
                 ("hired 2025 or later (excluded)", sum("hired 2025" in r["exclude_reason"] for r in sub)),
                 ("automated check raised", sum(bool(r["checks"]) for r in sub)),
                 ("hire year from first-disclosure fallback", sum(r["hire_year_source"].startswith("first") for r in sub))]
        out += ["", "| Flag | Count |", "|---|---|"] + [f"| {k} | {n} |" for k, n in flags]
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
