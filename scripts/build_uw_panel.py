#!/usr/bin/env python3
"""University-wide salary panel for professorial faculty, linked to the public UW faculty roster.

Usage:
  python3 scripts/build_uw_panel.py --disclosures DIR

Inputs:
- DIR/<year>.html  public salary disclosure pages, 2011-2025 (see build_disclosure_title_panels.py)
- data/private/uw_roster.csv  (from build_uw_roster.py)

Steps:
1. Parse every disclosure year; keep rows with a professorial or teaching-stream title.
2. Key people by normalized surname + first given name. A key shared by two different people in
   the same year (two rows) is ambiguous and dropped for all years.
3. Link roster entries to panel keys (nickname-aware). Each person gets:
   - units: every unit whose faculty listing includes them;
   - home unit: the unit whose listing gives a plain title (no other unit named in the position);
     if several, the unit whose profile states the cross-appointment *with* another unit;
     unresolved cases are flagged;
   - cross-appointed (listing): listed by two or more units;
   - cross-appointed (profile): their profile text states a cross- or joint appointment.

Outputs (gitignored, names):
- data/private/uw_people.csv        one row per linked person: key, home unit, flags, units
- data/private/uw_panel_long.csv    key, year, salary, title, rank
"""

from __future__ import annotations

import argparse
import importlib.util
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "data" / "private" / "uw_roster.csv"
OUT_PEOPLE = ROOT / "data" / "private" / "uw_people.csv"
OUT_PANEL = ROOT / "data" / "private" / "uw_panel_long.csv"

_spec = importlib.util.spec_from_file_location("tp", ROOT / "scripts" / "build_disclosure_title_panels.py")
tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tp)

ACADEMIC = {"assistant", "associate", "full", "teaching_assistant", "teaching_associate", "teaching_full", "lecturer"}
UNIT_WORDS = re.compile(r"\b(?:School|Department|Faculty|Engineering|Science|Studies|Mathematics|Pharmacy|Planning|"
                        r"Psychology|Biology|Chemistry|Physics|Economics|Statistics|Kinesiology|Health|Optometry|"
                        r"Architecture|Geography|Computer|Applied|Management|Systems|Philosophy|History|English)\b")


def key_of(surname: str, given: str) -> tuple[str, str]:
    return tp.norm(surname), tp.first_token(given)


def build_panel(disc_dir: Path) -> pd.DataFrame:
    disc = tp.load_disclosures(disc_dir)
    rows = []
    for y, recs in disc.items():
        for d in recs:
            rank = tp.title_rank(d["title"])
            if rank not in ACADEMIC:
                continue
            k = key_of(d["surname"], d["given"])
            rows.append({"key": "|".join(k), "year": y, "salary": d["salary"], "title": d["title"], "rank": rank})
    df = pd.DataFrame(rows)
    dup = df.groupby(["key", "year"]).size()
    ambiguous = set(dup[dup > 1].index.get_level_values(0))
    print(f"Disclosure rows with academic titles: {len(df)}; ambiguous keys dropped: {len(ambiguous)}")
    return df[~df["key"].isin(ambiguous)].copy()


def split_name(display: str) -> tuple[str, str]:
    parts = tp.norm(display.replace(" - Profile", "")).split()
    return parts[-1] if parts else "", " ".join(parts[:-1])


def link_roster(panel_keys: set[str]) -> pd.DataFrame:
    roster = pd.read_csv(ROSTER).fillna("")
    linked = []
    for r in roster.itertuples():
        parts = tp.norm(r.name).split()
        if len(parts) < 2:
            continue
        given = " ".join(parts[:-1])
        found = None
        for k in (1, 2, 3):  # surname may be one to three tokens
            sur = " ".join(parts[-k:])
            g = " ".join(parts[:-k]) or given
            cand = "|".join((sur, tp.first_token(g)))
            if cand in panel_keys:
                found = cand
                break
        linked.append({**r._asdict(), "key": found})
    return pd.DataFrame(linked)


def resolve_people(linked: pd.DataFrame) -> pd.DataFrame:
    out = []
    for key, g in linked[linked["key"].notna()].groupby("key"):
        units = sorted(set(g["unit"]))
        plain = sorted(set(g.loc[~g["position"].str.contains(",|\\|", regex=True) |
                                 ~g["position"].apply(lambda p: bool(UNIT_WORDS.search(p.split(",", 1)[-1] if "," in p else ""))),
                                 "unit"]))
        xa_text = " || ".join(sorted(set(t for t in g["xa_text"] if t)))
        home, how = None, ""
        if len(units) == 1:
            home, how = units[0], "single listing"
        elif len(plain) == 1:
            home, how = plain[0], "plain title in one listing"
        else:
            stated = sorted(set(g.loc[g["xa_text"].str.contains(r"cross|joint", case=False), "unit"]))
            if len(stated) == 1:
                home, how = stated[0], "profile states cross-appointment"
            else:
                home, how = None, "unresolved"
        out.append({
            "key": key, "name": g["name"].iloc[0], "home_unit": home, "home_rule": how,
            "home_faculty": g.loc[g["unit"] == home, "faculty"].iloc[0] if home else "",
            "n_units": len(units), "units": "; ".join(units),
            "xa_listing": int(len(units) >= 2), "xa_profile": int(bool(xa_text)),
            "xa_text": xa_text[:500],
        })
    return pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--disclosures", type=Path, required=True)
    args = ap.parse_args()
    panel = build_panel(args.disclosures)
    linked = link_roster(set(panel["key"]))
    print(f"Roster listings: {len(linked)}; linked to a disclosure key: {linked['key'].notna().sum()}")
    people = resolve_people(linked)
    keep = set(people["key"])
    panel = panel[panel["key"].isin(keep)]
    OUT_PEOPLE.parent.mkdir(parents=True, exist_ok=True)
    people.to_csv(OUT_PEOPLE, index=False)
    panel.to_csv(OUT_PANEL, index=False)
    print(f"People linked: {len(people)} (home unresolved: {(people['home_rule'] == 'unresolved').sum()}); "
          f"listed by 2+ units: {people['xa_listing'].sum()}; profile states cross/joint: {people['xa_profile'].sum()}")
    print(f"Wrote {OUT_PEOPLE.relative_to(ROOT)} and {OUT_PANEL.relative_to(ROOT)} ({len(panel)} person-years)")


if __name__ == "__main__":
    main()
