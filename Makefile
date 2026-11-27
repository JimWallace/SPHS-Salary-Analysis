# Salary anomaly screen: rebuild everything from the archived inputs.
#
#   make anomaly          inputs -> models -> report -> checks
#   make anomaly-verify   rebuild twice from scratch and confirm the outputs are byte-identical
#
# Archived inputs (not refetched): data/raw/ (disclosures, manifest with SHA-256), the listing cache in
# data/private/anomaly_cache/, and the collected fields in data/private/anomaly_collect/ (gathered
# under docs/anomaly_collection_protocol.md). Person-level files stay in data/private/ (gitignored).
# The Computer Science scope count reads the School's listing from the same cache (fetched once if absent).

PY := python3
SCRIPTS := scripts
OUTPUTS := analysis_output/anomaly_input_summary.md analysis_output/anomaly_fit_summary.csv \
           analysis_output/anomaly_coefficients.csv analysis_output/anomaly_subject_results.csv \
           analysis_output/anomaly_subject_design.csv analysis_output/anomaly_residuals_S1_main.csv \
           analysis_output/anomaly_residuals_S2_main.csv analysis_output/anomaly_results.tex \
           analysis_output/anomaly_skipped_specs.csv analysis_output/anomaly_cross_report.tex \
           analysis_output/anomaly_inputs.tex analysis_output/anomaly_table_subject.tex \
           analysis_output/anomaly_table_coefficients.tex analysis_output/anomaly_screen_rates.csv \
           analysis_output/anomaly_table_rank.tex analysis_output/anomaly_table_screen.tex \
           analysis_output/anomaly_table_cs.tex analysis_output/anomaly_cs_scope.md \
           analysis_output/anomaly_cs_scope.tex

.PHONY: anomaly-wg2020 anomaly anomaly-inputs anomaly-models anomaly-report anomaly-check anomaly-verify anomaly-test

anomaly: anomaly-inputs anomaly-models anomaly-report anomaly-check

anomaly-inputs:
	cd $(SCRIPTS) && $(PY) anomaly_health_roster.py && $(PY) anomaly_targets.py && $(PY) anomaly_build_inputs.py

anomaly-models: anomaly-inputs
	Rscript $(SCRIPTS)/anomaly_models.R
	cd $(SCRIPTS) && $(PY) anomaly_cross_report.py && $(PY) anomaly_cs_scope.py

anomaly-report: anomaly-models anomaly-wg2020
	Rscript $(SCRIPTS)/anomaly_fit2020.R >/dev/null
	pdflatex -interaction=nonstopmode -halt-on-error anomaly_report.tex >/dev/null
	pdflatex -interaction=nonstopmode -halt-on-error anomaly_report.tex >/dev/null
	@echo "Built anomaly_report.pdf"

anomaly-check: anomaly-models
	cd $(SCRIPTS) && $(PY) anomaly_check.py

anomaly-test:
	$(PY) -m unittest discover -s tests

# Clean rebuild: remove generated outputs, rebuild, hash; repeat; compare.
anomaly-verify:
	rm -f $(OUTPUTS) anomaly_report.pdf
	$(MAKE) anomaly
	sha256sum $(OUTPUTS) > /tmp/anomaly_hashes_1.txt
	rm -f $(OUTPUTS) anomaly_report.pdf
	$(MAKE) anomaly
	sha256sum $(OUTPUTS) > /tmp/anomaly_hashes_2.txt
	diff /tmp/anomaly_hashes_1.txt /tmp/anomaly_hashes_2.txt && echo "Rebuild is byte-identical."

# Test 1 (private, not part of `make anomaly`): the Working Group's published 2020 equation applied to the
# subject's own 1 May 2020 record. Reads and writes data/private/ only.
anomaly-wg2020:
	$(PY) $(SCRIPTS)/anomaly_wg2020_self.py
