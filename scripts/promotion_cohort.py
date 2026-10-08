#!/usr/bin/env python3
"""University-wide promotion cohort (Associate -> Professor) from two UW salary disclosure lists.

Usage:
  python3 scripts/promotion_cohort.py --year 2025     # compares 2024 with 2025

Reads the archived pages listed in data/raw/manifest.csv (see fetch_salary_disclosure.py).
Outputs:
- data/private/cohort_named.csv     (gitignored: names)
- data/review/matches_to_check.csv  (gitignored: names)
- output/cohort_summary.md          (no names except Wallace)
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
MANIFEST = RAW_DIR / "manifest.csv"
OUT_COHORT = ROOT / "data" / "private" / "cohort_named.csv"
OUT_REVIEW = ROOT / "data" / "review" / "matches_to_check.csv"
OUT_SUMMARY = ROOT / "output" / "cohort_summary.md"
# Names that must be in the cohort (columns: year, surname, given). Gitignored: the repository is public.
REQUIRED_NAMES = ROOT / "data" / "private" / "required_names.csv"

SUBJECT = ("WALLACE", "JAMES")

# Year-specific checks on the subject. Years without an entry skip them.
VALIDATION = {
    2025: {
        "subject_paid": 143_600.0,
        "subject_paid_tolerance": 500.0,
        "subject_annualized_base": 162_628.83,
    }
}

FUZZY_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Title classification
# ---------------------------------------------------------------------------

COLLEGES = ("Renison", "Conrad Grebel", "St. Jerome's", "United College")
RANK_PART = re.compile(r"^(?:(Assistant|Associate) )?Professor$")
NON_REGULAR_PART = re.compile(r"^(?:Research|Clinical|Adjunct|Visiting) (?:(?:Assistant|Associate) )?Professor$")
ADMIN_WORD = re.compile(r"\b(?:Dean|Chair|Director|Vice-President|AVP|Provost|President|Principal|Head)\b")
TEACHING_STREAM = "Teaching Stream"


@dataclass(frozen=True)
class TitleClass:
    rank: str  # "Assistant", "Associate", "Professor" or "other"
    stream: str  # "research" or "teaching"
    flags: frozenset[str]  # subset of {"college", "nonregular", "admin"}


def classify_title(title: str) -> TitleClass:
    """Map a disclosure position title to rank, stream and flags.

    The title is split on commas and each part must match a rank pattern exactly,
    so "Research Associate Professor" is never read as "Associate Professor".
    """
    title = title.replace("’", "'")
    parts = [p.strip() for p in title.split(",") if p.strip()]
    flags: set[str] = set()

    if any(college in title for college in COLLEGES):
        flags.add("college")
    if any(NON_REGULAR_PART.match(p) for p in parts):
        flags.add("nonregular")

    stream = "teaching" if TEACHING_STREAM in parts else "research"
    rank = "other"
    rank_index = None
    for i, part in enumerate(parts):
        m = RANK_PART.match(part)
        if m:
            rank = m.group(1) or "Professor"
            rank_index = i
            break

    if "nonregular" in flags:
        rank = "other"

    # Parts other than the rank, the stream and the college name are administrative roles.
    other_parts = [
        p for i, p in enumerate(parts)
        if i != rank_index and p != TEACHING_STREAM and not any(c in p for c in COLLEGES)
    ]
    if rank_index is not None and other_parts:
        flags.add("admin")
    if rank == "other" and "nonregular" not in flags and ADMIN_WORD.search(title):
        flags.add("admin")

    return TitleClass(rank=rank, stream=stream, flags=frozenset(flags))


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

def normalize_name_part(text: str) -> str:
    """Upper case, remove accents and punctuation; hyphens, periods and spaces become single spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    upper = no_accents.upper().replace("-", " ").replace(".", " ")
    letters = re.sub(r"[^A-Z ]", "", upper)
    return " ".join(letters.split())


def normalize_given(text: str) -> str:
    """Normalize a given name and remove middle initials (single letters after the first word)."""
    words = normalize_name_part(text).split()
    if not words:
        return ""
    return " ".join([words[0]] + [w for w in words[1:] if len(w) > 1])


def name_key(surname: str, given: str) -> tuple[str, str]:
    return normalize_name_part(surname), normalize_given(given)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Record:
    surname: str
    given: str
    title: str
    paid: float
    cls: TitleClass

    @property
    def key(self) -> tuple[str, str]:
        return name_key(self.surname, self.given)

    @property
    def name(self) -> str:
        return f"{self.surname}, {self.given}"


