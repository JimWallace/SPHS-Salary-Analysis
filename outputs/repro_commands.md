# Reproducibility Commands

Full pipeline (macOS; needs Xcode and Python 3), from the repository root:

```bash
sh scripts/run_full_pipeline.sh
```

Just the core analysis and these deliverables:

```bash
xcodebuild -project SalaryData.xcodeproj -scheme SalaryData -configuration Release -derivedDataPath build_release build
./build_release/Build/Products/Release/SalaryData
python3 scripts/generate_requested_outputs.py
```

Notes:
- The analysis binary reads `data/sphs.csv` if present and writes core results to `analysis_output/`.
- The reporting script writes requested deliverables to `outputs/`.
- Steps that read faculty CVs (`Faculty CVs/`, `data/private/`) need local files that are not in the repository. Without them the CV-derived start years are blank, so results that use the CV/override start-year rule will differ from the report.
