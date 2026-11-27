"""Shared helpers for the salary anomaly screen (scripts/anomaly_*.py).

Disclosure parsing, name normalization and title classification come from promotion_cohort.py;
this module adds a multi-year person history and the 2025 promotion pool membership
(the same rule as build_promotion_pool.py).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

import promotion_cohort as pc

ROOT = pc.ROOT
YEARS = range(2011, 2026)
PRIVATE = ROOT / "data" / "private"
OUT_DIR = ROOT / "analysis_output"


@lru_cache(maxsize=None)
def year_records(year: int) -> tuple[pc.Record, ...]:
    return tuple(pc.load_year(year))


@lru_cache(maxsize=None)
def year_index(year: int) -> dict:
    return pc.index_by_key(list(year_records(year)))


def find_in_year(record: pc.Record, year: int) -> pc.Record | None:
    """The one record in `year` for this person: exact normalized key, then full name with initials."""
    matches = year_index(year).get(record.key, [])
    if len(matches) > 1:
        matches = [r for r in matches if r.full_key == record.full_key]
    return matches[0] if len(matches) == 1 else None


def history(record: pc.Record) -> dict[int, pc.Record]:
    out = {}
    for y in YEARS:
        r = find_in_year(record, y)
        if r is not None:
            out[y] = r
    return out


def person_id(record: pc.Record) -> str:
    """Stable pseudonymous id from the disclosed name (no name in the id itself)."""
    s, g = record.full_key
    return "P" + hashlib.sha256(f"{s}|{g}".encode()).hexdigest()[:8]


def pool_members(year: int = 2025) -> list[tuple[pc.Record, int]]:
    """(record in `year`, promotion year) for the research-stream Associate->Professor promotions
    in year-1 and year, as in build_promotion_pool.py. Includes the subject."""
    y0, y1, y2 = (list(year_records(y)) for y in (year - 2, year - 1, year))
    earlier = pc.build_cohorts(y0, y1).cohorts["research"]
    current = pc.build_cohorts(y1, y2).cohorts["research"]
    out = []
    for _, b in earlier:
        c = find_in_year(b, year)
        if c and c.cls.rank == "Professor" and pc.is_main_campus_regular(c.cls):
            out.append((c, year - 1))
    for _, b in current:
        out.append((b, year))
    return out
