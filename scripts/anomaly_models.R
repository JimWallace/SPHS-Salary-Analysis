#!/usr/bin/env Rscript
# anomaly_models.R
#
# The regression screen from the University's 2020-21 Salary Anomaly Working Group, without its
# rating-based terms (average R score, OPAs), applied to public salary data. Base R only.
#
#   Rscript scripts/anomaly_models.R                  # default
#   Rscript scripts/anomaly_models.R --with-ratings   # also compares the Stage 3 break-even with the
#                                                     # subject's own ratings (OFF by default; reads
#                                                     # data/private/subject_ratings.csv; writes only to
#                                                     # data/private/)
#
# Every model is fitted WITHOUT the subject's row and the subject's salary is predicted from that fit.
# Leave-one-out residuals for everyone else use the exact OLS identity e_i / (1 - h_ii) on the fit
# without the subject.
#
# Input:  data/private/anomaly_inputs.csv (scripts/anomaly_build_inputs.py)
# Outputs (no names; colleague-level values appear only as unlabelled, sorted residuals):
#   analysis_output/anomaly_fit_summary.csv       spec, stage, n, parameters, adj. R^2, residual SD
#   analysis_output/anomaly_coefficients.csv      spec, term, estimate, SE, t, p
#   analysis_output/anomaly_subject_results.csv   subject's fitted/actual/gap/ratio/flag/percentile/break-even
#   analysis_output/anomaly_subject_design.csv    subject's model-matrix row per spec (for the hand check)
#   analysis_output/anomaly_residuals_<spec>.csv  sorted LOO residuals (unlabelled; subject marked)
#   analysis_output/anomaly_results.tex           LaTeX macros for the report

options(stringsAsFactors = FALSE, warn = 1)

args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("--file=", args, value = TRUE)
root <- if (length(file_arg)) normalizePath(file.path(dirname(sub("--file=", "", file_arg[1])), "..")) else getwd()
with_ratings <- "--with-ratings" %in% commandArgs(trailingOnly = TRUE)
out_dir <- file.path(root, "analysis_output")

# Working Group constants (Appendix, Table 4 and "Identification of Individual Anomalies").
WG_R_COEF <- 27711.54
FLAG_ABS <- 5000
FLAG_REL <- 0.90
REF_YEAR <- 2025
INTERACTION_MIN_CELL <- 5   # Lag x rank-at-hire kept only if every non-reference hire rank has >= 5 people

d <- read.csv(file.path(root, "data", "private", "anomaly_inputs.csv"), check.names = FALSE)
num <- c("hire_year", "degree_year", "lag", "years_since_hire", "salary_2024", "salary_2025",
         "salary_max_2024_2025", "admin_flag", "admin_flag_confirmed", "leave_flag")
for (v in num) d[[v]] <- suppressWarnings(as.numeric(d[[v]]))
blank <- function(x) is.na(x) | x == ""
d$hire_collected <- d$hire_year_source == "collected"
d <- d[blank(d$exclude_reason), ]
stopifnot(sum(d$is_subject == 1) == 1)

# ---------------------------------------------------------------------------------------------------
# Specification builders
# ---------------------------------------------------------------------------------------------------

prep <- function(df, salary_var, rank_var = "current_rank", ref_year = REF_YEAR, impute = FALSE) {
  df$salary <- df[[salary_var]]
  df$rank <- df[[rank_var]]
  df$yrs <- ref_year - df$hire_year
  df$lag_missing <- 0
  if (impute) {
    # Robustness only: missing lag -> median lag of the same rank at hire (overall median if none),
    # with an indicator; missing rank at hire -> its own level.
    df$rank_at_hire[blank(df$rank_at_hire)] <- "Unknown"
    miss <- is.na(df$lag)
    df$lag_missing <- as.numeric(miss)
    for (i in which(miss)) {
      pool <- df$lag[!miss & df$rank_at_hire == df$rank_at_hire[i]]
      df$lag[i] <- if (length(pool)) median(pool) else median(df$lag[!miss])
    }
  }
  df
}

complete_rows <- function(df, vars) {
  ok <- rep(TRUE, nrow(df))
  for (v in vars) ok <- ok & !(is.na(df[[v]]) | df[[v]] == "")
  df[ok, ]
}

