#!/usr/bin/env python3
"""Build a Faculty of Health roster from the public faculty listings of its three units.

Usage:
  python3 scripts/build_health_roster.py

Each listing page is downloaded once and archived under data/raw/ (gitignored: names).
Retrieval date and SHA-256 go to data/raw/unit_manifest.csv. The roster goes to
data/private/health_roster.csv (unit, name). Listings show current faculty, so a person
who left after promotion is not in the roster.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
MANIFEST = RAW_DIR / "unit_manifest.csv"
ROSTER = ROOT / "data" / "private" / "health_roster.csv"
MANIFEST_FIELDS = ["unit", "url", "file", "retrieved", "sha256", "bytes"]

UNITS = {
    "SPHS": "https://uwaterloo.ca/public-health-sciences/faculty",
    "KHS": "https://uwaterloo.ca/kinesiology-health-sciences/faculty",
    "RLS": "https://uwaterloo.ca/recreation-and-leisure-studies/our-people/researchers-profiles",
}


def read_manifest() -> dict[str, dict[str, str]]:
    if not MANIFEST.exists():
        return {}
    with MANIFEST.open(encoding="utf-8") as f:
        return {r["unit"]: r for r in csv.DictReader(f)}


def archive(unit: str, url: str) -> dict[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        content = response.read()
    retrieved = date.today().isoformat()
    file_name = f"unit-{unit.lower()}_retrieved-{retrieved}.html"
    (RAW_DIR / file_name).write_bytes(content)
    return {"unit": unit, "url": url, "file": file_name, "retrieved": retrieved,
            "sha256": hashlib.sha256(content).hexdigest(), "bytes": str(len(content))}


def parse_names(page_html: str) -> list[str]:
    """Names from the aria-label of each profile link."""
    labels = re.findall(r'<a href="[^"]*/(?:people-)?profiles/[^"]+"\s+aria-label="([^"]+)"', page_html)
    return sorted({" ".join(html.unescape(label).split()) for label in labels})


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest()
    for unit, url in UNITS.items():
        if unit not in manifest:
            manifest[unit] = archive(unit, url)
            print(f"Archived {url} -> data/raw/{manifest[unit]['file']}")
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest[u] for u in UNITS)

    rows = []
    for unit, entry in manifest.items():
        content = (RAW_DIR / entry["file"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise SystemExit(f"SHA-256 mismatch for data/raw/{entry['file']}.")
        names = parse_names(content.decode("utf-8"))
        print(f"{unit}: {len(names)} names")
        rows += [{"unit": unit, "name": name} for name in names]

    ROSTER.parent.mkdir(parents=True, exist_ok=True)
    with ROSTER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["unit", "name"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {ROSTER.relative_to(ROOT)} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
