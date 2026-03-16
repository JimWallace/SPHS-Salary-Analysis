# Reproducibility Commands

```bash
cd /Users/jim/Documents/SPHS\ Salary\ Analysis
xcodebuild -project SalaryData.xcodeproj -scheme SalaryData -configuration Debug -derivedDataPath build build
./build/Build/Products/Debug/SalaryData
python3 scripts/generate_requested_outputs.py
```

Notes:
- The analysis binary reads `data/sphs.csv` if present and writes core results to `analysis_output/`.
- The reporting script writes requested deliverables to `outputs/`.