set_levels <- function(df) {
  lev <- function(x, ref) {
    present <- unique(x)
    ref <- if (ref %in% present) ref else names(sort(table(x), decreasing = TRUE))[1]
    factor(x, levels = c(ref, setdiff(sort(present), ref)))
  }
  if ("highest_degree" %in% names(df)) df$highest_degree <- lev(df$highest_degree, "Bachelor")
  if ("rank" %in% names(df)) df$rank <- lev(df$rank, "Assistant")
  if ("rank_at_hire" %in% names(df)) df$rank_at_hire <- lev(df$rank_at_hire, "Assistant")
  if ("group" %in% names(df)) df$group <- lev(df$group, "Health")
  df
}

# ---------------------------------------------------------------------------------------------------
# Fit, predict and report one specification
# ---------------------------------------------------------------------------------------------------

fit_spec <- function(spec, stage, label, df, formula_fn, notes = "") {
  df <- set_levels(df)
  others <- df[df$is_subject != 1, ]
  subj <- df[df$is_subject == 1, ]
  stopifnot(nrow(subj) == 1)
  others <- droplevels(others)
  # Factor levels with a single observation cannot be estimated reliably; they stay in, and
  # aliasing is reported, but the subject's levels must exist in the fit.
  for (f in intersect(c("highest_degree", "rank", "rank_at_hire", "group"), names(df))) {
    if (!(as.character(subj[[f]]) %in% levels(others[[f]]))) stop(spec, ": subject's ", f, " not in fit")
    subj[[f]] <- factor(as.character(subj[[f]]), levels = levels(others[[f]]))
  }
  fs <- formula_fn(others)
  m <- lm(fs$formula, data = others)
  aliased <- names(coef(m))[is.na(coef(m))]
  fitted <- unname(predict(m, newdata = subj))
  actual <- subj$salary
  gap <- fitted - actual
  h <- hatvalues(m)
  loo_res <- residuals(m) / (1 - h)          # actual - LOO fitted, for each colleague
  subj_res <- actual - fitted                # the subject is out of sample already
  pct <- 100 * mean(loo_res < subj_res)      # share of colleagues with a lower (more negative) residual
  s <- summary(m)
  co <- as.data.frame(coef(s))
  co$term <- rownames(co)
  names(co)[1:4] <- c("estimate", "se", "t", "p")

  X <- model.matrix(delete.response(terms(m)), model.frame(delete.response(terms(m)), subj, xlev = m$xlevels))
  design <- data.frame(spec = spec, term = colnames(X), x = as.numeric(X[1, ]),
                       coef = unname(coef(m)[colnames(X)]))

  list(
    summary = data.frame(spec = spec, stage = stage, label = label, n = nrow(others),
                         parameters = length(coef(m)) - length(aliased), adj_r2 = s$adj.r.squared,
                         r2 = s$r.squared, resid_sd = s$sigma, interaction = fs$interaction,
                         aliased = paste(aliased, collapse = ";"), notes = notes),
    coefs = cbind(spec = spec, co[, c("term", "estimate", "se", "t", "p")]),
    subject = data.frame(spec = spec, stage = stage, label = label, n = nrow(others), fitted = fitted,
                         actual = actual, gap = gap, ratio = actual / fitted,
                         crit_abs = gap > FLAG_ABS, crit_rel = actual < FLAG_REL * fitted,
                         flagged = (gap > FLAG_ABS) & (actual < FLAG_REL * fitted),
                         loo_percentile = pct, breakeven_r = gap / WG_R_COEF,
                         n_flagged_colleagues = sum((-loo_res) > FLAG_ABS &
                                                      (others$salary < FLAG_REL * (others$salary - loo_res)))),
    residuals = data.frame(spec = spec, residual = c(sort(unname(loo_res)), subj_res),
                           subject = c(rep(0, length(loo_res)), 1)),
    design = design,
    model = m,
    others = others
  )
}

