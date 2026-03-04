#!/usr/bin/env python3
"""
Scrape publicly available SPHS faculty pages and export group memberships.

Outputs:
- data/public_sphs_scrape/raw_html/faculty_listing.html
- data/public_sphs_scrape/raw_html/cross_appointments.html
- data/public_sphs_scrape/raw_html/profiles/<slug>.html
- data/public_sphs_scrape/faculty_group_membership.csv
- data/public_sphs_scrape/faculty_roster_with_groups.csv
- data/public_sphs_scrape/cross_appointments_reference.csv
- analysis_output/public_sphs_group_summary.csv
"""

from __future__ import annotations

import csv
import html
import re
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
LISTING_URL = "https://uwaterloo.ca/public-health-sciences/faculty"
CROSS_APPOINTMENTS_URL = "https://uwaterloo.ca/public-health-sciences/our-people/our-people-cross-appointments"
BASE_URL = "https://uwaterloo.ca"

SCRAPE_DIR = ROOT / "data" / "public_sphs_scrape"
RAW_DIR = SCRAPE_DIR / "raw_html"
PROFILE_RAW_DIR = RAW_DIR / "profiles"
MEMBERSHIP_CSV = SCRAPE_DIR / "faculty_group_membership.csv"
ROSTER_CSV = SCRAPE_DIR / "faculty_roster_with_groups.csv"
CROSS_REFERENCE_CSV = SCRAPE_DIR / "cross_appointments_reference.csv"
GROUP_SUMMARY_CSV = ROOT / "analysis_output" / "public_sphs_group_summary.csv"


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_text(value: str) -> str:
    stripped = re.sub(r"<[^>]+>", " ", value)
    unescaped = html.unescape(stripped)
    return re.sub(r"\s+", " ", unescaped).strip()


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def article_blocks(listing_html: str) -> Iterable[str]:
    return re.findall(r"<article[^>]*card__teaser--profile[^>]*>(.*?)</article>", listing_html, flags=re.IGNORECASE | re.DOTALL)


def parse_profile_href(block_html: str) -> Optional[str]:
    match = re.search(r"<h2[^>]*class=\"card__title\"[^>]*>.*?<a[^>]*href=\"([^\"]+)\"", block_html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    href = match.group(1).strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def parse_faculty_name(block_html: str) -> str:
    match = re.search(r"<h2[^>]*class=\"card__title\"[^>]*>(.*?)</h2>", block_html, flags=re.IGNORECASE | re.DOTALL)
    return clean_text(match.group(1)) if match else ""


def parse_group_tags(block_html: str) -> List[str]:
    tags_match = re.search(r"<div[^>]*class=\"card__tags\"[^>]*>(.*?)</div>", block_html, flags=re.IGNORECASE | re.DOTALL)
    if not tags_match:
        return []
    tags_html = tags_match.group(1)
    raw_tags = re.findall(r"<a[^>]*rel=\"tag\"[^>]*>(.*?)</a>", tags_html, flags=re.IGNORECASE | re.DOTALL)
    cleaned = [clean_text(tag) for tag in raw_tags]
    return [tag for tag in cleaned if tag and tag.lower() != "faculty"]


def name_key(display_name: str) -> Optional[tuple[str, str]]:
    tokens = re.findall(r"[A-Za-z]+", display_name.upper())
    if len(tokens) < 2:
        return None
    return (tokens[0], tokens[-1])


def parse_cross_appointment_names(cross_html: str) -> List[str]:
    headings = re.findall(r"<h2[^>]*>(.*?)</h2>", cross_html, flags=re.IGNORECASE | re.DOTALL)
    names: List[str] = []
    for heading in headings:
        cleaned = clean_text(heading)
        if not cleaned:
            continue
        if cleaned.lower().startswith("information about"):
            continue
        key = name_key(cleaned)
        if key is None:
            continue
        names.append(cleaned)
    return names


def slug_from_profile_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", slug)
    return slug or "profile"


def write_membership_csv(rows: List[Dict[str, str]]) -> None:
    MEMBERSHIP_CSV.parent.mkdir(parents=True, exist_ok=True)
    with MEMBERSHIP_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["faculty_name", "profile_url", "group_tag", "cross_appointment"])
        writer.writeheader()
        writer.writerows(rows)


