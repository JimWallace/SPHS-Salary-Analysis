#!/usr/bin/env python3
"""University-wide faculty roster with cross-appointments, from public UW department web pages.

Usage:
  python3 scripts/build_uw_roster.py [--delay 0.5]

For each academic unit below, reads its public contacts listing (uwaterloo.ca/<slug>/contacts),
keeps entries whose listed position is professorial or a lecturer, then reads each person's
public profile page and records any sentence mentioning a cross-appointment or joint appointment.
Pages are cached under data/private/uw_cache/ so reruns do not refetch.

Outputs (gitignored, names):
- data/private/uw_roster.csv          unit, faculty, name, position, profile_url, xa_text
- data/private/uw_roster_units.csv    unit, slug, contacts listed, faculty kept, fetch status

Cross-appointment is then defined two ways (see the analysis script): a profile that states one,
or the same person appearing in the faculty listings of two or more units.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "private" / "uw_cache"
OUT = ROOT / "data" / "private" / "uw_roster.csv"
OUT_UNITS = ROOT / "data" / "private" / "uw_roster_units.csv"
BASE = "https://uwaterloo.ca"
UA = "SPHS-salary-analysis research crawler (public pages, rate-limited)"

# (Faculty, unit name, site slug). Main-campus academic departments and schools.
UNITS = [
    ("Arts", "Anthropology", "anthropology"),
    ("Arts", "Classical Studies", "classical-studies"),
    ("Arts", "Communication Arts", "communication-arts"),
    ("Arts", "Economics", "economics"),
    ("Arts", "English Language and Literature", "english"),
    ("Arts", "Fine Arts", "fine-arts"),
    ("Arts", "French Studies", "french-studies"),
    ("Arts", "Germanic and Slavic Studies", "germanic-slavic-studies"),
    ("Arts", "History", "history"),
    ("Arts", "Philosophy", "philosophy"),
    ("Arts", "Political Science", "political-science"),
    ("Arts", "Psychology", "psychology"),
    ("Arts", "Sociology and Legal Studies", "sociology-and-legal-studies"),
    ("Arts", "Accounting and Finance", "school-of-accounting-and-finance"),
    ("Arts", "Stratford School", "stratford-school"),
    ("Engineering", "Architecture", "architecture"),
    ("Engineering", "Chemical Engineering", "chemical-engineering"),
    ("Engineering", "Civil and Environmental Engineering", "civil-environmental-engineering"),
    ("Engineering", "Electrical and Computer Engineering", "electrical-computer-engineering"),
    ("Engineering", "Management Science and Engineering", "management-science-engineering"),
    ("Engineering", "Mechanical and Mechatronics Engineering", "mechanical-mechatronics-engineering"),
    ("Engineering", "Systems Design Engineering", "systems-design-engineering"),
    ("Engineering", "Conrad School of Entrepreneurship and Business", "conrad-school-entrepreneurship-business"),
    ("Environment", "Geography and Environmental Management", "geography-environmental-management"),
    ("Environment", "Planning", "planning"),
    ("Environment", "Environment, Enterprise and Development", "school-environment-enterprise-development"),
    ("Environment", "Environment, Resources and Sustainability", "environment-resources-and-sustainability"),
    ("Health", "Public Health Sciences", "public-health-sciences"),
    ("Health", "Kinesiology and Health Sciences", "kinesiology-health-sciences"),
    ("Health", "Recreation and Leisure Studies", "recreation-and-leisure-studies"),
    ("Mathematics", "Applied Mathematics", "applied-mathematics"),
    ("Mathematics", "Combinatorics and Optimization", "combinatorics-and-optimization"),
    ("Mathematics", "Computer Science", "computer-science"),
    ("Mathematics", "Pure Mathematics", "pure-mathematics"),
    ("Mathematics", "Statistics and Actuarial Science", "statistics-and-actuarial-science"),
    ("Science", "Biology", "biology"),
    ("Science", "Chemistry", "chemistry"),
    ("Science", "Earth and Environmental Sciences", "earth-environmental-sciences"),
    ("Science", "Physics and Astronomy", "physics-astronomy"),
    ("Science", "Optometry and Vision Science", "optometry-vision-science"),
    ("Science", "Pharmacy", "pharmacy"),
]

FACULTY_POS = re.compile(r"\b(?:Professor|Lecturer)\b", re.I)
EXCLUDE_POS = re.compile(r"\b(?:Adjunct|Emerit|Visiting|Retired|Postdoc|Status only|Clinical|Sessional|"
                         r"Research Professor|Research Assistant Professor|Research Associate Professor)\b", re.I)
# Positions held at another institution (people listed without the word "adjunct").
EXTERNAL = re.compile(r"\b(?:Universit(?:y|e|é)(?! of Waterloo| Research Chair)|College|Hospital|Institute|Laurier|"
                      r"McMaster|Guelph|Inc\b|Ltd\b|Health Network|Public Health Ontario|Government)", re.I)
XA = re.compile(r"[^.]{0,120}\b(?:cross[- ]?appoint\w*|joint(?:ly)? appoint\w*)[^.]{0,160}", re.I)
CONTACT = re.compile(
    r'<h2 class="uw-contact__h2">\s*<a href="(?P<href>[^"]+)">\s*(?P<name>.*?)\s*</a>\s*</h2>\s*'
    r'(?:<span class="uw-contact__position">\s*(?P<pos>.*?)\s*</span>)?(?P<rest>.*?)(?=<h2 class="uw-contact__h2">|\Z)',
    re.S)
PROFILE = re.compile(r'<div class="uw-contact__profile">.*?<a href="(?P<href>[^"]+)"', re.S)


def get(url: str, delay: float) -> str | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    time.sleep(delay)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            text = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        text = f"<!-- HTTP {e.code} -->"
    except Exception as e:  # network hiccup: do not cache
        print(f"  fetch failed {url}: {e}")
        return None
    path.write_text(text, encoding="utf-8")
    return text


def clean(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def page_text(page: str) -> str:
    page = re.sub(r"<(script|style|nav|header|footer)\b.*?</\1>", " ", page, flags=re.S | re.I)
    main = re.search(r"<main\b.*?</main>", page, re.S | re.I)
    txt = clean(main.group(0) if main else page)
    # Site navigation menus contain the phrase "Cross appointments" as a link; drop it.
    return re.sub(r"Cross[- ]appointments Adjunct appointments", " ", txt)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()
    rows, unit_rows = [], []
    for fac, unit, slug in UNITS:
        listing = get(f"{BASE}/{slug}/contacts", args.delay)
        if not listing or listing.startswith("<!-- HTTP"):
            unit_rows.append({"faculty": fac, "unit": unit, "slug": slug, "contacts": 0, "kept": 0,
                              "status": "no contacts page"})
            print(f"{unit}: no contacts page")
            continue
        entries = list(CONTACT.finditer(listing))
        kept = 0
        for m in entries:
            pos = clean(m.group("pos") or "")
            if not FACULTY_POS.search(pos) or EXCLUDE_POS.search(pos) or EXTERNAL.search(pos):
                continue
            name = clean(m.group("name"))
            prof = PROFILE.search(m.group("rest"))
            href = prof.group("href") if prof else m.group("href")
            url = href if href.startswith("http") else BASE + href
            page = get(url, args.delay) or ""
            txt = page_text(page)
            xa = " || ".join(dict.fromkeys(x.strip() for x in XA.findall(txt)))[:600]
            rows.append({"faculty": fac, "unit": unit, "slug": slug, "name": name, "position": pos,
                         "profile_url": url, "xa_text": xa})
            kept += 1
        unit_rows.append({"faculty": fac, "unit": unit, "slug": slug, "contacts": len(entries), "kept": kept,
                          "status": "ok"})
        print(f"{unit}: {len(entries)} contacts, {kept} faculty")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with OUT_UNITS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(unit_rows[0].keys()))
        w.writeheader()
        w.writerows(unit_rows)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(rows)} rows) and {OUT_UNITS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
