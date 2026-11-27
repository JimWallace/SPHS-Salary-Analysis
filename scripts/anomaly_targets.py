#!/usr/bin/env python3
"""People whose degree and hire details must be collected for the anomaly screen.

Usage:
  python3 scripts/anomaly_targets.py

Targets are (1) Faculty of Health roster members matched to the 2025 disclosure
(data/private/health_roster.csv, from anomaly_health_roster.py) and (2) the 2025 promotion pool
(anomaly_common.pool_members, the 48 of the October report). The subject is in both.

Output (gitignored, names): data/private/anomaly_targets.csv, one row per person with the
disclosure facts a collector needs as hints (titles, first disclosure year).
"""

from __future__ import annotations

import csv

import anomaly_common as ac
import promotion_cohort as pc

ROSTER = ac.PRIVATE / "health_roster.csv"
OUT = ac.PRIVATE / "anomaly_targets.csv"


def main() -> None:
    targets: dict[str, dict[str, str]] = {}
    by_name = {(r.surname, r.given): r for r in ac.year_records(2025)}

    with ROSTER.open(encoding="utf-8") as f:
        roster = [r for r in csv.DictReader(f) if r["match_2025"] == "unique"]
    for row in roster:
        rec = by_name[(row["disc_surname"], row["disc_given"])]
        pid = ac.person_id(rec)
        targets[pid] = {"person_id": pid, "rec": rec, "in_health": "1", "in_pool": "0", "pool_year": "",
                        "unit": row["unit"], "display_name": row["name"], "listed_position": row["position"],
                        "profile_url": row["profile_url"], "also_listed_by": row["also_listed_by"],
                        "match_how": row["match_how"]}
    for rec, pyear in ac.pool_members(2025):
        pid = ac.person_id(rec)
        t = targets.setdefault(pid, {"person_id": pid, "rec": rec, "in_health": "0", "unit": "",
                                     "display_name": f"{rec.given.title()} {rec.surname.title()}",
                                     "listed_position": "", "profile_url": "", "also_listed_by": "",
                                     "match_how": "pool"})
        t["in_pool"], t["pool_year"] = "1", str(pyear)

    rows = []
    for pid, t in sorted(targets.items(), key=lambda kv: (kv[1]["in_health"] != "1", kv[0])):
        rec = t.pop("rec")
        hist = ac.history(rec)
        years = sorted(hist)
        first = years[0]
        t.update({
            "disc_surname": rec.surname, "disc_given": rec.given,
            "is_subject": "1" if rec.key == pc.SUBJECT else "0",
            "title_2025": rec.title, "title_2024": hist[2024].title if 2024 in hist else "",
            "first_disclosure_year": str(first), "first_disclosure_title": hist[first].title,
            "disclosure_years": ";".join(map(str, years)),
        })
        rows.append(t)
    fields = ["person_id", "is_subject", "in_health", "in_pool", "pool_year", "unit", "display_name",
              "disc_surname", "disc_given", "listed_position", "profile_url", "also_listed_by", "match_how",
              "title_2025", "title_2024", "first_disclosure_year", "first_disclosure_title", "disclosure_years"]
    pc.write_csv(OUT, rows, fields)
    print(f"Wrote {OUT.relative_to(ac.ROOT)}: {len(rows)} people "
          f"({sum(r['in_health'] == '1' for r in rows)} Health, {sum(r['in_pool'] == '1' for r in rows)} pool, "
          f"{sum(r['in_health'] == '1' and r['in_pool'] == '1' for r in rows)} both)")


if __name__ == "__main__":
    main()
