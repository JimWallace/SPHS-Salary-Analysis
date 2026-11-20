"""Confirmatory analysis: add the 2022 and 2023 promotion cohorts.

Descriptive only. The title, name and cohort rules come from scripts/promotion_cohort.py
and scripts/build_promotion_pool.py, so group (a) uses the same code as the main report.
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import promotion_cohort as pc  # noqa: E402
from build_promotion_pool import find_one, quartile_check, roster_match  # noqa: E402

GROUPS = {"a": (2024, 2025), "b": (2023, 2024, 2025), "c": (2022, 2023, 2024, 2025)}
FINAL_YEAR = 2025


@dataclass(frozen=True)
class Member:
    cohort: int        # year of the later list (the promotion year)
    prev: pc.Record    # Associate Professor record, cohort - 1
    curr: pc.Record    # Professor record, cohort year


def cohort_members(prev: list[pc.Record], curr: list[pc.Record], year: int) -> tuple[list[Member], list[dict]]:
    """Research-stream main-campus Associate -> Professor changes between two consecutive lists.

    Uses the main report's build_cohorts, so the title, college, rank and name rules are the same.
    Returns the members and the rows for the manual review file.
    """
    result = pc.build_cohorts(prev, curr)
    members = [Member(year, a, b) for a, b in result.cohorts["research"]]
    review = [{"cohort": year, **row} for row in result.review]
    return members, review


def assign_cohorts(lists: dict[int, list[pc.Record]], years: tuple[int, ...]) -> tuple[list[Member], list[dict]]:
    """Cohorts for each year in years. lists must hold that year and the year before."""
    members, review = [], []
    for year in years:
        m, r = cohort_members(lists[year - 1], lists[year], year)
        members += m
        review += r
    return members, review


def retained(member: Member, final: list[pc.Record]) -> pc.Record | None:
    """The member's record in the final list if they are still a main-campus Professor, else None."""
    record = find_one(pc.index_by_key(final), member.curr)
    if record and record.cls.rank == "Professor" and pc.is_main_campus_regular(record.cls):
        return record
    return None


def quartiles(values: list[float]) -> tuple[float, float, float]:
    """Q1, median, Q3 by the inclusive method (R quantile type = 7)."""
    q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return q1, median, q3


def rank_and_percentile(values: list[float], mine: float) -> tuple[int, float]:
    """Rank (1 = highest; ties share the better rank) and percentile.

    values includes mine. Percentile = share of the other members with a strictly lower value.
    """
    rank = 1 + sum(v > mine for v in values)
    below = sum(v < mine for v in values)
    return rank, 100.0 * below / (len(values) - 1)


def scale_factor(cohort: int, increases: dict[str, float | None], final: int = FINAL_YEAR) -> float:
    """Compounded general scale increases from cohort + 1 to final. Refuses missing values."""
    factor = 1.0
    for year in range(cohort + 1, final + 1):
        value = increases.get(str(year))
        if value is None:
            raise ValueError(f"Scale increase for {year} is not set in config.yml.")
        factor *= 1.0 + value
    return factor


def scale_increases_complete(increases: dict[str, float | None], first_cohort: int, final: int = FINAL_YEAR) -> bool:
    return all(increases.get(str(y)) is not None for y in range(first_cohort + 1, final + 1))


def lump_sum_flags(history: dict[int, float], promotion_year: int, threshold: float) -> list[tuple[int, float]]:
    """Year-over-year increases above threshold, except in the promotion year and the year after.

    history maps year to salary paid. Returns (year, change) pairs; change is a fraction.
    """
    flags = []
    years = sorted(history)
    for before, year in zip(years, years[1:]):
        if year != before + 1 or year in (promotion_year, promotion_year + 1):
            continue
        change = history[year] / history[before] - 1.0
        if change > threshold:
            flags.append((year, change))
    return flags


def withheld_statistics(values: list[float]) -> set[str]:
    """Quartiles that equal one person's salary (whole position, or equal neighbours)."""
    names = {"Q1": "lower_quartile", "median": "median", "Q3": "upper_quartile"}
    return {names[k] for k, (_, _, shown) in quartile_check(values).items() if not shown}


def summary_row(values: list[float], mine: float) -> dict[str, float | str]:
    """Statistics for one analysis. A quartile that is one person's salary is withheld."""
    q1, median, q3 = quartiles(values)
    rank, pct = rank_and_percentile(values, mine)
    row: dict[str, float | str] = {
        "n": len(values), "lower_quartile": q1, "median": median, "upper_quartile": q3,
        "my_rank": rank, "my_percentile": pct,
        "my_diff_from_median": mine - median, "my_diff_from_lower_quartile": mine - q1}
    withheld = withheld_statistics(values)
    derived = {"median": "my_diff_from_median", "lower_quartile": "my_diff_from_lower_quartile"}
    for name in withheld:
        row[name] = "withheld"
        if name in derived:
            row[derived[name]] = "withheld"
    return row


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def health_count(records: list[pc.Record], roster: list[list[str]]) -> list[bool]:
    """True for each record whose surname and first given name match the roster."""
    return [roster_match(r, roster) == "yes" for r in records]
