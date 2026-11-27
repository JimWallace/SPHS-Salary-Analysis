#!/usr/bin/env python3
"""Scope of a Stage 1-style comparison sample in the Cheriton School of Computer Science (counts only).

Usage:
  python3 scripts/anomaly_cs_scope.py [--refresh]

Nothing is collected here under docs/anomaly_collection_protocol.md. The script
1. reads the School's public contact listing (cached with the Health listings in
   data/private/anomaly_cache/; --refresh refetches) and keeps regular faculty whose home is the School,
   with the same position rules as anomaly_health_roster.py, plus the School's own name and the other
   Mathematics and Engineering units whose cross-appointed members it lists;
2. matches them to the 2025 salary disclosure by name, as for the Health roster;
3. measures the Faculty of Health collection (people per batch, second-round share, ORCID gap fill,
   evidence entries per person, and the share of matched people who reached the main fit), and applies
   those rates to the CS count.

Outputs:
- data/private/cs_roster.csv            (gitignored, names) one row per kept listing entry
- analysis_output/anomaly_cs_scope.md   (no names) counts
- analysis_output/anomaly_cs_scope.tex  (no names) LaTeX macros
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter

import anomaly_build_inputs as bi
import anomaly_common as ac
import anomaly_health_roster as hr
import promotion_cohort as pc

URLS = ["https://uwaterloo.ca/computer-science/contacts"]
OWN_UNIT = [r"David R\.? Cheriton School of Computer Science", r"Cheriton School of Computer Science",
            r"School of Computer Science", r"Computer Science", r"Software Engineering",  # program run by the School
            r"University Research Chair"]  # an honour, not another institution
# Units whose faculty the School lists as cross-appointed (home elsewhere).
OTHER_UNITS = re.compile(r"\b(?:Electrical|Combinatorics|Optimization|Applied Mathematics|"
                         r"Pure Mathematics|Engineering|Systems Design|Philosophy|Physics|Chemistry|Mathematics|Management Sciences?|"
                         r"Stratford|Conrad School|Public Health|Interaction Design)\b",
                         re.I)
HONORIFIC = re.compile(r"^(?:University|Distinguished|Cheriton|Canada Research Chair[^,]*,)\s*", re.I)
OUT = ac.PRIVATE / "cs_roster.csv"
OUT_MD = ac.OUT_DIR / "anomaly_cs_scope.md"
OUT_TEX = ac.OUT_DIR / "anomaly_cs_scope.tex"
BATCH_SIZE = 15  # people per first-round collection batch, as in the Health collection


def classify(pos: str) -> str:
    """'' if a regular faculty rank with home in the School, otherwise the reason it is dropped."""
    pos = HONORIFIC.sub("", pos.strip())
    reason = hr.classify_position(re.sub("|".join(OWN_UNIT), " ", pos, flags=re.I))
    if reason:
        return reason
    if OTHER_UNITS.search(re.sub("|".join(OWN_UNIT), " ", pos, flags=re.I)):
        return "position names another unit"
    return ""


def health_effort() -> dict:
    """Rates from the Faculty of Health collection (private files; counts only leave this function)."""
    targets = list(csv.DictReader((ac.PRIVATE / "anomaly_targets.csv").open(encoding="utf-8")))
    inputs = list(csv.DictReader((ac.PRIVATE / "anomaly_inputs.csv").open(encoding="utf-8")))
    log = list(csv.DictReader((ac.PRIVATE / "verification_log.csv").open(encoding="utf-8")))
    samples = list(csv.DictReader((ac.PRIVATE / "anomaly_model_samples.csv").open(encoding="utf-8")))
    collect = ac.PRIVATE / "anomaly_collect"

    def people(pattern: str) -> set[str]:
        out = set()
        for p in sorted(collect.glob(pattern)):
            out |= {r["person_id"] for r in json.loads(p.read_text(encoding="utf-8"))}
        return out

    first, second, orcid = people("batch_*.json"), people("supplement_round2_*.json"), people("supplement_zz_*.json")
    health = {r["person_id"] for r in inputs if r["in_health"] == "1" and r["is_subject"] != "1"}
    health_ok = {r["person_id"] for r in inputs if r["in_health"] == "1" and r["is_subject"] != "1"
                 and not r["exclude_reason"]}
    in_fit = {r["person_id"] for r in samples if r["spec"] == "S1_main"}
    evidence = [r for r in log if r["person_id"] in health and r["source_url"]
                and not r["method"].startswith("fallback")]
    hire_found = sum(r["hire_year_source"].startswith("collected") for r in inputs if r["person_id"] in health_ok)
    lag_found = sum(r["lag"] != "" for r in inputs if r["person_id"] in health_ok)
    return {
        "targets": len(targets), "first_round": len(first), "batches": math.ceil(len(first) / BATCH_SIZE),
        "health_colleagues": len(health), "health_ok": len(health_ok), "in_fit": len(in_fit & health),
        "second_share": len(second & health) / len(health), "orcid_share": len(orcid & health) / len(health),
        "evidence_per_person": len(evidence) / len(health),
        "hire_share": hire_found / len(health_ok), "lag_share": lag_found / len(health_ok),
        "fit_share": len(in_fit & health) / len(health_ok),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--roster", action="store_true", help="write data/private/cs_roster.csv only (inputs stage)")
    args = ap.parse_args()
    rows, dropped, retrieved = build_roster(args.refresh)
    if args.roster:
        print(f"Wrote {OUT.relative_to(ac.ROOT)}: {len(rows)} listed, "
              f"{sum(r['match_2025'] == 'unique' for r in rows)} matched to 2025.")
        return
    summarize(rows, dropped, retrieved)


def build_roster(refresh: bool = False) -> tuple[list[dict], Counter, str]:
    """Kept listing entries matched to the 2025 disclosure (writes data/private/cs_roster.csv)."""
    manifest = hr.read_cache_manifest()
    d2025 = pc.load_year(2025)
    index = hr.disclosure_index(d2025)
    kept: dict[str, dict] = {}
    dropped = Counter()
    retrieved = ""
    for url in URLS:
        page, retrieved = hr.fetch(url, manifest, refresh)
        for pattern in (hr.CARD, hr.CONTACT):
            for m in pattern.finditer(page):
                name, pos = hr.clean(m.group("name")), hr.clean(m.group("pos"))
                reason = classify(pos)
                if reason:
                    dropped[reason] += 1
                    continue
                href = m.group("href")
                href = href if href.startswith("http") else hr.BASE + href
                row = kept.setdefault(pc.normalize_name_part(name), {"name": name, "position": pos, "profile_url": href})
                if "/profiles/" in href and "/profiles/" not in row["profile_url"]:
                    row["profile_url"] = href
    hr.write_cache_manifest(manifest)

    rows = []
    for key, row in sorted(kept.items()):
        hits, how = hr.match_any(row["name"], index, d2025)
        regular = [h for h in hits if pc.is_main_campus_regular(h.cls) and bi.title_rank(h.title)]
        chosen = regular[0] if len(regular) == 1 else None
        row.update({"person_id": ac.person_id(chosen) if chosen else "",
                    "disc_surname": chosen.surname if chosen else "", "disc_given": chosen.given if chosen else "",
                    "match_2025": "unique" if chosen else ("ambiguous" if len(regular) > 1 else "none"),
                    "match_how": how, "title_2025": chosen.title if chosen else "",
                    "title_rank_2025": bi.title_rank(chosen.title) if chosen else "",
                    "senior_admin_title": int(bool(chosen) and bool(bi.SENIOR_ADMIN_TITLE.search(chosen.title))
                                              and not bi.rank_from_title(chosen.title))})
        rows.append(row)
    pc.write_csv(OUT, rows, ["person_id", "name", "position", "profile_url", "disc_surname", "disc_given",
                             "match_2025", "match_how", "title_2025", "title_rank_2025", "senior_admin_title"])
    return rows, dropped, retrieved


def summarize(rows: list[dict], dropped: Counter, retrieved: str) -> None:

    listed = len(rows)
    matched = [r for r in rows if r["match_2025"] == "unique"]
    ranks = Counter(r["title_rank_2025"] for r in matched)
    e = health_effort()
    exp_fit = round(len(matched) * e["fit_share"])
    batches = math.ceil(len(matched) / BATCH_SIZE)
    second = round(len(matched) * e["second_share"])
    evidence = round(len(matched) * e["evidence_per_person"])

    md = [
        "# Computer Science comparison: scope (no names, nothing collected)",
        "",
        "Generated by `scripts/anomaly_cs_scope.py`. Counts only.",
        "",
        f"Listing: {URLS[0]} (retrieved {retrieved}). Regular faculty with home in the School: **{listed}**; "
        f"matched to the 2025 disclosure: **{len(matched)}** ({100 * len(matched) / listed:.0f}%).",
        "",
        "| 2025 disclosed rank | Matched |", "|---|---|",
        *[f"| {k} | {n} |" for k, n in sorted(ranks.items(), key=lambda kv: -kv[1])],
        "",
        "Listing entries dropped: " + ", ".join(f"{k} {n}" for k, n in sorted(dropped.items())) + ".",
        "",
        "## Faculty of Health collection, for comparison",
        "",
        "| Measure | Value |", "|---|---|",
        f"| People in the first collection round (Health and promotion pool) | {e['first_round']} in "
        f"{e['batches']} batches of up to {BATCH_SIZE} |",
        f"| Health colleagues searched again in the second round | {100 * e['second_share']:.0f}% |",
        f"| Health colleagues with an ORCID gap fill | {100 * e['orcid_share']:.0f}% |",
        f"| Evidence entries (source, date, quotation) per Health colleague | {e['evidence_per_person']:.1f} |",
        f"| Hire year found in a public source (Health, not excluded) | {100 * e['hire_share']:.0f}% |",
        f"| Lag (degree and hire year) found | {100 * e['lag_share']:.0f}% |",
        f"| Reached the main fit | {e['in_fit']} of {e['health_ok']} ({100 * e['fit_share']:.0f}%) |",
        "",
        "## Applied to Computer Science",
        "",
        "| Measure | Estimate |", "|---|---|",
        f"| People to collect | {len(matched)} |",
        f"| First-round batches of {BATCH_SIZE} | {batches} |",
        f"| Second-round searches | about {second} |",
        f"| Evidence entries to record | about {evidence} |",
        f"| Expected colleagues in a main fit | about {exp_fit} (Faculty of Health: {e['in_fit']}) |",
        f"| People to collect for a fit as large as the Faculty of Health one | about "
        f"{math.ceil(e['in_fit'] / e['fit_share'])} |",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    macros = {
        "CSListed": listed, "CSMatched": len(matched), "CSCoverage": f"{100 * len(matched) / listed:.0f}",
        "CSProf": ranks.get("Professor", 0), "CSAssoc": ranks.get("Associate", 0),
        "CSAssist": ranks.get("Assistant", 0),
        "CSTeaching": sum(n for k, n in ranks.items() if k.endswith("-TS") or k == "Lecturer"),
        "CSRetrieved": retrieved, "CSBatches": batches, "CSSecond": second, "CSEvidence": evidence,
        "CSExpFit": exp_fit, "CSNeed": math.ceil(e["in_fit"] / e["fit_share"]), "HFirstRound": e["first_round"], "HBatches": e["batches"],
        "HSecondShare": f"{100 * e['second_share']:.0f}", "HEvidence": f"{e['evidence_per_person']:.0f}",
        "HHireShare": f"{100 * e['hire_share']:.0f}", "HFitShare": f"{100 * e['fit_share']:.0f}",
        "HInFit": e["in_fit"], "HOk": e["health_ok"], "CSBatchSize": BATCH_SIZE,
    }
    lines = ["% Generated by scripts/anomaly_cs_scope.py. Do not edit."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    OUT_TEX.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"CS listing: {listed} regular faculty, {len(matched)} matched to 2025; expected main-fit n about {exp_fit}.")


if __name__ == "__main__":
    main()
