#!/usr/bin/env python3
"""Count completed graduate theses supervised by each SPHS faculty member, by year, from UWSpace.

Usage:
  python3 scripts/build_theses_person_year.py

Queries the public UWSpace (DSpace) search API for theses whose advisor field contains the
faculty member's surname, then keeps records where an advisor entry contains both the surname and
the first given name (in either order). Co-supervised theses count once for each supervisor and are
also recorded as a 1/n share.

Output (gitignored, names): data/private/theses_person_year.csv
  person, year, level (phd/masters), n_theses, supervision_share
"""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "sphs.csv"
OUT = ROOT / "data" / "private" / "theses_person_year.csv"
API = "https://dspacemainprd01.lib.uwaterloo.ca/server/api/discover/search/objects"
NICK = {"JAMES": {"JIM", "JAMES"}, "PETER": {"PETER", "PETE"}, "JOHN": {"JOHN", "JACK"},
        "MARK": {"MARK"}, "PHILIP": {"PHILIP", "PHIL"}, "WARREN": {"WARREN"}}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z' -]", " ", text).upper().split())


def fetch(query: str, page: int) -> dict:
    params = urllib.parse.urlencode({"query": query, "dsoType": "ITEM", "size": 100, "page": page})
    req = urllib.request.Request(f"{API}?{params}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main() -> None:
    with PANEL.open() as f:
        panel = list(csv.DictReader(f))
    counts = defaultdict(lambda: [0, 0.0])
    for row in panel:
        surname_tokens = [t for t in norm(row["Surname"]).replace("(", " ").split() if len(t) > 2]
        given = [t for t in norm(row["Given name"]).split() if len(t) > 1][0]
        given_ok = NICK.get(given, {given})
        sur = surname_tokens[-1] if len(surname_tokens) > 1 and row["Surname"].startswith("TAIT") else surname_tokens[0]
        seen = set()
        page = 0
        while True:
            d = fetch(f"dc.contributor.advisor:{sur}", page)
            sr = d["_embedded"]["searchResult"]
            for o in sr["_embedded"]["objects"]:
                item = o["_embedded"]["indexableObject"]
                md = item["metadata"]
                g = lambda k: [v["value"] for v in md.get(k, [])]
                advisors = g("dc.contributor.advisor")
                hit = [a for a in advisors if sur in norm(a).split() and given_ok & set(norm(a).split())]
                if not hit or item["uuid"] in seen:
                    continue
                seen.add(item["uuid"])
                year = int((g("dc.date.issued") or ["0"])[0][:4])
                degree = " ".join(g("uws-etd.degree") + g("dc.type")).lower()
                level = "phd" if "doctor" in degree else "masters"
                counts[(row["Surname"], year, level)][0] += 1
                counts[(row["Surname"], year, level)][1] += 1 / max(len(advisors), 1)
            if page + 1 >= sr["page"]["totalPages"]:
                break
            page += 1
            time.sleep(0.5)
        print(f"{row['Surname']}: {len(seen)} theses")
        time.sleep(0.5)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["person", "year", "level", "n_theses", "supervision_share"])
        for (p, y, lvl), (n, sh) in sorted(counts.items()):
            w.writerow([p, y, lvl, n, round(sh, 3)])
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
