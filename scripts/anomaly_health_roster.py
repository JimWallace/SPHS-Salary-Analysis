#!/usr/bin/env python3
"""Current regular faculty in the three Faculty of Health units, from their public listings.

Usage:
  python3 scripts/anomaly_health_roster.py [--refresh]

Reads each unit's public faculty and contact listings (cached under data/private/anomaly_cache/,
with URL, retrieval date and SHA-256 in data/private/anomaly_cache/manifest.csv; --refresh refetches)
and keeps entries whose listed position is a regular University of Waterloo faculty rank:
Assistant/Associate Professor, Professor (with or without "Teaching Stream"), or Lecturer.
Emeritus, adjunct, research, clinical, visiting, postdoctoral, staff and instructor positions are
dropped, as are positions that name another institution or another UW unit (people whose home
unit is elsewhere and who are listed here as cross-appointed or adjunct).

Each kept person is matched to the 2025 salary disclosure by normalized name
(promotion_cohort.name_key, with the nickname table from build_disclosure_title_panels).

Outputs (gitignored, names):
- data/private/health_roster.csv          one row per person: unit, name, position, profile URL,
                                          listing URL, retrieval date, 2025 disclosure match
- data/private/health_roster_dropped.csv  listing entries not kept, with the reason
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

import promotion_cohort as pc

ROOT = pc.ROOT
CACHE = ROOT / "data" / "private" / "anomaly_cache" / "listings"
CACHE_MANIFEST = ROOT / "data" / "private" / "anomaly_cache" / "manifest.csv"
OUT = ROOT / "data" / "private" / "health_roster.csv"
OUT_DROPPED = ROOT / "data" / "private" / "health_roster_dropped.csv"
BASE = "https://uwaterloo.ca"

UNITS = {
    "SPHS": ("School of Public Health Sciences", [
        "https://uwaterloo.ca/public-health-sciences/faculty",
        "https://uwaterloo.ca/public-health-sciences/contacts",
    ]),
    "KHS": ("Kinesiology and Health Sciences", [
        "https://uwaterloo.ca/kinesiology-health-sciences/faculty",
        "https://uwaterloo.ca/kinesiology-health-sciences/contacts",
    ]),
    "RLS": ("Recreation and Leisure Studies", [
        "https://uwaterloo.ca/recreation-and-leisure-studies/about/people",
        "https://uwaterloo.ca/recreation-and-leisure-studies/contacts",
    ]),
}

NICKNAMES = {"BILL": "WILLIAM", "BOB": "ROBERT", "ROB": "ROBERT", "JEFF": "JEFFREY", "JON": "JONATHAN",
             "PAM": "PAMELA", "MIKE": "MICHAEL", "CHRIS": "CHRISTOPHER", "JIM": "JAMES", "KATIE": "KATHERINE",
             "DAVE": "DAVID", "DAN": "DANIEL", "STEVE": "STEPHEN", "SAM": "SAMUEL", "TOM": "THOMAS",
             "JOE": "JOSEPH", "KATE": "KATHERINE", "LIZ": "ELIZABETH", "NICK": "NICHOLAS", "ANDY": "ANDREW",
             "GEOFF": "GEOFFREY", "SUE": "SUSAN", "MATT": "MATTHEW", "ALEX": "ALEXANDER"}

RANK = re.compile(r"^(?:(?:Assistant|Associate) )?Professor(?:, Teaching Stream)?\b|^Lecturer\b", re.I)
EXCLUDE = re.compile(r"\b(?:Emerit\w*|Adjunct|Research Professor|Assistant Research Professor|Clinical|Visiting|"
                     r"Postdoc\w*|Post-doctoral|Postdoctoral|Instructor|Professor of Practice)\b", re.I)
# A position naming another institution, another UW unit, or an affiliated college.
ELSEWHERE = re.compile(
    r"\b(?:Universit(?:y|é|e)|College|Institute|Hospital|Agency|Laurier|McMaster|Guelph|York|Toronto|Western|"
    r"Brock|Alberta|Calgary|Victoria|Leuven|Bath|Deakin|Laval|Trent|Lakehead|Renison|St\.? ?Jerome|Conrad Grebel|"
    r"School of Pharmacy|Pharmacy|Statistics|Psychology|Biology|Geography|Computer Science|Kinesiology and Health|"
    r"Recreation and Leisure|English|Sociology|Anthropology|Nursing|Medicine|CIHI|ITK|Inc\b|Corp\b|Ltd\b)",
    re.I)
OWN_UNIT_NAMES = [r"Department of Kinesiology and Health Sciences", r"Faculty of Health",
                  r"School of Public Health Sciences", r"Department of Recreation and Leisure Studies"]
CROSS_TO = re.compile(r"Cross-Appointed to", re.I)  # "..., Cross-Appointed to <other unit>": home is this unit

CARD = re.compile(r'<h2 class="card__title">\s*<a href="(?P<href>[^"]+)">\s*(?P<name>.*?)\s*</a>\s*</h2>'
                  r'(?:\s*<div class="card__position">\s*(?P<pos>.*?)\s*</div>)?', re.S)
CONTACT = re.compile(r'<h2 class="uw-contact__h2">\s*<a href="(?P<href>[^"]+)">\s*(?P<name>.*?)\s*</a>\s*</h2>'
                     r'(?:\s*<span class="uw-contact__position">\s*(?P<pos>.*?)\s*</span>)?', re.S)


def clean(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).split())


def read_cache_manifest() -> dict[str, dict[str, str]]:
    if not CACHE_MANIFEST.exists():
        return {}
    with CACHE_MANIFEST.open(encoding="utf-8") as f:
        return {r["url"]: r for r in csv.DictReader(f)}


def write_cache_manifest(entries: dict[str, dict[str, str]]) -> None:
    CACHE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "file", "retrieved", "sha256", "bytes"])
        w.writeheader()
        w.writerows(sorted(entries.values(), key=lambda r: r["url"]))


def fetch(url: str, manifest: dict[str, dict[str, str]], refresh: bool) -> tuple[str, str]:
    """Page text and retrieval date, from the cache unless refresh is set."""
    name = hashlib.sha1(url.encode()).hexdigest()[:16] + ".html"
    path = CACHE / name
    if path.exists() and url in manifest and not refresh:
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest[url]["sha256"]:
            raise SystemExit(f"SHA-256 mismatch for cached {url}")
        return content.decode("utf-8", errors="replace"), manifest[url]["retrieved"]
    time.sleep(0.5)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        content = r.read()
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    manifest[url] = {"url": url, "file": name, "retrieved": date.today().isoformat(),
                     "sha256": hashlib.sha256(content).hexdigest(), "bytes": str(len(content))}
    return content.decode("utf-8", errors="replace"), manifest[url]["retrieved"]


def classify_position(pos: str) -> str:
    """'' if the position is a regular faculty rank in this unit, otherwise the reason it is dropped."""
    if not pos:
        return "no position listed"
    if not RANK.search(pos):
        return "not a faculty rank"
    if EXCLUDE.search(pos):
        return "non-regular position"
    rest = CROSS_TO.split(pos)[0]
    for own in OWN_UNIT_NAMES:  # an administrative role in the unit itself is not "elsewhere"
        rest = re.sub(own, " ", rest, flags=re.I)
    if ELSEWHERE.search(rest):
        return "position names another institution or unit"
    return ""


def name_parts(display: str) -> tuple[str, str]:
    """(surname, given) from a display name; drops honorifics and parenthesized nicknames."""
    display = re.sub(r"\(.*?\)|\b(?:Dr|Prof)\.?\s", " ", display)
    toks = display.split()
    return " ".join(toks[-1:]), " ".join(toks[:-1])


def disclosure_index(records: list[pc.Record]) -> dict[tuple[str, str], list[pc.Record]]:
    index: dict[tuple[str, str], list[pc.Record]] = {}
    for r in records:
        s, g = r.key
        first = g.split()[0] if g else ""
        index.setdefault((s, NICKNAMES.get(first, first)), []).append(r)
    return index


def given_tokens(given: str) -> list[str]:
    toks = [t for t in pc.normalize_name_part(given).split() if len(t) > 1]
    return [NICKNAMES.get(t, t) for t in toks]


def relaxed_match(display: str, records: list[pc.Record]) -> list[pc.Record]:
    """Compound or hyphenated surnames and leading initials: a roster surname token must appear in the
    disclosed surname and the roster first name must be one of the disclosed given names."""
    toks = [t for t in pc.normalize_name_part(re.sub(r"\(.*?\)", " ", display)).split() if t not in {"DR", "PROF"}]
    if len(toks) < 2:
        return []
    first, surname = NICKNAMES.get(toks[0], toks[0]), toks[-1]
    return [r for r in records if surname in r.key[0].split() and first in given_tokens(r.given)]


def match(display: str, index: dict) -> tuple[list[pc.Record], str]:
    toks = pc.normalize_name_part(re.sub(r"\(.*?\)", " ", display)).split()
    toks = [t for t in toks if t not in {"DR", "PROF"}]
    if len(toks) < 2:
        return [], "unparsed name"
    first = NICKNAMES.get(toks[0], toks[0])
    for k in (1, 2, 3):  # last token, then compound surnames
        if len(toks) - k < 1:
            break
        hits = index.get((" ".join(toks[-k:]), first), [])
        if hits:
            return hits, f"surname={k} token(s)"
    return [], "no match"


def match_any(display: str, index: dict, records: list[pc.Record]) -> tuple[list[pc.Record], str]:
    hits, how = match(display, index)
    if hits:
        return hits, how
    hits = relaxed_match(display, records)
    return hits, ("relaxed (compound surname or initials): check" if hits else "no match")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    manifest = read_cache_manifest()
    d2025 = pc.load_year(2025)
    index = disclosure_index(d2025)

    people: dict[tuple[str, str], dict[str, str]] = {}
    dropped: list[dict[str, str]] = []
    for unit, (unit_name, urls) in UNITS.items():
        for url in urls:
            page, retrieved = fetch(url, manifest, args.refresh)
            for pattern in (CARD, CONTACT):
                for m in pattern.finditer(page):
                    name, pos = clean(m.group("name")), clean(m.group("pos"))
                    href = m.group("href")
                    href = href if href.startswith("http") else BASE + href
                    reason = classify_position(pos)
                    key = (unit, pc.normalize_name_part(name))
                    if reason:
                        dropped.append({"unit": unit, "name": name, "position": pos, "reason": reason,
                                        "listing_url": url})
                        continue
                    row = people.setdefault(key, {
                        "unit": unit, "unit_name": unit_name, "faculty": "Health", "name": name,
                        "position": pos, "profile_url": href, "listing_url": url, "listing_retrieved": retrieved,
                    })
                    if "/profiles/" in href and "/profiles/" not in row["profile_url"]:
                        row["profile_url"] = href  # prefer the profile page over the contact card
    write_cache_manifest(manifest)

    # Drop people whose kept entry was overridden by a dropped entry in the same unit (e.g. listed
    # as faculty on one page and as emeritus on the other): flag for review instead of guessing.
    dropped_keys = {(d["unit"], pc.normalize_name_part(d["name"])) for d in dropped
                    if d["reason"] == "non-regular position"}

    rows = []
    for key, row in sorted(people.items()):
        hits, how = match_any(row["name"], index, d2025)
        # Faculty ranks, lecturers, and purely administrative titles (e.g. Dean); never college or non-regular.
        regular = [h for h in hits if pc.is_main_campus_regular(h.cls) and
                   (h.cls.rank != "other" or "Lecturer" in h.title or "admin" in h.cls.flags)]
        chosen = regular if len(regular) == 1 else []
        row.update({
            "conflicting_listing": "yes" if key in dropped_keys else "",
            "match_2025": "unique" if chosen else ("ambiguous" if len(regular) > 1 else "none"),
            "match_how": how,
            "disc_surname": chosen[0].surname if chosen else "",
            "disc_given": chosen[0].given if chosen else "",
            "title_2025": chosen[0].title if chosen else "",
        })
        rows.append(row)

    # A person listed by two Health units: keep one row, flag both units.
    by_person: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        k = (r["disc_surname"], r["disc_given"]) if r["disc_surname"] else ("", r["name"])
        by_person.setdefault(k, []).append(r)
    final = []
    for group in by_person.values():
        if len(group) > 1:
            units = ";".join(sorted(g["unit"] for g in group))
            for g in group:
                g["also_listed_by"] = units
        final.append(group[0])
    for r in final:
        r.setdefault("also_listed_by", "")

    pc.write_csv(OUT, final, list(final[0].keys()))
    pc.write_csv(OUT_DROPPED, dropped, ["unit", "name", "position", "reason", "listing_url"])
    print(f"Kept {len(final)} people; dropped {len(dropped)} listing entries.")
    for unit in UNITS:
        sub = [r for r in final if r["unit"] == unit]
        print(f"  {unit}: {len(sub)} kept, 2025 match unique {sum(r['match_2025'] == 'unique' for r in sub)}, "
              f"ambiguous {sum(r['match_2025'] == 'ambiguous' for r in sub)}, none {sum(r['match_2025'] == 'none' for r in sub)}")


if __name__ == "__main__":
    main()
