#!/usr/bin/env python3
import csv
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis_output"
VERIFY_PATH = ANALYSIS / "appendix_analysis_verification_matrix.csv"
OUT_DIR = ANALYSIS / "jw_peer_series"
LIST_TEX = ANALYSIS / "jw_peer_series_list.tex"
PLOT_TEX = ANALYSIS / "jw_peer_series_plot.tex"


def to_float(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return float(s.replace("$", "").replace(",", ""))


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def first_obs_year(row):
    year_cols = sorted(int(c) for c in row.keys() if c.strip().isdigit())
    for y in year_cols:
        if to_float(row.get(str(y))) is not None:
            return y
    return None


def start_year_for(row):
    raw = str(row.get("Start Year", "")).strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return first_obs_year(row)


def find_wallace(rows):
    for row in rows:
        name = str(row.get("Faculty", "")).upper()
        if "WALLACE" in name and "JAMES" in name:
            return row
    raise ValueError("Could not find James Wallace in verification matrix.")


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "faculty"

def display_name(name):
    raw = str(name).strip()
    if not raw:
        return "Unknown"
    tokens = raw.split()
    if len(tokens) >= 3 and (tokens[-1].endswith(".") or len(tokens[-1]) == 1):
        first = " ".join(tokens[-2:])
        last = " ".join(tokens[:-2])
    else:
        first = tokens[-1]
        last = " ".join(tokens[:-1])

    def tidy(token):
        lower = token.lower()
        if lower.startswith("(") and lower.endswith(")"):
            inner = lower[1:-1].capitalize()
            return f"({inner})"
        if "." in lower:
            parts = [p for p in lower.split(".") if p]
            return ".".join(p.capitalize() for p in parts) + "."
        return lower.capitalize()

    first_fmt = " ".join(tidy(t) for t in first.split())
    last_fmt = " ".join(tidy(t) for t in last.split())
    return f"{first_fmt} {last_fmt}".strip()


def extract_series(row):
    years = sorted(int(c) for c in row.keys() if c.strip().isdigit())
    series = []
    for y in years:
        val = to_float(row.get(str(y)))
        if val is None:
            continue
        series.append((y, val))
    return series


def latex_escape(text):
    return (
        text.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )


def main():
    rows = read_csv(VERIFY_PATH)
    wallace = find_wallace(rows)
    jw_start = start_year_for(wallace)
    if jw_start is None:
        raise ValueError("James Wallace start year unavailable.")

    selected = []
    for row in rows:
        sy = start_year_for(row)
        if sy is None:
            continue
        if abs(sy - jw_start) <= 1:
            selected.append(row)

    if not selected:
        raise ValueError("No peer rows found within +/-1 year of James Wallace.")

    OUT_DIR.mkdir(exist_ok=True)

    peer_files = []
    peer_entries = []
    peer_entries_labeled = []
    plot_entries = []
    jw_file = None
    jw_name = None
    jw_label_year = None
    jw_label_salary = None

    for row in selected:
        name = str(row.get("Faculty", "")).strip()
        slug = slugify(name)
        filename = f"{slug}.csv"
        series = extract_series(row)
        if not series:
            continue
        label_year, label_salary = series[-1]
        out_path = OUT_DIR / filename
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["year", "salary"])
            for year, salary in series:
                w.writerow([year, f"{salary:.2f}"])

        mhi_raw = str(row.get("MHI Classification", "")).strip().lower()
        is_mhi = 1 if ("mhi" in mhi_raw and "non" not in mhi_raw) else 0
        pretty = display_name(name)

        entry = {
            "filename": filename,
            "pretty": pretty,
            "is_mhi": is_mhi,
            "label_year": label_year,
            "label_salary": label_salary,
            "is_jw": row is wallace,
        }

        if row is wallace:
            jw_file = filename
            jw_name = pretty
            jw_label_year = label_year
            jw_label_salary = label_salary
        else:
            peer_files.append(filename)
            peer_entries.append((filename, pretty, is_mhi))
            peer_entries_labeled.append((filename, pretty, is_mhi, label_year, label_salary))
        plot_entries.append(entry)

    if not jw_file:
        raise ValueError("James Wallace series not written.")
    if not jw_name:
        jw_name = "James Wallace"
    if jw_label_year is None or jw_label_salary is None:
        raise ValueError("James Wallace label coordinates unavailable.")
    jw_xmin = jw_start - 1

    # Write LaTeX helper list
    with LIST_TEX.open("w", encoding="utf-8") as f:
        f.write("% Auto-generated by build_jw_peer_trajectory_plot.py\n")
        f.write("\\def\\JWPeerSeriesFiles{")
        f.write(",".join(peer_files))
        f.write("}\n")
        f.write("\\def\\JWPeerSeriesEntries{")
        f.write(",".join(f"{fn}/{{{nm}}}/{mhi}" for fn, nm, mhi in peer_entries))
        f.write("}\n")
        f.write("\\def\\JWPeerSeriesEntriesLabeled{")
        f.write(",".join(f"{fn}/{{{nm}}}/{mhi}/{ly}/{ls:.2f}" for fn, nm, mhi, ly, ls in peer_entries_labeled))
        f.write("}\n")
        f.write(f"\\def\\JWPeerJWFile{{{jw_file}}}\n")
        f.write(f"\\def\\JWPeerJWName{{{jw_name}}}\n")
        f.write(f"\\def\\JWPeerJWLabelYear{{{jw_label_year}}}\n")
        f.write(f"\\def\\JWPeerJWLabelSalary{{{jw_label_salary:.2f}}}\n")
        f.write(f"\\def\\JWPeerXMin{{{jw_xmin}}}\n")
        f.write(f"\\def\\JWPeerStartYear{{{jw_start}}}\n")
        f.write(f"\\def\\JWPeerCount{{{len(peer_files)}}}\n")

    with PLOT_TEX.open("w", encoding="utf-8") as f:
        label_offsets = {
            "Jennifer L Yessis": 6,
            "Diane Williams": -6,
            "Ashok Chaurasia": 8,
            "James R. Wallace": -8,
        }
        f.write("% Auto-generated by build_jw_peer_trajectory_plot.py\n")
        for entry in plot_entries:
            filename = entry["filename"]
            pretty = latex_escape(entry["pretty"])
            yshift = label_offsets.get(entry["pretty"], 0)
            yshift_opt = f", yshift={yshift}pt" if yshift else ""
            is_mhi = entry["is_mhi"]
            label_year = entry["label_year"]
            label_salary = entry["label_salary"]
            if entry["is_jw"]:
                f.write(
                    f"\\addplot[draw=MHIColor, very thick] table[col sep=comma, x=year, y=salary] {{analysis_output/jw_peer_series/{filename}}};\n"
                )
                f.write(
                    f"\\addplot[only marks, mark=triangle*, mark size=1.7pt, draw=MHIColor, fill=MHIColor, opacity=0.90, forget plot] table[col sep=comma, x=year, y=salary] {{analysis_output/jw_peer_series/{filename}}};\n"
                )
                f.write(
                    f"\\node[anchor=west, xshift=4pt{yshift_opt}, text=MHIColor, font=\\footnotesize] at (axis cs:{label_year},{label_salary:.2f}) {{\\textbf{{{pretty}}}}};\n"
                )
                continue
            if is_mhi:
                f.write(
                    f"\\addplot[draw=MHIColor, line width=1.1pt, opacity=0.55, densely dashed] table[col sep=comma, x=year, y=salary] {{analysis_output/jw_peer_series/{filename}}};\n"
                )
                f.write(
                    f"\\addplot[only marks, mark=triangle*, mark size=1.3pt, draw=MHIColor, fill=MHIColor, opacity=0.55, forget plot] table[col sep=comma, x=year, y=salary] {{analysis_output/jw_peer_series/{filename}}};\n"
                )
                f.write(
                    f"\\node[anchor=west, xshift=4pt{yshift_opt}, text=MHIColor, font=\\footnotesize] at (axis cs:{label_year},{label_salary:.2f}) {{{pretty}}};\n"
                )
            else:
                f.write(
                    f"\\addplot[draw=NonMHIColor, line width=1.1pt, opacity=0.55, densely dashed] table[col sep=comma, x=year, y=salary] {{analysis_output/jw_peer_series/{filename}}};\n"
                )
                f.write(
                    f"\\addplot[only marks, mark=o, mark size=1.1pt, draw=NonMHIColor, fill=white, opacity=0.55, forget plot] table[col sep=comma, x=year, y=salary] {{analysis_output/jw_peer_series/{filename}}};\n"
                )
                f.write(
                    f"\\node[anchor=west, xshift=4pt{yshift_opt}, text=NonMHIColor, font=\\footnotesize] at (axis cs:{label_year},{label_salary:.2f}) {{{pretty}}};\n"
                )


if __name__ == "__main__":
    main()