# Model A (Stage 1): Working Group specification minus R score, OPAs, and the academic-group terms.
model_a <- function(others) {
  tab <- table(others$rank_at_hire)
  non_ref <- setdiff(names(tab), levels(others$rank_at_hire)[1])
  keep_int <- length(non_ref) > 0 && all(tab[non_ref] >= INTERACTION_MIN_CELL)
  rhs <- "lag + yrs + I(yrs^2)"
  for (f in c("highest_degree", "rank", "rank_at_hire")) if (nlevels(others[[f]]) > 1) rhs <- paste(rhs, "+", f)
  if ("lag_missing" %in% names(others) && any(others$lag_missing == 1)) rhs <- paste(rhs, "+ lag_missing")
  if (keep_int) rhs <- paste(rhs, "+ lag:rank_at_hire")
  list(formula = as.formula(paste("salary ~", rhs)), interaction = keep_int)
}

# Stage 2: seniority and lag, plus academic group (collapsed to Faculties).
model_s2 <- function(others) {
  rhs <- "yrs + I(yrs^2) + lag"
  if (nlevels(others$group) > 1) rhs <- paste(rhs, "+ group")
  if ("cohort2025" %in% names(others)) rhs <- paste(rhs, "+ cohort2025")
  if ("lag_missing" %in% names(others) && any(others$lag_missing == 1)) rhs <- paste(rhs, "+ lag_missing")
  list(formula = as.formula(paste("salary ~", rhs)), interaction = NA)
}

# ---------------------------------------------------------------------------------------------------
# Stage 1: Faculty of Health
# ---------------------------------------------------------------------------------------------------

h_all <- d[d$in_health == 1, ]
s1_vars <- c("salary", "rank", "rank_at_hire", "highest_degree", "lag", "yrs")
s1_base <- function(salary_var = "salary_2025", rank_var = "current_rank", ref_year = REF_YEAR,
                    fallback = FALSE, impute = FALSE) {
  df <- h_all
  if (!fallback) df <- df[df$hire_collected, ]
  df <- prep(df, salary_var, rank_var, ref_year, impute)
  complete_rows(df, s1_vars)
}

res <- list()
skipped <- data.frame(spec = character(), reason = character())
add <- function(expr) {
  # A specification that cannot predict the subject (e.g. every other member of the subject's group
  # removed) is recorded as not estimable instead of stopping the run.
  r <- tryCatch(expr, error = function(e) e)
  if (inherits(r, "error")) {
    msg <- conditionMessage(r)
    skipped[nrow(skipped) + 1, ] <<- list(sub(":.*", "", msg), msg)
  } else {
    res[[length(res) + 1]] <<- r
  }
}

base <- s1_base()
add(fit_spec("S1_main", 1, "Main: 2025 salaries", base, model_a))
s24 <- s1_base("salary_2024", "rank_2024", 2024)
s24$salary[s24$is_subject == 1] <- s24$salary_2024[s24$is_subject == 1]
add(fit_spec("S1_i_2024", 1, "(i) 2024 salaries, 2024 ranks", s24, model_a,
             "Subject's 2024 paid salary (no leave in 2024)."))
add(fit_spec("S1_ii_max", 1, "(ii) max(2024, 2025) for colleagues", s1_base("salary_max_2024_2025"), model_a))
add(fit_spec("S1_iii_admin", 1, "(iii) excluding confirmed administrative roles",
             base[base$admin_flag_confirmed != 1 | base$is_subject == 1, ], model_a))
add(fit_spec("S1_iii_admin_broad", 1, "(iii-b) excluding any administrative role",
             base[base$admin_flag != 1 | base$is_subject == 1, ], model_a))
add(fit_spec("S1_iv_leave", 1, "(iv) excluding likely leave", base[base$leave_flag != 1 | base$is_subject == 1, ], model_a))
add(fit_spec("S1_v_prof", 1, "(v) professorial ranks only", base[base$rank != "Lecturer", ], model_a))
# (vi) high leverage: hat > 2p/n or Cook's distance > 4/n in the main fit, removed and refitted.
by_spec <- function(spec) res[[which(vapply(res, function(r) r$summary$spec, "") == spec)]]
influential <- function(r) {
  m <- r$model
  r$others$person_id[hatvalues(m) > 2 * length(coef(m)) / nobs(m) | cooks.distance(m) > 4 / nobs(m)]
}
drop_ids <- influential(by_spec("S1_main"))
add(fit_spec("S1_vi_leverage", 1, "(vi) excluding high-leverage observations",
             base[!(base$person_id %in% drop_ids), ], model_a,
             sprintf("%d observations removed (hat > 2p/n or Cook's D > 4/n).", length(drop_ids))))
