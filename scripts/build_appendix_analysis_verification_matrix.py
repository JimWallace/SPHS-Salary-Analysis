#!/usr/bin/env python3
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "sphs.csv"
OUT = ROOT / "analysis_output" / "appendix_analysis_verification_matrix.csv"
SPHS_LIST = ROOT / "SalaryData" / "SPHS Faculty List.swift"


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def norm(value: str) -> str:
    return "".join(value.strip().lower().split())


def fmt_salary(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    cleaned = raw.replace("$", "").replace(",", "")
    try:
        amount = float(cleaned)
    except ValueError:
        return raw
    return f"{amount:.2f}"


def load_allowed_faculty() -> set[str]:
    text = SPHS_LIST.read_text(encoding="utf-8")
    names = re.findall(r'"([^"\n]+)"', text)
    allowed = set()
    for name in names:
        normalized = " ".join(name.strip().upper().replace(",", " ").split())
        allowed.add(normalized)
    return allowed


def main() -> None:
    allowed = load_allowed_faculty()
    with INPUT.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        surname_col = next(c for c in fieldnames if norm(c) in {"surname", "surame"})
        given_col = next(c for c in fieldnames if norm(c) == "givenname")
        mhi_col = next(c for c in fieldnames if norm(c) == "mhi")
        year_cols = sorted((c for c in fieldnames if c and c.strip().isdigit()), key=lambda y: int(y))

        out_rows = []
        for row in reader:
            surname = (row.get(surname_col) or "").strip().upper()
            given = (row.get(given_col) or "").strip().upper()
            if not surname or not given:
                continue
            faculty_name = f"{surname} {given}"
            faculty_key = " ".join(faculty_name.strip().upper().replace(",", " ").split())
            if faculty_key not in allowed:
                continue
            mhi_class = "MHI" if parse_bool(row.get(mhi_col, "")) else "Non-MHI"

            start_year = ""
            for yc in year_cols:
                if (row.get(yc) or "").strip():
                    start_year = yc
                    break

            out_row = {
                "Faculty": faculty_name,
                "MHI Classification": mhi_class,
                "Starting Year": start_year,
            }
            for yc in year_cols:
                out_row[yc] = fmt_salary(row.get(yc, ""))
            out_rows.append(out_row)

    headers = ["Faculty", "MHI Classification", "Starting Year"] + year_cols
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote appendix verification matrix: {OUT}")


if __name__ == "__main__":
    main()
