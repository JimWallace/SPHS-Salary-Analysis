#!/usr/bin/env python3
"""Build title-and-salary panels from the UW salary disclosure pages.

Usage:
  python3 scripts/build_disclosure_title_panels.py --disclosures DIR [--rosters DIR] [--fetch-rosters]

DIR holds one page per year named <year>.html (2011-2025), e.g. downloaded with
`curl -L -o 2011.html https://uwaterloo.ca/about/accountability/salary-disclosure-2011`.

Outputs:
- data/sphs_titles.csv  (public: disclosed title for each SPHS panel person-year; every match is
                         checked against the salary already in data/sphs.csv)

Disclosed titles show academic rank only: administrative roles (Director, Associate Dean, Chair)
do not appear, so stipend years cannot be identified from them.
- data/private/comparison_unit_panels.csv  (gitignored: Kinesiology and Recreation and Leisure
                         Studies faculty, long format, built the same way as the SPHS panel)
- data/private/comparison_unit_matches.csv (gitignored: roster name -> disclosure match log)

The comparison units use their current public faculty and contact listings, like the SPHS
panel, so all three units share the same survivorship (only currently listed faculty).
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "sphs.csv"
OUT_SPHS_TITLES = ROOT / "data" / "sphs_titles.csv"
OUT_UNITS = ROOT / "data" / "private" / "comparison_unit_panels.csv"
OUT_MATCHES = ROOT / "data" / "private" / "comparison_unit_matches.csv"
YEARS = range(2011, 2026)

ROSTER_PAGES = {
    "KIN": ["https://uwaterloo.ca/kinesiology-health-sciences/faculty",
            "https://uwaterloo.ca/kinesiology-health-sciences/contacts"],
    "RLS": ["https://uwaterloo.ca/recreation-and-leisure-studies/about/people",
            "https://uwaterloo.ca/recreation-and-leisure-studies/contacts"],
}
PROFILE_LINK = re.compile(
    r'<a[^>]+href="/[a-z-]+/(?:contacts|about/people|profiles|people-profiles)/[a-z0-9-]+"[^>]*>(.*?)</a>', re.S)

REGULAR_RANK = re.compile(r"^(?:(Assistant|Associate) )?Professor(?:, Teaching Stream)?$")
ADMIN_WORD = re.compile(r"\b(?:Dean|Chair|Director|Vice-President|AVP|Provost|President|Principal|Head)\b")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z' -]", " ", text).upper().split())


NICKNAMES = {"BILL": "WILLIAM", "BOB": "ROBERT", "ROB": "ROBERT", "JEFF": "JEFFREY", "JON": "JONATHAN",
             "PAM": "PAMELA", "MIKE": "MICHAEL", "CHRIS": "CHRISTOPHER", "JIM": "JAMES", "KATIE": "KATHERINE"}


def first_token(given: str) -> str:
    toks = [t for t in norm(given).split() if len(t) > 1]
    tok = toks[0] if toks else norm(given)[:1]
    return NICKNAMES.get(tok, tok)


def parse_money(text: str) -> float:
    return float(re.sub(r"[^0-9.]", "", text) or "nan")


def parse_year(path: Path) -> list[dict]:
    page = path.read_text(encoding="utf-8", errors="replace")
    out = []
    for row in re.findall(r"<tr.*?</tr>", page, re.S):
        cells = [" ".join(html.unescape(re.sub(r"<.*?>", " ", c)).split())
                 for c in re.findall(r"<t[dh][ >].*?</t[dh]>", row, re.S)]  # some years put the surname in <th>
        if len(cells) < 4 or cells[0].lower() == "surname":
            continue
        try:
            salary = parse_money(cells[3])
        except ValueError:
            continue
        out.append({"surname": cells[0].upper(), "given": cells[1].upper(), "title": cells[2], "salary": salary})
    return out


def title_rank(title: str) -> str:
    """Academic rank implied by a disclosed title: assistant / associate / full / teaching / other."""
    first = title.split(";")[0].split(" and ")[0].strip()
    m = re.match(r"^(Assistant|Associate)? ?Professor\b", first)
    if m:
        level = {"Assistant": "assistant", "Associate": "associate"}.get(m.group(1) or "", "full")
        return f"teaching_{level}" if "Teaching Stream" in title else level
    return "lecturer" if first.startswith("Lecturer") else "other"


def load_disclosures(directory: Path) -> dict[int, list[dict]]:
    data = {}
    for y in YEARS:
        p = directory / f"{y}.html"
        if not p.exists():
            raise SystemExit(f"Missing {p}")
        data[y] = parse_year(p)
        if len(data[y]) < 500:
            raise SystemExit(f"Only {len(data[y])} rows parsed from {p}")
    return data


def build_sphs_titles(disc: dict[int, list[dict]]) -> list[dict]:
    rows_out = []
    with PANEL.open() as f:
        panel = list(csv.DictReader(f))
    unmatched = []
    for r in panel:
        sur = norm(r["Surname"])
        for y in YEARS:
            val = r.get(str(y), "")
            if not val:
                continue
            sal = float(val)
            hits = [d for d in disc[y] if norm(d["surname"]) == sur and abs(d["salary"] - sal) < 1.0]
            if len(hits) != 1:
                unmatched.append((sur, y, len(hits)))
                continue
            t = hits[0]["title"]
            rows_out.append({"Surname": r["Surname"], "year": y, "title": t, "rank": title_rank(t),
                             "admin_title": int(bool(ADMIN_WORD.search(t)))})
    if unmatched:
        raise SystemExit(f"SPHS person-years without a unique salary match: {unmatched[:10]} ({len(unmatched)})")
    return rows_out


def fetch_rosters(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for unit, urls in ROSTER_PAGES.items():
        for i, url in enumerate(urls):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                (directory / f"{unit}_{i}.html").write_bytes(resp.read())


def roster_names(directory: Path, unit: str) -> list[str]:
    names = set()
    for p in sorted(directory.glob(f"{unit}_*.html")):
        page = p.read_text(encoding="utf-8", errors="replace")
        for m in PROFILE_LINK.finditer(page):
            txt = " ".join(html.unescape(re.sub(r"<.*?>", " ", m.group(1))).split())
            txt = txt.replace(" - Profile", "")
            if txt and 2 <= len(txt.split()) <= 5:
                names.add(txt)
    return sorted(names)


def build_units(disc: dict[int, list[dict]], roster_dir: Path) -> tuple[list[dict], list[dict]]:
    # Index disclosures by (surname, first given token).
    index: dict[tuple[str, str], list[tuple[int, dict]]] = defaultdict(list)
    for y, rows in disc.items():
        for d in rows:
            index[(norm(d["surname"]), first_token(d["given"]))].append((y, d))
    panel_rows, log = [], []
    seen_people = set()
    for unit in ROSTER_PAGES:
        for name in roster_names(roster_dir, unit):
            parts = norm(name).split()
            given = [t for t in parts[:-1] if len(t) > 1]
            if not given:
                continue
            # Try last token, then last two tokens, as the surname.
            cands = []
            for k in (1, 2):
                sur = " ".join(parts[-k:])
                cands += index.get((sur, first_token(" ".join(given))), [])
            if not cands:
                log.append({"unit": unit, "roster_name": name, "status": "no disclosure match"})
                continue
            keys = {(norm(d["surname"]), norm(d["given"])) for _, d in cands}
            # Several people can share surname + first name across the university; keep the one
            # with a regular professorial title, and drop the name if that is still ambiguous.
            prof_keys = {(norm(d["surname"]), norm(d["given"])) for _, d in cands if REGULAR_RANK.match(
                d["title"].split(";")[0].strip()) or title_rank(d["title"]) not in {"other", "lecturer"}}
            if len({k[0] + "|" + first_token(k[1]) for k in prof_keys}) == 0:
                log.append({"unit": unit, "roster_name": name, "status": "matched, never a professorial title"})
                continue
            per_year = defaultdict(list)
            for y, d in cands:
                if (norm(d["surname"]), norm(d["given"])) in prof_keys:
                    per_year[y].append(d)
            if any(len(v) > 1 for v in per_year.values()):
                log.append({"unit": unit, "roster_name": name, "status": "ambiguous (two people same name in a year)"})
                continue
            pid = f"{unit}:{norm(name)}"
            if (unit, tuple(sorted(keys))) in seen_people:
                continue
            seen_people.add((unit, tuple(sorted(keys))))
            log.append({"unit": unit, "roster_name": name, "status": f"matched {len(per_year)} years"})
            for y, (d,) in sorted(per_year.items()):
                panel_rows.append({"unit": unit, "person": pid, "year": y, "salary": d["salary"],
                                   "title": d["title"], "rank": title_rank(d["title"]),
                                   "admin_title": int(bool(ADMIN_WORD.search(d["title"])))})
    # Collapse duplicate roster spellings of the same person (e.g. with and without middle initial).
    dedup = {}
    for r in panel_rows:
        dedup[(r["unit"], r["year"], r["salary"], r["title"])] = r
    return list(dedup.values()), log


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--disclosures", type=Path, required=True)
    ap.add_argument("--rosters", type=Path, default=ROOT / "data" / "private" / "rosters")
    ap.add_argument("--fetch-rosters", action="store_true")
    args = ap.parse_args()

    disc = load_disclosures(args.disclosures)
    sphs = build_sphs_titles(disc)
    write(OUT_SPHS_TITLES, sphs)
    print(f"Wrote {OUT_SPHS_TITLES.relative_to(ROOT)} ({len(sphs)} person-years, all salary-verified)")

    if args.fetch_rosters:
        fetch_rosters(args.rosters)
    units, log = build_units(disc, args.rosters)
    write(OUT_UNITS, units)
    write(OUT_MATCHES, log)
    for u in ROSTER_PAGES:
        people = {r["person"] for r in units if r["unit"] == u}
        print(f"{u}: {len(people)} people, {sum(r['unit'] == u for r in units)} person-years")
    print(f"Wrote {OUT_UNITS.relative_to(ROOT)} and {OUT_MATCHES.relative_to(ROOT)} (private)")


if __name__ == "__main__":
    main()