add(fit_spec("S1_vii_fallback", 1, "(vii) adding first-disclosure hire years", s1_base(fallback = TRUE), model_a,
             "Hire year = first disclosure year where no public source was found."))
add(fit_spec("S1_viii_impute", 1, "(viii) imputing missing lag and rank at hire",
             complete_rows(prep(h_all[h_all$hire_collected, ], "salary_2025", impute = TRUE), s1_vars), model_a,
             "Missing lag: median of the same rank at hire, with an indicator; missing rank at hire: own level."))

# ---------------------------------------------------------------------------------------------------
# Stage 2: the 2025 promotion pool, adjusted for seniority
# ---------------------------------------------------------------------------------------------------

p_all <- d[d$in_pool == 1, ]
p_all$group <- p_all$academic_group_s2
s2_vars <- c("salary", "lag", "yrs", "group")
s2_base <- function(salary_var = "salary_2025", ref_year = REF_YEAR, fallback = FALSE, impute = FALSE) {
  df <- p_all
  if (!fallback) df <- df[df$hire_collected, ]
  df <- prep(df, salary_var, "current_rank", ref_year, impute)
  df <- complete_rows(df, s2_vars)
  # Groups with fewer than 3 people (subject excluded) are pooled into "Other" and documented.
  tab <- table(df$group[df$is_subject != 1])
  small <- names(tab)[tab < 3 & names(tab) != "Health"]
  df$group[df$group %in% small] <- "Other"
  attr(df, "pooled") <- small
  df
}
pb <- s2_base()
pool_note <- function(df) if (length(attr(df, "pooled"))) paste("Pooled into Other:", paste(attr(df, "pooled"), collapse = ", ")) else ""
add(fit_spec("S2_main", 2, "Main: 2025 salaries", pb, model_s2, pool_note(pb)))
p24 <- s2_base("salary_2024", 2024)
p24$cohort2025 <- as.numeric(p24$pool_year == "2025")
add(fit_spec("S2_i_2024", 2, "(i) 2024 salaries, with promotion-year indicator", p24, model_s2, pool_note(p24)))
pmx <- s2_base("salary_max_2024_2025")
add(fit_spec("S2_ii_max", 2, "(ii) max(2024, 2025) for colleagues", pmx, model_s2, pool_note(pmx)))
add(fit_spec("S2_iii_admin", 2, "(iii) excluding confirmed administrative roles",
             pb[pb$admin_flag_confirmed != 1 | pb$is_subject == 1, ], model_s2))
add(fit_spec("S2_iv_leave", 2, "(iv) excluding likely leave", pb[pb$leave_flag != 1 | pb$is_subject == 1, ], model_s2))
drop2 <- influential(by_spec("S2_main"))
add(fit_spec("S2_vi_leverage", 2, "(vi) excluding high-leverage observations",
             pb[!(pb$person_id %in% drop2), ], model_s2,
             sprintf("%d observations removed (hat > 2p/n or Cook's D > 4/n).", length(drop2))))
pfb <- s2_base(fallback = TRUE)
add(fit_spec("S2_vii_fallback", 2, "(vii) adding first-disclosure hire years", pfb, model_s2, pool_note(pfb)))
pim <- s2_base(impute = TRUE)
add(fit_spec("S2_viii_impute", 2, "(viii) imputing missing lag", pim, model_s2, pool_note(pim)))

# ---------------------------------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------------------------------

bind <- function(k) do.call(rbind, lapply(res, `[[`, k))
fits <- bind("summary"); coefs <- bind("coefs"); subj <- bind("subject"); design <- bind("design")
write.csv(fits, file.path(out_dir, "anomaly_fit_summary.csv"), row.names = FALSE)
write.csv(skipped, file.path(out_dir, "anomaly_skipped_specs.csv"), row.names = FALSE)
# Sample membership per specification, for the independent re-derivation (private: person ids).
samples <- do.call(rbind, lapply(res, function(r) data.frame(spec = r$summary$spec, person_id = r$others$person_id,
                                                             salary = r$others$salary, lag = r$others$lag,
                                                             yrs = r$others$yrs)))