def clean_text(fragment: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def parse_money(text: str) -> float:
    return float(re.sub(r"[^0-9.\-]", "", text))


def parse_disclosure(page_html: str) -> list[Record]:
    records = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, flags=re.IGNORECASE | re.DOTALL):
        cells = [clean_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.IGNORECASE | re.DOTALL)]
        if len(cells) != 5 or cells[0] == "Surname":
            continue
        surname, given, title, paid, _benefits = cells
        records.append(Record(surname, given, title, parse_money(paid), classify_title(title)))
    return records


def load_year(year: int) -> list[Record]:
    with MANIFEST.open(encoding="utf-8") as f:
        entries = [r for r in csv.DictReader(f) if int(r["year"]) == year]
    if not entries:
        raise SystemExit(f"No {year} entry in {MANIFEST.relative_to(ROOT)}. Run scripts/fetch_salary_disclosure.py {year}.")
    entry = entries[0]
    content = (RAW_DIR / entry["file"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise SystemExit(f"SHA-256 mismatch for data/raw/{entry['file']}.")
    return parse_disclosure(content.decode("utf-8"))


# ---------------------------------------------------------------------------
# Cohort
# ---------------------------------------------------------------------------

def is_main_campus_regular(cls: TitleClass) -> bool:
    return not cls.flags & {"college", "nonregular"}


def flags_text(*classes: TitleClass) -> str:
    return ";".join(sorted(set().union(*(c.flags for c in classes))))


def index_by_key(records: list[Record]) -> dict[tuple[str, str], list[Record]]:
    index: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for r in records:
        index[r.key].append(r)
    return index


def fuzzy_score(a: Record, b: Record) -> float:
    (sa, ga), (sb, gb) = a.key, b.key
    if sa == sb and ga and gb and ga.split()[0] == gb.split()[0]:
        return 1.0
    return difflib.SequenceMatcher(None, f"{sa} {ga}", f"{sb} {gb}").ratio()


def review_row(reason: str, a: Record | None, b: Record | None, score: float | None = None) -> dict[str, str]:
    return {
        "reason": reason,
        "name_prev": a.name if a else "",
        "title_prev": a.title if a else "",
        "paid_prev": f"{a.paid:.2f}" if a else "",
        "name_curr": b.name if b else "",
        "title_curr": b.title if b else "",
        "paid_curr": f"{b.paid:.2f}" if b else "",
        "match_score": f"{score:.3f}" if score is not None else "",
    }


@dataclass
class CohortResult:
    cohorts: dict[str, list[tuple[Record, Record]]]
    review: list[dict[str, str]]
    counts: list[tuple[str, int]]


def build_cohorts(prev: list[Record], curr: list[Record]) -> CohortResult:
    counts: list[tuple[str, int]] = [("prev-year rows", len(prev))]
    pool = [r for r in prev if "college" not in r.cls.flags]
    counts.append(("excluded: affiliated college", len(prev) - len(pool)))
    n = len(pool)
    pool = [r for r in pool if "nonregular" not in r.cls.flags]
    counts.append(("excluded: non-regular rank (Research/Clinical/Adjunct/Visiting)", n - len(pool)))
    n = len(pool)
    pool = [r for r in pool if r.cls.rank == "Associate"]
    counts.append(("excluded: rank not Associate in prev year", n - len(pool)))

    prev_index, curr_index = index_by_key(prev), index_by_key(curr)
    matched_curr: set[int] = set()
    cohorts: dict[str, list[tuple[Record, Record]]] = {"research": [], "teaching": []}
    review: list[dict[str, str]] = []
    unmatched: list[Record] = []
    step = Counter()

    for stream in ("research", "teaching"):
        counts.append((f"[{stream}] Associate pool, main campus", sum(r.cls.stream == stream for r in pool)))

    for a in pool:
        stream = a.cls.stream
        same_prev, same_curr = prev_index[a.key], curr_index.get(a.key, [])
        if len(same_prev) > 1 or len(same_curr) > 1:
            step[stream, "excluded: name not unique in a year"] += 1
            for b in same_curr or [None]:
                review.append(review_row("ambiguous exact name (not unique in a year)", a, b))
            continue
        if not same_curr:
            unmatched.append(a)
            step[stream, "excluded: no exact name match in curr year"] += 1
            continue
        b = same_curr[0]
        matched_curr.add(id(b))
        if "admin" in a.cls.flags | b.cls.flags:
            review.append(review_row(f"admin title ({flags_text(a.cls, b.cls)})", a, b))
        if not is_main_campus_regular(b.cls):
            step[stream, "excluded: curr title is college or non-regular"] += 1
        elif b.cls.rank != "Professor":
            step[stream, "excluded: curr rank not Professor"] += 1
        elif b.cls.stream != stream:
            step[stream, "excluded: stream changed"] += 1
            review.append(review_row("stream changed between years", a, b))
        else:
            cohorts[stream].append((a, b))

    # Fuzzy pass: suggestions only, never added to the cohort.
    candidates = [b for b in curr if id(b) not in matched_curr]
    for a in unmatched:
        for b in candidates:
            score = fuzzy_score(a, b)
            if score >= FUZZY_THRESHOLD:
                review.append(review_row("fuzzy match (not exact)", a, b, score))

    for stream in ("research", "teaching"):
        for (s, label), value in sorted(step.items()):
            if s == stream:
                counts.append((f"[{stream}] {label}", value))
        counts.append((f"[{stream}] cohort size", len(cohorts[stream])))
    return CohortResult(cohorts, review, counts)


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def five_numbers(values: list[float]) -> tuple[float, float, float, float, float]:
    q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return min(values), q1, median, q3, max(values)


def position(values: list[float], value: float) -> tuple[int, float]:
    """Rank (1 = highest) and percentile (share of the other members with a lower value)."""
    rank = 1 + sum(v > value for v in values)
    below = sum(v < value for v in values)
    return rank, 100.0 * below / (len(values) - 1)


def money(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def stats_table(columns: list[tuple[str, list[float]]]) -> list[str]:
    lines = ["| Statistic | " + " | ".join(c for c, _ in columns) + " |", "|---" * (len(columns) + 1) + "|"]
    labels = ["Minimum", "Lower quartile", "Median", "Upper quartile", "Maximum"]
    stats = [five_numbers(values) for _, values in columns]
    for i, label in enumerate(labels):
        lines.append(f"| {label} | " + " | ".join(money(s[i]) for s in stats) + " |")
    return lines


def subject_table(columns: list[tuple[str, list[float], float]]) -> list[str]:
    lines = ["| Measure | Wallace | Rank (1 = highest) | Percentile |", "|---|---|---|---|"]
    n = len(columns[0][1])
    for label, values, value in columns:
        rank, pct = position(values, value)
        lines.append(f"| {label} | {money(value)} | {rank} of {n} | {pct:.0f} |")
    return lines


def write_summary(prev_year: int, year: int, result: CohortResult, check: dict | None) -> list[str]:
    pairs = result.cohorts["research"]
    p_prev = [a.paid for a, _ in pairs]
    p_curr = [b.paid for _, b in pairs]
    change = [b.paid - a.paid for a, b in pairs]
    out = [
        f"# Promotion cohort: Associate Professor ({prev_year}) to Professor ({year})",
        "",
        f"Source: University of Waterloo salary disclosure lists for {prev_year} and {year}, "
        "archived under `data/raw/` (see `data/raw/manifest.csv` for retrieval dates and SHA-256 hashes).",
        "",
        f"Cohort: research-stream faculty on the main campus whose title was \"Associate Professor\" in {prev_year} "
        f"and \"Professor\" in {year}, matched by exact normalized name. Affiliated colleges, non-regular ranks "
        "(Research, Clinical, Adjunct, Visiting) and teaching-stream titles are not in this cohort. "
        "Fuzzy name matches are not in the cohort; they are in the manual-review file.",
        "",
        "## Read this first",
        "",
        "- The comparison is descriptive, not causal.",
        f"- The {year} figures blend about six months at each rank (promotions take effect on July 1).",
        "- \"Paid\" is the salary paid in the calendar year. Comparator figures can include sabbaticals, "
        "stipends and other payments.",
    ]
    if check:
        out.append(
            f"- Wallace's {year} paid figure includes about eight months of sabbatical at 85% pay. "
            "The last section uses his annualized base salary instead."
        )
    out += [
        "- Quartiles use the inclusive method (Python `statistics.quantiles`, `method=\"inclusive\"`).",
        "- Percentile = percentage of the other cohort members with a lower value.",
        "",
        "## Filter counts",
        "",
        "| Step | Count |",
        "|---|---|",
    ]
    out += [f"| {label} | {value} |" for label, value in result.counts]
    out += ["", f"## Research-stream cohort (n = {len(pairs)})", ""]
    out += stats_table([(f"{prev_year} paid", p_prev), (f"{year} paid", p_curr), (f"Change ({year} - {prev_year})", change)])

    subject = [(a, b) for a, b in pairs if a.key == SUBJECT]
    if subject:
        a, b = subject[0]
        out += ["", "### Wallace's position", ""]
        out += subject_table([
            (f"{prev_year} paid", p_prev, a.paid),
            (f"{year} paid", p_curr, b.paid),
            (f"Change ({year} - {prev_year})", change, b.paid - a.paid),
        ])
        base = check.get("subject_annualized_base") if check else None
        if base:
            alt_curr = [base if y is b else y.paid for _, y in pairs]
            alt_change = [(base if y is b else y.paid) - x.paid for x, y in pairs]
            out += [
                "",
                f"### {year} figures with Wallace's annualized base (${base:,.2f}) in place of his paid figure",
                "",
            ]
            out += stats_table([(f"{year} paid", alt_curr), (f"Change ({year} - {prev_year})", alt_change)])
            out += [""]
            out += subject_table([
                (f"{year} paid", alt_curr, base),
                (f"Change ({year} - {prev_year})", alt_change, base - a.paid),
            ])

    teaching = result.cohorts["teaching"]
    out += ["", f"## Teaching-stream cohort (n = {len(teaching)})", ""]
    if len(teaching) >= 2:
        out += stats_table([
            (f"{prev_year} paid", [a.paid for a, _ in teaching]),
            (f"{year} paid", [b.paid for _, b in teaching]),
            (f"Change ({year} - {prev_year})", [b.paid - a.paid for a, b in teaching]),
        ])
    else:
        out.append("Too few members for summary statistics.")

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text("\n".join(out) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def required_names(year: int) -> list[tuple[str, str]]:
    if not REQUIRED_NAMES.exists():
        return []
    with REQUIRED_NAMES.open(encoding="utf-8") as f:
        return [name_key(r["surname"], r["given"]) for r in csv.DictReader(f) if int(r["year"]) == year]


def validate(year: int, result: CohortResult, curr: list[Record], check: dict | None) -> None:
    required = required_names(year)
    if not required:
        print(f"No required names for {year} in {REQUIRED_NAMES.relative_to(ROOT)}; name check skipped.")
    cohort_keys = {a.key for a, _ in result.cohorts["research"]}
    problems = []
    for key in required:
        if key in cohort_keys:
            continue
        rows = [r for r in curr if r.key == key]
        detail = "; ".join(f"{year} title {r.title!r} -> {r.cls}" for r in rows) or f"no exact {year} name match"
        problems.append(f"{key[0]}, {key[1]} is not in the cohort ({detail}).")
    subject = [b for a, b in result.cohorts["research"] if a.key == SUBJECT]
    if check and subject and abs(subject[0].paid - check["subject_paid"]) > check["subject_paid_tolerance"]:
        problems.append(f"Wallace {year} paid is {subject[0].paid:,.2f}, expected about {check['subject_paid']:,.0f}.")
    if problems:
        raise SystemExit("VALIDATION FAILED:\n  " + "\n  ".join(problems))
    print(f"Validation passed: {', '.join(k[0] for k in required) or 'no names'} in the cohort.")
    if subject:
        print(f"Wallace {year} paid = ${subject[0].paid:,.2f}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, required=True, help="promotion year; compared with year - 1")
    args = parser.parse_args()
    year, prev_year = args.year, args.year - 1

    prev, curr = load_year(prev_year), load_year(year)
    result = build_cohorts(prev, curr)

    print(f"Filter counts ({prev_year} -> {year}):")
    for label, value in result.counts:
        print(f"  {label}: {value}")

    check = VALIDATION.get(year)
    validate(year, result, curr, check)

    cohort_rows = []
    for stream in ("research", "teaching"):
        for a, b in result.cohorts[stream]:
            cohort_rows.append({
                "cohort": stream,
                "name": a.name,
                f"title_{prev_year}": a.title,
                f"paid_{prev_year}": f"{a.paid:.2f}",
                f"title_{year}": b.title,
                f"paid_{year}": f"{b.paid:.2f}",
                "change": f"{b.paid - a.paid:.2f}",
                "flags": flags_text(a.cls, b.cls),
                "faculty": "",
            })
    write_csv(OUT_COHORT, cohort_rows, ["cohort", "name", f"title_{prev_year}", f"paid_{prev_year}",
                                        f"title_{year}", f"paid_{year}", "change", "flags", "faculty"])
    write_csv(OUT_REVIEW, result.review, list(review_row("", None, None).keys()))
    write_summary(prev_year, year, result, check)

    print(f"Wrote {OUT_COHORT.relative_to(ROOT)} ({len(cohort_rows)} rows)")
    print(f"Wrote {OUT_REVIEW.relative_to(ROOT)} ({len(result.review)} rows)")
    print(f"Wrote {OUT_SUMMARY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
