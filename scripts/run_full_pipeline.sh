#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[1/13] Refresh public SPHS scrape"
python3 scripts/scrape_public_sphs_groups.py

echo "[2/13] Build disclosure completeness audit"
python3 scripts/build_disclosure_completeness_audit.py

echo "[3/13] Rebuild data/sphs.csv from disclosures"
python3 scripts/rebuild_sphs_csv_from_disclosures.py

echo "[4/13] Build CV start-year crosswalk"
python3 scripts/build_cv_start_year_crosswalk.py

echo "[5/13] Build appendix verification matrix"
python3 scripts/build_appendix_analysis_verification_matrix.py

echo "[6/13] Build CV crosswalk"
python3 scripts/build_faculty_cv_crosswalk.py

echo "[7/13] Build combined completeness matrix"
python3 scripts/build_faculty_completeness_matrix.py

echo "[8/13] Build and run SalaryData analysis binary (Release)"
xcodebuild -project SalaryData.xcodeproj -scheme SalaryData -configuration Release -derivedDataPath build_release build
./build_release/Build/Products/Release/SalaryData

echo "[9/13] Build descriptive outputs"
python3 scripts/build_descriptive_outputs.py

echo "[10/13] Build trajectory + pgfplots outputs"
python3 scripts/build_matched_model_trajectory_data.py
python3 scripts/build_pgfplots_salary_figure_data.py

echo "[11/13] Build appendix exploratory matrix"
python3 scripts/build_appendix_faculty_exploratory_matrix.py

echo "[12/13] Build skeptic appendix outputs"
python3 scripts/build_skeptic_appendix_outputs.py

echo "[13/13] Build requested report deliverables"
python3 scripts/generate_requested_outputs.py

echo "Pipeline complete."