write.csv(samples, file.path(root, "data", "private", "anomaly_model_samples.csv"), row.names = FALSE)
write.csv(coefs, file.path(out_dir, "anomaly_coefficients.csv"), row.names = FALSE)
write.csv(subj, file.path(out_dir, "anomaly_subject_results.csv"), row.names = FALSE)
write.csv(design, file.path(out_dir, "anomaly_subject_design.csv"), row.names = FALSE)
for (r in res) {
  spec <- r$summary$spec
  if (spec %in% c("S1_main", "S2_main")) {
    write.csv(r$residuals[, c("residual", "subject")], file.path(out_dir, sprintf("anomaly_residuals_%s.csv", spec)),
              row.names = FALSE)
  }
}

money <- function(x) {
  s <- formatC(abs(round(x)), format = "d", big.mark = ",")
  paste0(if (x < 0) "$-$" else "", "\\$", gsub(",", "{,}", s))
}
mac <- c("% Generated by scripts/anomaly_models.R. Do not edit.")
put <- function(name, value) mac <<- c(mac, sprintf("\\newcommand{\\%s}{%s}", name, value))
for (i in seq_len(nrow(subj))) {
  key <- sub("^S1_", "One", sub("^S2_", "Two", subj$spec[i]))
  key <- gsub("[^A-Za-z]", "", key)
  f <- fits[fits$spec == subj$spec[i], ]
  put(paste0(key, "N"), subj$n[i])
  put(paste0(key, "Fitted"), money(subj$fitted[i]))
  put(paste0(key, "Actual"), money(subj$actual[i]))
  put(paste0(key, "Gap"), money(subj$gap[i]))
  put(paste0(key, "Ratio"), sprintf("%.1f", 100 * subj$ratio[i]))
  put(paste0(key, "Flag"), if (subj$flagged[i]) "Yes" else "No")
  put(paste0(key, "CritAbs"), if (subj$crit_abs[i]) "Yes" else "No")
  put(paste0(key, "CritRel"), if (subj$crit_rel[i]) "Yes" else "No")
  put(paste0(key, "Pct"), sprintf("%.0f", subj$loo_percentile[i]))
  put(paste0(key, "BreakEven"), sprintf("%.2f", subj$breakeven_r[i]))
  put(paste0(key, "AdjRsq"), sprintf("%.0f", 100 * f$adj_r2))
  put(paste0(key, "ResidSD"), money(f$resid_sd))
}
put("WGRCoef", money(WG_R_COEF))
writeLines(mac, file.path(out_dir, "anomaly_results.tex"))

if (nrow(skipped)) { cat("\n== Not estimable ==\n"); print(skipped) }
cat("\n== Fit summary ==\n"); print(fits[, c("spec", "n", "parameters", "adj_r2", "resid_sd", "interaction", "aliased")], digits = 3)
cat("\n== Subject ==\n"); print(subj[, c("spec", "n", "fitted", "actual", "gap", "ratio", "flagged", "loo_percentile", "breakeven_r")], digits = 4)

# ---------------------------------------------------------------------------------------------------
# Stage 3 comparison with the subject's own ratings: OFF unless --with-ratings.
# ---------------------------------------------------------------------------------------------------
if (with_ratings) {
  rf <- file.path(root, "data", "private", "subject_ratings.csv")   # columns: year, rating
  if (!file.exists(rf)) stop("--with-ratings needs ", rf)
  r <- read.csv(rf)
  r <- r[r$year >= 2014 & r$year <= 2020, ]
  out <- data.frame(spec = subj$spec, breakeven_r = subj$breakeven_r, subject_mean_r_2014_2020 = mean(r$rating))
  write.csv(out, file.path(root, "data", "private", "anomaly_ratings_comparison.csv"), row.names = FALSE)
  cat("\nRatings comparison written to data/private/anomaly_ratings_comparison.csv (not published).\n")
}
