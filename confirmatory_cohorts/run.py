#!/usr/bin/env python3
"""Confirmatory analysis: does the result hold with the 2022 and 2023 promotion cohorts?

Usage:
  python3 confirmatory_cohorts/run.py

Reads the archived disclosure lists (data/raw/manifest.csv), the Faculty of Health roster
(data/private/health_roster.csv) and confirmatory_cohorts/config.yml.
Writes confirmatory_cohorts/output/ (no names, no individual salaries) and
confirmatory_cohorts/review/manual_matches.csv (names; gitignored). Descriptive only.
"""

from __future__ import annotations

import csv
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

import yaml

import confirm as cf
from confirm import pc

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
REVIEW = HERE / "review"
YEARS = range(2021, 2026)
EXPECTED_A = {"n": 48, "my_rank": 47, "median": 207_957, "lower_quartile": 189_333}
ANALYSES = ["A", "B-unadjusted", "B-adjusted"]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    config = yaml.safe_load((HERE / "config.yml").read_text(encoding="utf-8"))
    base = float(config["annualized_base_2025"])
    increases = config["scale_increases"] or {}
    threshold = float(config["lump_sum_flag_threshold"])

    lists = {y: pc.load_year(y) for y in YEARS}
    members, review = cf.assign_cohorts(lists, (2022, 2023, 2024, 2025))

    mine = [m for m in members if " ".join(m.prev.key) == config["my_name_normalized"]]
    if len(mine) != 1:
        raise SystemExit(f"Expected one member named {config['my_name_normalized']}, found {len(mine)}.")
    me = mine[0]
    for year, record in ((2024, me.prev), (2025, me.curr)):
        if abs(record.paid - float(config[f"disclosed_{year}"])) > 1:
            raise SystemExit(f"My {year} disclosed salary {record.paid:,.2f} differs from config.yml.")

    # Attrition: earlier cohorts must still be main-campus Professors in 2025.
    final = {}
    attrition = {}
    for m in members:
        if m.cohort == cf.FINAL_YEAR:
            final[id(m)] = m.curr
        else:
            record = cf.retained(m, lists[cf.FINAL_YEAR])
            if record:
                final[id(m)] = record
            else:
                attrition[m.cohort] = attrition.get(m.cohort, 0) + 1

    with (pc.ROOT / "data" / "private" / "health_roster.csv").open(encoding="utf-8") as f:
        roster = [pc.normalize_name_part(r["name"]).split() for r in csv.DictReader(f)]

    summary, health = [], []
    for group, cohorts in cf.GROUPS.items():
        in_group = [m for m in members if m.cohort in cohorts]
        adjusted_ready = cf.scale_increases_complete(increases, min(cohorts))
        for analysis in ANALYSES:
            row = {"group": group, "cohorts": "-".join(map(str, cohorts)), "analysis": analysis}
            if analysis == "B-adjusted" and not adjusted_ready:
                summary.append(row | {"status": "pending: scale increases not set in config.yml"})
                health.append(row | {"status": "pending"})
                continue
            values, records = [], []
            for m in in_group:
                if m is me:
                    values.append(base)
                    records.append(m.curr)
                elif analysis == "A":
                    if id(m) in final:
                        values.append(final[id(m)].paid)
                        records.append(final[id(m)])
                elif analysis == "B-unadjusted":
                    values.append(m.curr.paid)
                    records.append(m.curr)
                else:
                    values.append(m.curr.paid * cf.scale_factor(m.cohort, increases))
                    records.append(m.curr)
            stats = cf.summary_row(values, base)
            status = "ok" if analysis != "A" or group == "a" else "ok; not like-for-like (older cohorts have more years as Professor)"
            withheld = [k for k in ("lower_quartile", "median", "upper_quartile") if stats[k] == "withheld"]
            if withheld:
                status += f"; withheld (equals one person's salary): {', '.join(withheld)}"
            summary.append(row | {k: round(v, 2) if isinstance(v, float) else v for k, v in stats.items()} | {"status": status})
            is_health = cf.health_count(records, roster)
            health_values = [v for v, h in zip(values, is_health) if h]
            rank, _ = cf.rank_and_percentile(health_values, base)
            health.append(row | {"n": len(health_values), "my_rank": rank, "status": "ok"})

    a = next(r for r in summary if r["group"] == "a" and r["analysis"] == "A")
    got = {k: round(a[k]) if isinstance(a[k], float) else a[k] for k in EXPECTED_A}
    if got != EXPECTED_A:
        raise SystemExit(f"Group (a) does not reproduce the main report: expected {EXPECTED_A}, got {got}.")

    # Lump-sum and retroactive payment flags, 2021-2025 (no adjustment).
    indexes = {y: pc.index_by_key(lists[y]) for y in YEARS}
    flags, decreases, in_promotion_year, in_year_after = [], 0, 0, 0
    for i, m in enumerate(sorted(members, key=lambda m: (m.cohort, m.curr.paid)), start=1):
        history = {}
        for y in YEARS:
            record = cf.find_one(indexes[y], m.curr)
            if record:
                history[y] = record.paid
        for year, change in cf.lump_sum_flags(history, m.cohort, threshold):
            flags.append({"person_id": f"P{i:03d}", "cohort": m.cohort, "year": year, "change_pct": round(100 * change, 1)})
        for y, counter in ((m.cohort, "promo"), (m.cohort + 1, "after")):
            if y in history and y - 1 in history and history[y] / history[y - 1] - 1 > threshold:
                if counter == "promo":
                    in_promotion_year += 1
                else:
                    in_year_after += 1
        years = sorted(history)
        decreases += sum(1 for b, y in zip(years, years[1:]) if y == b + 1 and history[y] / history[b] - 1 < -threshold)

    OUT.mkdir(parents=True, exist_ok=True)
    stat_fields = ["n", "lower_quartile", "median", "upper_quartile", "my_rank", "my_percentile",
                   "my_diff_from_median", "my_diff_from_lower_quartile"]
    write_csv(OUT / "summary_table.csv", summary, ["group", "cohorts", "analysis"] + stat_fields + ["status"])
    write_csv(OUT / "health_subset.csv", health, ["group", "cohorts", "analysis", "n", "my_rank", "status"])
    write_csv(OUT / "lump_sum_flags.csv", flags, ["person_id", "cohort", "year", "change_pct"])
    write_csv(REVIEW / "manual_matches.csv", review,
              ["cohort", "reason", "name_prev", "title_prev", "paid_prev", "name_curr", "title_curr", "paid_curr", "match_score"])

    counts = {y: sum(m.cohort == y for m in members) for y in (2022, 2023, 2024, 2025)}
    admin = {y: sum(r["cohort"] == y and r["reason"].startswith("admin") for r in review) for y in counts}
    nonexact = {y: sum(r["cohort"] == y and not r["reason"].startswith("admin") for r in review) for y in counts}
    flag_years = {y: sum(f["year"] == y for f in flags) for y in range(2022, 2026)}
    manifest = list(csv.DictReader(pc.MANIFEST.open(encoding="utf-8")))
    write_notes(counts, attrition, admin, nonexact, flag_years, len(flags), decreases, manifest, threshold,
                (in_promotion_year, in_year_after))
    write_result(summary, health)
    write_environment(manifest)
    print((OUT / "RESULT.md").read_text(encoding="utf-8"))