def write_roster_csv(rows: List[Dict[str, str]]) -> None:
    ROSTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    with ROSTER_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "faculty_name",
                "profile_url",
                "cross_appointment",
                "group_count",
                "group_tags",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_group_summary_csv(rows: List[Dict[str, str]]) -> None:
    GROUP_SUMMARY_CSV.parent.mkdir(parents=True, exist_ok=True)
    with GROUP_SUMMARY_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["group_tag", "faculty_count"])
        writer.writeheader()
        writer.writerows(rows)


def write_cross_reference_csv(rows: List[Dict[str, str]]) -> None:
    CROSS_REFERENCE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with CROSS_REFERENCE_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "cross_appointment_name",
                "matched_faculty_listing_name",
                "matched_on_faculty_listing",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    listing_html = fetch_text(LISTING_URL)
    save_text(RAW_DIR / "faculty_listing.html", listing_html)
    cross_html = fetch_text(CROSS_APPOINTMENTS_URL)
    save_text(RAW_DIR / "cross_appointments.html", cross_html)

    cross_names = parse_cross_appointment_names(cross_html)
    cross_keys = {key for key in (name_key(name) for name in cross_names) if key is not None}

    membership_rows: List[Dict[str, str]] = []
    roster_rows: List[Dict[str, str]] = []
    group_members: Dict[str, set[str]] = {}
    profile_urls: Dict[str, str] = {}

    for block in article_blocks(listing_html):
        name = parse_faculty_name(block)
        profile_url = parse_profile_href(block)
        tags = parse_group_tags(block)

        if not name:
            continue

        if profile_url:
            profile_urls[name] = profile_url

        cross_flag = "1" if (name_key(name) in cross_keys) else "0"

        for tag in tags:
            membership_rows.append(
                {
                    "faculty_name": name,
                    "profile_url": profile_url or "",
                    "group_tag": tag,
                    "cross_appointment": cross_flag,
                }
            )
            group_members.setdefault(tag, set()).add(name)

        roster_rows.append(
            {
                "faculty_name": name,
                "profile_url": profile_url or "",
                "cross_appointment": cross_flag,
                "group_count": str(len(tags)),
                "group_tags": "; ".join(tags),
            }
        )

    # Save raw public profile pages locally.
    for name, profile_url in profile_urls.items():
        try:
            profile_html = fetch_text(profile_url)
        except Exception as exc:
            print(f"Warning: failed to fetch {profile_url}: {exc}")
            continue
        slug = slug_from_profile_url(profile_url)
        save_text(PROFILE_RAW_DIR / f"{slug}.html", profile_html)

    write_membership_csv(membership_rows)
    write_roster_csv(roster_rows)

    summary_rows = [
        {"group_tag": group_tag, "faculty_count": str(len(members))}
        for group_tag, members in sorted(group_members.items(), key=lambda item: (-len(item[1]), item[0].lower()))
    ]
    write_group_summary_csv(summary_rows)

    faculty_key_to_name: Dict[tuple[str, str], str] = {}
    for row in roster_rows:
        key = name_key(row["faculty_name"])
        if key is not None and key not in faculty_key_to_name:
            faculty_key_to_name[key] = row["faculty_name"]

    cross_reference_rows: List[Dict[str, str]] = []
    for cross_name in cross_names:
        key = name_key(cross_name)
        matched_name = faculty_key_to_name.get(key, "") if key is not None else ""
        cross_reference_rows.append(
            {
                "cross_appointment_name": cross_name,
                "matched_faculty_listing_name": matched_name,
                "matched_on_faculty_listing": "1" if matched_name else "0",
            }
        )
    write_cross_reference_csv(cross_reference_rows)

    print(f"Saved listing HTML: {(RAW_DIR / 'faculty_listing.html').resolve()}")
    print(f"Saved cross appointments HTML: {(RAW_DIR / 'cross_appointments.html').resolve()} ({len(cross_names)} names)")
    print(f"Saved profile HTML pages: {PROFILE_RAW_DIR.resolve()} ({len(profile_urls)} files targeted)")
    print(f"Wrote faculty-group membership CSV: {MEMBERSHIP_CSV.resolve()} ({len(membership_rows)} rows)")
    print(f"Wrote faculty roster CSV: {ROSTER_CSV.resolve()} ({len(roster_rows)} rows)")
    print(f"Wrote cross-appointments reference CSV: {CROSS_REFERENCE_CSV.resolve()} ({len(cross_reference_rows)} rows)")
    print(f"Wrote group summary CSV: {GROUP_SUMMARY_CSV.resolve()} ({len(summary_rows)} groups)")


if __name__ == "__main__":
    main()
