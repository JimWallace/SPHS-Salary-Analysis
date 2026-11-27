#!/usr/bin/env python3
"""Fill gaps in the collected inputs from public ORCID records.

Usage:
  python3 scripts/anomaly_orcid_fill.py

For each target whose collected record lacks degree year, UW hire year or rank at hire, search the
public ORCID registry (pub.orcid.org v3.0 expanded search) for family name + given name + an
affiliation with the University of Waterloo. Only a single unambiguous hit is used. From that record:
- degree year: end year of the doctoral (else highest) education entry;
- UW hire year and rank at hire: the earliest University of Waterloo employment entry whose role is a
  regular faculty rank (not adjunct, research, visiting, postdoctoral or clinical).

Responses are cached in data/private/anomaly_cache/orcid/. Output (gitignored, names):
data/private/anomaly_collect/supplement_orcid.json, in the collection-protocol format, containing only
the fields it fills. anomaly_build_inputs.py uses supplements only where the primary record is null.
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date

import anomaly_common as ac

CACHE = ac.PRIVATE / "anomaly_cache" / "orcid"
TARGETS = ac.PRIVATE / "anomaly_targets.csv"
COLLECT = ac.PRIVATE / "anomaly_collect"
OUT = COLLECT / "supplement_orcid.json"
API = "https://pub.orcid.org/v3.0"

FACULTY_ROLE = re.compile(r"\b(?:(?:Assistant|Associate) )?Professor\b|\bLecturer\b", re.I)
NON_REGULAR = re.compile(r"\b(?:Adjunct|Research|Visiting|Post-?doc\w*|Clinical|Emerit\w*|Sessional|Honorary)\b", re.I)
DOCTORAL = re.compile(r"\b(?:Ph\.?\s?D|D\.?Phil|Doctor|Doctorate|Ed\.?D|Dr\.?P\.?H|Sc\.?D)\b", re.I)
MASTERS = re.compile(r"\b(?:M\.?Sc|M\.?A\b|Master|M\.?Eng|MPH|MBA|M\.?Math|MASc)\b", re.I)


def get_json(path: str) -> dict:
    key = re.sub(r"[^A-Za-z0-9]+", "_", path)[:180] + ".json"
    cached = CACHE / key
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    time.sleep(0.3)
    req = urllib.request.Request(API + path, headers={"Accept": "application/json", "User-Agent": "research-script"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data), encoding="utf-8")
    return data


def year(d) -> int | None:
    try:
        return int(((d or {}).get("year") or {}).get("value"))
    except (TypeError, ValueError):
        return None


def entries(orcid: str, section: str) -> list[dict]:
    out = []
    for g in get_json(f"/{orcid}/{section}").get("affiliation-group", []):
        for s in g.get("summaries", []):
            x = next(iter(s.values()))
            out.append({"org": x["organization"]["name"], "dept": x.get("department-name") or "",
                        "role": x.get("role-title") or "", "start": year(x.get("start-date")),
                        "end": year(x.get("end-date"))})
    return out


def search(given: str, family: str) -> list[str]:
    q = f'family-name:"{family}" AND given-names:"{given}" AND affiliation-org-name:"University of Waterloo"'
    res = get_json("/expanded-search/?" + urllib.parse.urlencode({"q": q, "rows": 5}))
    return [r["orcid-id"] for r in res.get("expanded-result") or []]


def names(t: dict) -> list[tuple[str, str]]:
    disp = re.sub(r"\(.*?\)|\b[A-Z]\.\s?", " ", t["display_name"]).split()
    given_first = disp[0] if disp else t["disc_given"].split()[0].title()
    out = [(given_first, disp[-1] if disp else t["disc_surname"].title())]
    out.append((t["disc_given"].split()[0].title(), t["disc_surname"].title()))
    return list(dict.fromkeys(out))


def main() -> None:
    primary = {}
    for p in sorted(COLLECT.glob("batch_*.json")):
        for r in json.loads(p.read_text(encoding="utf-8")):
            primary[r["person_id"]] = r
    with TARGETS.open(encoding="utf-8") as f:
        targets = [t for t in csv.DictReader(f) if t["is_subject"] != "1"]

    today = date.today().isoformat()
    out, stats = [], {"searched": 0, "unique hit": 0, "filled any": 0}
    for t in targets:
        rec = primary.get(t["person_id"], {})
        need = {k for k in ("degree_year", "hire_year_uw", "rank_at_hire")
                if rec.get(k) in (None, "", "unknown")}
        if not need:
            continue
        stats["searched"] += 1
        ids: list[str] = []
        for given, family in names(t):
            ids = search(given, family)
            if ids:
                break
        if len(ids) != 1:
            continue
        stats["unique hit"] += 1
        orcid = ids[0]
        url = f"https://orcid.org/{orcid}"
        fill = {"person_id": t["person_id"], "sources": [], "confidence": {}, "notes": f"ORCID {orcid}"}

        if "degree_year" in need:
            edu = entries(orcid, "educations")
            doc = [e for e in edu if DOCTORAL.search(e["role"]) and (e["end"] or e["start"])]
            if doc:
                e = max(doc, key=lambda e: e["end"] or e["start"])
                fill["degree_year"] = e["end"] or e["start"]
                fill["highest_degree"] = "Doctoral"
                fill["confidence"]["degree_year"] = "medium" if e["end"] else "low"
                fill["sources"].append({"field": "degree_year", "url": url, "retrieved": today,
                                        "quote": f"Education: {e['org']}, {e['role']}, {e['start']}-{e['end']}"})
        if need & {"hire_year_uw", "rank_at_hire"}:
            emp = [e for e in entries(orcid, "employments")
                   if "waterloo" in e["org"].lower() and "laurier" not in e["org"].lower()
                   and FACULTY_ROLE.search(e["role"]) and not NON_REGULAR.search(e["role"]) and e["start"]]
            # Use only an earliest entry at Assistant Professor or Lecturer. Entries at Associate or Professor
            # are usually the current rank with its own start date (a promotion, or a role title updated in
            # place) and contradicted the salary disclosures in testing, so they are not used.
            emp = [e for e in emp if re.search(r"Assistant|Lecturer|Teaching", e["role"], re.I)]
            if emp:
                e = min(emp, key=lambda e: e["start"])
                quote = f"Employment: {e['org']}, {e['dept']}, {e['role']}, {e['start']}-{e['end'] or 'present'}"
                # An earliest entry at Associate or Professor may be a promotion date entered as its own
                # employment row, so it is used only at low confidence and checked against disclosures.
                entry_rank_ok = bool(re.search(r"Assistant|Lecturer|Teaching", e["role"], re.I))
                if "hire_year_uw" in need:
                    fill["hire_year_uw"] = e["start"]
                    fill["confidence"]["hire_year_uw"] = "medium" if entry_rank_ok else "low"
                    fill["sources"].append({"field": "hire_year_uw", "url": url, "retrieved": today, "quote": quote})
                if "rank_at_hire" in need:
                    role = e["role"]
                    rank = ("Lecturer" if re.search(r"Lecturer|Teaching", role, re.I) else
                            "Assistant Professor" if re.search(r"Assistant", role, re.I) else
                            "Associate Professor" if re.search(r"Associate", role, re.I) else "Professor")
                    fill["rank_at_hire"] = rank
                    fill["confidence"]["rank_at_hire"] = "medium" if entry_rank_ok else "low"
                    fill["sources"].append({"field": "rank_at_hire", "url": url, "retrieved": today, "quote": quote})
        if len(fill["sources"]):
            stats["filled any"] += 1
            out.append(fill)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"ORCID: {stats}; wrote {OUT.relative_to(ac.ROOT)} ({len(out)} records)")


if __name__ == "__main__":
    main()