def write_notes(counts, attrition, admin, nonexact, flag_years, n_flags, decreases, manifest, threshold, promo) -> None:
    lines = ["# Data notes", "", "## Sources", "",
             "University of Waterloo salary disclosure lists, archived once under `data/raw/` "
             "(raw HTML gitignored). New for this analysis: 2021 and 2022.", "",
             "| Year | URL | Retrieved | SHA-256 |", "|---|---|---|---|"]
    lines += [f"| {r['year']} | {r['url']} | {r['retrieved']} | `{r['sha256']}` |" for r in manifest]
    lines += ["", "Format check: every list has one table with the same five columns (Surname, Given name, "
              "Position title, Salary paid, Taxable benefits), five cells in every row, and no missing salaries. "
              "Difference: the 2021-2023 lists have no \"Teaching Stream\" titles; teaching-stream faculty were "
              "titled \"Lecturer\" until 2023. Those titles have no academic rank, so the research-stream rule is "
              "the same in every year. One new title form, \"Professor Emeritus\" (2022), has no rank and is not used.", "",
              "## Cohorts", "", "| Cohort | Members | Administrative-title cases | Other non-exact matches | Not a main-campus Professor in 2025 |",
              "|---|---|---|---|---|"]
    lines += [f"| {y} | {counts[y]} | {admin[y]} | {nonexact[y]} | {attrition.get(y, 0) if y < cf.FINAL_YEAR else 'n/a'} |" for y in counts]
    lines += ["", "- Administrative-title cases: an Associate Professor in the year before whose title in the cohort "
              "year (or the year before) has an administrative role. They are not included or excluded automatically; "
              "they are in `review/manual_matches.csv`.",
              "- Other non-exact matches (names not unique, matched by middle initial, fuzzy suggestions, stream changes) "
              "are in the same file. Fuzzy suggestions are never added to a cohort.",
              "- Attrition: these members are excluded from Analysis A (2025 salary). Analysis B (salary in the "
              "promotion year) keeps them.", "",
              "## Lump-sum and retroactive payment flags", "",
              f"Year-over-year increases above {threshold:.0%} in disclosed salary, 2021-2025, for every cohort member, "
              "excluding the promotion year and the year after. No figure is adjusted. "
              f"Total flags: {n_flags}. List (anonymous IDs, no salaries): `output/lump_sum_flags.csv`.", "",
              "| Year | Flags |", "|---|---|"]
    lines += [f"| {y} | {n} |" for y, n in flag_years.items()]
    lines += ["", f"Not flagged by this rule: {promo[0]} increases above {threshold:.0%} in a member's promotion year "
              f"and {promo[1]} in the year after. Analysis B uses the promotion-year salary, so these figures can include "
              "lump sums. They raise colleagues' values, so they can only make my position look worse, not better.",
              "", f"For information: {decreases} year-over-year decreases larger than {threshold:.0%} "
              "(possible leaves or sabbaticals).", "",
              "## Faculty of Health subset", "",
              "A member counts only if surname and first given name both match the current public unit listings "
              "(SPHS, Kinesiology and Health Sciences, Recreation and Leisure Studies). The listings show current "
              "faculty, so people who left are missed. This matters more for the older cohorts."]
    (OUT / "data_notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_result(summary, health) -> None:
    def get(rows, group, analysis):
        return next(r for r in rows if r["group"] == group and r["analysis"] == analysis)

    lines = ["# Result", ""]
    rows = []
    for analysis in ANALYSES:
        for group in cf.GROUPS:
            r = get(summary, group, analysis)
            h = get(health, group, analysis)
            if r["status"].startswith("pending"):
                rows.append(f"| {analysis} | {group} ({r['cohorts']}) | pending | | | |")
            else:
                diff = r["my_diff_from_median"]
                diff = f"{diff:+,.0f}" if isinstance(diff, float) else diff
                rows.append(f"| {analysis} | {group} ({r['cohorts']}) | {r['my_rank']} of {r['n']} | {r['my_percentile']:.0f} "
                            f"| {diff} | {h['my_rank']} of {h['n']} |")
    worst = max((r for r in summary if not r["status"].startswith("pending")), key=lambda r: r["my_percentile"])
    holds = all(r["my_percentile"] <= 10 for r in summary if not r["status"].startswith("pending"))
    c_a, c_b = get(summary, "c", "A"), get(summary, "c", "B-unadjusted")
    if holds:
        lines += ["The result holds in every analysis. Test used: my percentile is 10 or lower in every analysis "
                  "that ran.", "",
                  f"Sentence for the report: \"The result does not change when the 2022 and 2023 cohorts are added: "
                  f"my salary is {cf.ordinal(c_b['my_rank'])} of {c_b['n']} at the year of promotion, and "
                  f"{cf.ordinal(c_a['my_rank'])} of {c_a['n']} in 2025.\""]
    else:
        lines += [f"The result does not hold in every analysis. The weakest position is analysis {worst['analysis']}, "
                  f"group {worst['group']}: rank {worst['my_rank']} of {worst['n']} ({worst['my_percentile']:.0f}th percentile)."]
    lines += ["", "| Analysis | Group | My rank (1 = highest) | Percentile | Difference from median | Faculty of Health rank |",
              "|---|---|---|---|---|---|"] + rows
    lines += ["", "Analysis A uses 2025 salaries. Older cohorts have had more years of increases as Professors, "
              "so A is not like-for-like for groups b and c. Analysis B uses each person's salary in their promotion "
              "year; unadjusted dollars are conservative because older salaries are lower. "
              "Analysis B-adjusted is pending until the scale increases are set in `config.yml`.",
              "", "Descriptive only. No regressions or statistical tests."]
    (OUT / "RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_environment(manifest) -> None:
    """The Python equivalent of R sessionInfo()."""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip()
    code = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            for p in (HERE / "confirm.py", HERE / "run.py", pc.ROOT / "scripts" / "promotion_cohort.py",
                      pc.ROOT / "scripts" / "build_promotion_pool.py")}
    lines = [f"python: {sys.version.split()[0]}", f"platform: {platform.platform()}", f"pyyaml: {yaml.__version__}",
             f"git commit: {commit}"]
    lines += [f"sha256[:16] {name}: {digest}" for name, digest in code.items()]
    lines += [f"disclosure {r['year']}: {r['sha256']}" for r in manifest]
    (OUT / "session_info.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
