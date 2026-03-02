#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

try:
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "data" / "sphs.csv"
OUT_DIR = ROOT / "analysis_output"
FIG_DIR = ROOT / "figures"


def parse_float(value: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_panel_rows() -> list[dict[str, object]]:
    with INPUT_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, object]] = []
        for raw in reader:
            row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
            surname = row.get("Surame") or row.get("Surname") or ""
            given = row.get("Given name") or row.get("Given Name") or ""
            full_name = f"{surname}, {given}".strip(", ")
            is_group_a = str(row.get("MHI", "")).strip().lower() == "true"
            for year in range(2011, 2025):
                salary = parse_float(str(row.get(str(year), "")))
                if salary is None:
                    continue
                rows.append(
                    {
                        "name": full_name,
                        "year": year,
                        "salary": salary,
                        "group_a": 1 if is_group_a else 0,
                    }
                )
    return rows


def write_year_means(panel_rows: list[dict[str, object]]) -> None:
    by_year: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in panel_rows:
        by_year[int(r["year"])][int(r["group_a"])].append(float(r["salary"]))

    out_path = OUT_DIR / "descriptive_group_year_means.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "year",
                "mean_group_a",
                "mean_group_b",
                "n_group_a",
                "n_group_b",
                "mean_diff_a_minus_b",
            ]
        )
        for year in sorted(by_year):
            a = by_year[year].get(1, [])
            b = by_year[year].get(0, [])
            mean_a = mean(a) if a else None
            mean_b = mean(b) if b else None
            diff = (mean_a - mean_b) if (mean_a is not None and mean_b is not None) else None
            w.writerow(
                [
                    year,
                    f"{mean_a:.3f}" if mean_a is not None else "",
                    f"{mean_b:.3f}" if mean_b is not None else "",
                    len(a),
                    len(b),
                    f"{diff:.3f}" if diff is not None else "",
                ]
            )


def write_sample_summary(panel_rows: list[dict[str, object]]) -> None:
    by_person: dict[str, int] = {}
    by_person_group: dict[str, int] = {}
    for r in panel_rows:
        name = str(r["name"])
        by_person[name] = by_person.get(name, 0) + 1
        by_person_group[name] = int(r["group_a"])

    n_faculty = len(by_person)
    n_person_years = len(panel_rows)
    n_group_a_faculty = sum(1 for g in by_person_group.values() if g == 1)
    n_group_b_faculty = n_faculty - n_group_a_faculty

    out_path = OUT_DIR / "sample_summary.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["n_faculty", n_faculty])
        w.writerow(["n_person_years", n_person_years])
        w.writerow(["n_group_a_faculty", n_group_a_faculty])
        w.writerow(["n_group_b_faculty", n_group_b_faculty])


def write_figures(panel_rows: list[dict[str, object]]) -> None:
    if plt is None:
        print("matplotlib not available; skipping descriptive figures.")
        return

    by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_year_group: dict[tuple[int, int], list[float]] = defaultdict(list)
    by_group_all: dict[int, list[float]] = defaultdict(list)

    for r in panel_rows:
        by_person[str(r["name"])].append(r)
        by_year_group[(int(r["year"]), int(r["group_a"]))].append(float(r["salary"]))
        by_group_all[int(r["group_a"])].append(float(r["salary"]))

    fig, ax = plt.subplots(figsize=(10, 6))
    for person_rows in by_person.values():
        person_rows = sorted(person_rows, key=lambda x: int(x["year"]))
        years = [int(x["year"]) for x in person_rows]
        salaries = [float(x["salary"]) for x in person_rows]
        group_a = int(person_rows[0]["group_a"])
        color = "#C44E52" if group_a == 1 else "#4C72B0"
        ax.plot(years, salaries, color=color, alpha=0.18, linewidth=0.8)

    years = sorted({int(r["year"]) for r in panel_rows})
    for group_a, color, label in [(1, "#C44E52", "Group A"), (0, "#4C72B0", "Group B")]:
        xs, ys = [], []
        for y in years:
            vals = by_year_group.get((y, group_a), [])
            if vals:
                xs.append(y)
                ys.append(mean(vals))
        ax.plot(xs, ys, color=color, linewidth=3, label=f"{label} mean")

    ax.set_title("Salary trajectories with group trends")
    ax.set_xlabel("Year")
    ax.set_ylabel("Salary (CAD)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "salary_trajectories_by_group.png", dpi=220)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.boxplot(
        [by_group_all.get(1, []), by_group_all.get(0, [])],
        labels=["Group A", "Group B"],
        showmeans=True,
    )
    ax.set_title("Salary distribution by group (all person-years)")
    ax.set_ylabel("Salary (CAD)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "salary_boxplot_by_group.png", dpi=220)
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    panel_rows = load_panel_rows()
    write_year_means(panel_rows)
    write_sample_summary(panel_rows)
    write_figures(panel_rows)
    print(f"Wrote descriptive outputs for {len(panel_rows)} person-years.")


if __name__ == "__main__":
    main()
