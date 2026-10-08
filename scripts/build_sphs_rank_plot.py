#!/usr/bin/env python3
"""SPHS faculty salaries in YEAR, by rank, with Wallace's annualized base.

Usage:
  python3 scripts/build_sphs_rank_plot.py --year 2025

Uses the SPHS faculty list in data/sphs.csv and the archived YEAR disclosure list.
Colleagues are shown at their disclosed salary paid; Wallace at his annualized base.
Each point is one colleague's salary, so all outputs are gitignored:
- data/private/sphs_rank_<year>.csv   (rank_ascending, salary, group, group_code, subject)
- data/private/sphs_rank_<year>.tex   (LaTeX macros for sphs_rank_figure.tex)
"""

from __future__ import annotations

import argparse
import csv

import promotion_cohort as pc
from build_promotion_pool import PRIVATE_DIR, SPHS_LIST, money, write_macros

GROUPS = ["Professor", "Associate", "Assistant", "Teaching"]


def rank_group(cls: pc.TitleClass) -> str | None:
    """Plot group for a disclosed title: teaching stream (any rank) or research-stream rank."""
    if not pc.is_main_campus_regular(cls) or cls.rank == "other":
        return None
    return "Teaching" if cls.stream == "teaching" else cls.rank


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    year = args.year
    base = pc.VALIDATION[year]["subject_annualized_base"]

    index = pc.index_by_key(pc.load_year(year))
    points: list[tuple[float, str, bool]] = [(base, "Professor", True)]
    not_listed = other_title = 0
    with SPHS_LIST.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = pc.name_key(row["Surname"], row["Given name"])
            if key == pc.SUBJECT:
                continue
            matches = index.get(key, [])
            if len(matches) != 1:
                not_listed += 1
                continue
            group = rank_group(matches[0].cls)
            if group is None:
                other_title += 1
                continue
            points.append((matches[0].paid, group, False))

    points.sort(key=lambda p: p[0])
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    with (PRIVATE_DIR / f"sphs_rank_{year}.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank_ascending", "salary", "group", "group_code", "subject"])
        for i, (salary, group, is_subject) in enumerate(points, start=1):
            writer.writerow([i, f"{salary:.2f}", group, GROUPS.index(group) + 1, int(is_subject)])

    others = [p for p in points if not p[2]]
    counts = {g: sum(p[1] == g for p in others) for g in GROUPS}
    above = sum(p[0] > base for p in others)
    macros = {f"SphsCount{g}": str(n) for g, n in counts.items()}
    macros |= {
        "SphsPlotYear": str(year),
        "SphsPlotN": str(len(others)),
        "SphsPlotAbove": str(above),
        "SphsPlotNotListed": str(not_listed + other_title),
        "SphsPlotBase": money(base),
        "SphsPlotBaseRaw": f"{base:.0f}",
        "SphsPlotRank": str(1 + above),
    }
    write_macros(PRIVATE_DIR / f"sphs_rank_{year}.tex", macros, year, "build_sphs_rank_plot.py")
    print(f"SPHS {year}: {len(others)} colleagues ({counts}); {above} paid more than Wallace's base; "
          f"{not_listed} not in the list, {other_title} with other titles")
    print(f"Salary range: ${points[0][0]:,.0f} to ${points[-1][0]:,.0f}")


if __name__ == "__main__":
    main()
