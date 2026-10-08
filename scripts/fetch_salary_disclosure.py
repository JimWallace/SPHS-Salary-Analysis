#!/usr/bin/env python3
"""Archive one UW salary disclosure page under data/raw/ and record it in the manifest.

Usage:
  python3 scripts/fetch_salary_disclosure.py 2026
  python3 scripts/fetch_salary_disclosure.py 2025 --html saved_copy.html   # archive a copy you already downloaded

The page is downloaded only if the manifest has no entry for the year.
Outputs:
- data/raw/salary-disclosure-<year>_retrieved-<date>.html  (gitignored: contains names)
- data/raw/manifest.csv  (year, url, file, retrieved, sha256, bytes)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
MANIFEST = RAW_DIR / "manifest.csv"
MANIFEST_FIELDS = ["year", "url", "file", "retrieved", "sha256", "bytes"]
# Newer lists use the first pattern; older lists (2023 and before) use the second.
DISCLOSURE_URLS = [
    "https://uwaterloo.ca/about/accountability-reports/salary-disclosure-{}",
    "https://uwaterloo.ca/about/accountability/salary-disclosure-{}",
]


def read_manifest() -> list[dict[str, str]]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_manifest(rows: list[dict[str, str]]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: int(r["year"]))
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def download(year: int) -> tuple[str, bytes]:
    for pattern in DISCLOSURE_URLS:
        url = pattern.format(year)
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return url, response.read()
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
    raise SystemExit(f"No disclosure page found for {year}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("year", type=int)
    parser.add_argument("--html", type=Path, help="archive this already-downloaded copy instead of downloading")
    parser.add_argument("--url", help="source URL of the --html copy (default: first URL pattern)")
    parser.add_argument("--retrieved", default=date.today().isoformat(), help="retrieval date (ISO), default today")
    args = parser.parse_args()

    rows = read_manifest()
    existing = [r for r in rows if int(r["year"]) == args.year]
    if existing:
        print(f"{args.year} is already in {MANIFEST.relative_to(ROOT)} ({existing[0]['file']}); nothing to do.")
        return

    if args.html:
        url, content = args.url or DISCLOSURE_URLS[0].format(args.year), args.html.read_bytes()
    else:
        url, content = download(args.year)
    if b"<table" not in content:
        raise SystemExit(f"No <table> found in the {args.year} page; not archived.")

    file_name = f"salary-disclosure-{args.year}_retrieved-{args.retrieved}.html"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / file_name).write_bytes(content)

    rows.append(
        {
            "year": str(args.year),
            "url": url,
            "file": file_name,
            "retrieved": args.retrieved,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": str(len(content)),
        }
    )
    write_manifest(rows)
    print(f"Archived {url} -> data/raw/{file_name}")


if __name__ == "__main__":
    main()
