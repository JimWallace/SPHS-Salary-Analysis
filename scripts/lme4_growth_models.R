#!/usr/bin/env Rscript
# lme4_growth_models.R
#
# Three-step unconditional growth model analysis for SPHS salary data.
#
# Step 1 — Unconditional means model:
#   salary ~ 1 + (1 | faculty)
#   Partitions variance into between-faculty and within-faculty components.
#   Provides ICC as baseline.
#
# Step 2 — Unconditional growth model:
#   salary ~ year_c + (year_c | faculty)
#   Establishes average growth trajectory before group differences.
#
# Step 3 — Conditional growth model:
#   salary ~ year_c * mhi + (year_c | faculty)
#   MHI main effect = intercept (level) gap.
#   year_c:mhi interaction = slope (growth) gap — primary estimate.
#
# Model fit comparison via likelihood ratio tests (anova()).
# Outputs CSV files to analysis_output/.

suppressPackageStartupMessages({
  library(lme4)
  library(lmerTest)
})

# ── 0. Paths ──────────────────────────────────────────────────────────────────
# Resolve project root: works both from Rscript <path> and interactive sessions
script_dir <- tryCatch({
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("--file=", args, value = TRUE)
  if (length(file_arg) > 0) {
    dirname(normalizePath(sub("--file=", "", file_arg[1])))
  } else {
    getwd()
  }
}, error = function(e) getwd())

# If invoked as Rscript scripts/lme4_growth_models.R from project root,
# script_dir is <project_root>/scripts — go one level up.
project_root <- normalizePath(file.path(script_dir, ".."))
data_path    <- file.path(project_root, "data", "sphs.csv")
out_dir      <- file.path(project_root, "analysis_output")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

# ── 1. Load and reshape data ──────────────────────────────────────────────────
wide <- read.csv(data_path, stringsAsFactors = FALSE, check.names = FALSE)

# Build faculty ID from Surname + Given name
wide$faculty_id <- paste0(trimws(wide$Surname), ", ", trimws(wide[["Given name"]]))
wide$mhi        <- as.integer(wide$MHI == "true" | wide$MHI == "TRUE" | wide$MHI == TRUE)

year_cols <- grep("^[0-9]{4}$", names(wide), value = TRUE)

# Reshape to long format
long_list <- vector("list", length(year_cols))
for (i in seq_along(year_cols)) {
  yr <- year_cols[i]
  tmp <- wide[, c("faculty_id", "mhi", yr)]
  names(tmp)[3] <- "salary"
  tmp$year <- as.integer(yr)
  long_list[[i]] <- tmp
}
long <- do.call(rbind, long_list)
long <- long[!is.na(long$salary) & long$salary > 0, ]
long <- long[order(long$faculty_id, long$year), ]

# Centre year at grand mean for numerical stability
year_mean <- mean(long$year)
long$year_c <- long$year - year_mean

# Ensure mhi is numeric 0/1
long$mhi <- as.numeric(long$mhi)

cat(sprintf("Panel: %d person-year observations, %d faculty (%d MHI)\n",
            nrow(long),
            length(unique(long$faculty_id)),
            length(unique(long$faculty_id[long$mhi == 1]))))

# ── 2. Fit three models (REML for variance components; ML for LRT) ────────────

# Model 1: Unconditional means (random intercept only)
m1_reml <- lmer(salary ~ 1 + (1 | faculty_id), data = long, REML = TRUE)
m1_ml   <- lmer(salary ~ 1 + (1 | faculty_id), data = long, REML = FALSE)

# Model 2: Unconditional growth (random intercept + slope, no group predictor)
m2_reml <- lmer(salary ~ year_c + (year_c | faculty_id), data = long, REML = TRUE)
m2_ml   <- lmer(salary ~ year_c + (year_c | faculty_id), data = long, REML = FALSE)

# Model 3: Conditional growth (MHI intercept + slope interaction)
m3_reml <- lmer(salary ~ year_c * mhi + (year_c | faculty_id), data = long, REML = TRUE)
m3_ml   <- lmer(salary ~ year_c * mhi + (year_c | faculty_id), data = long, REML = FALSE)

# ── 3. ICC from Model 1 ───────────────────────────────────────────────────────
vc1          <- as.data.frame(VarCorr(m1_reml))
var_between  <- vc1$vcov[vc1$grp == "faculty_id"]   # τ²₀₀
var_within   <- vc1$vcov[vc1$grp == "Residual"]     # σ²
icc          <- var_between / (var_between + var_within)

cat(sprintf("\nModel 1 — ICC\n"))
cat(sprintf("  Between-faculty variance (τ²₀₀): %10.2f\n", var_between))
cat(sprintf("  Within-faculty variance  (σ²):   %10.2f\n", var_within))
cat(sprintf("  ICC:                             %10.4f\n", icc))

# ── 4. Likelihood ratio tests ─────────────────────────────────────────────────
lrt_12 <- anova(m1_ml, m2_ml, refit = FALSE)   # M1 vs M2: does time improve fit?
lrt_23 <- anova(m2_ml, m3_ml, refit = FALSE)   # M2 vs M3: does MHI improve fit?

cat("\nLRT: Model 1 vs Model 2\n"); print(lrt_12)
cat("\nLRT: Model 2 vs Model 3\n"); print(lrt_23)

# ── 5. Extract fixed-effect coefficients from Model 3 ────────────────────────
coef_m3     <- summary(m3_reml)$coefficients        # uses lmerTest Satterthwaite df
int_est     <- coef_m3["(Intercept)",  "Estimate"]
time_est    <- coef_m3["year_c",        "Estimate"]
mhi_est     <- coef_m3["mhi",           "Estimate"]
int_mhi_est <- coef_m3["year_c:mhi",    "Estimate"]

# 95% Wald CIs
ci_m3       <- confint(m3_reml, method = "Wald", parm = "beta_")
# row names from confint(Wald) match fixef names
fe_names    <- rownames(ci_m3)

get_ci <- function(nm) {
  row <- which(fe_names == nm)
  if (length(row) == 0) return(c(NA_real_, NA_real_))
  ci_m3[row, ]
}

ci_int     <- get_ci("(Intercept)")
ci_time    <- get_ci("year_c")
ci_mhi     <- get_ci("mhi")
ci_int_mhi <- get_ci("year_c:mhi")

p_int     <- coef_m3["(Intercept)",  "Pr(>|t|)"]
p_time    <- coef_m3["year_c",        "Pr(>|t|)"]
p_mhi     <- coef_m3["mhi",           "Pr(>|t|)"]
p_int_mhi <- coef_m3["year_c:mhi",    "Pr(>|t|)"]

# ── 6. Write lme4_growth_model_summary.csv ────────────────────────────────────
n_obs      <- nrow(long)
n_fac      <- length(unique(long$faculty_id))
n_mhi      <- length(unique(long$faculty_id[long$mhi == 1]))

summary_rows <- data.frame(
  model       = character(),
  term        = character(),
  estimate    = numeric(),
  std_error   = numeric(),
  ci_lower    = numeric(),
  ci_upper    = numeric(),
  p_value     = numeric(),
  n_obs       = integer(),
  n_clusters  = integer(),
  stringsAsFactors = FALSE
)

add_row <- function(model, term, est, se, ci_lo, ci_hi, pval) {
  data.frame(model, term, estimate = est, std_error = se,
             ci_lower = ci_lo, ci_upper = ci_hi, p_value = pval,
             n_obs = n_obs, n_clusters = n_fac, stringsAsFactors = FALSE)
}

# Model 1 variance components
summary_rows <- rbind(summary_rows,
  add_row("Unconditional means (M1)", "ICC",
          icc, NA, NA, NA, NA),
  add_row("Unconditional means (M1)", "Var between-faculty (tau^2_00)",
          var_between, NA, NA, NA, NA),
  add_row("Unconditional means (M1)", "Var within-faculty (sigma^2)",
          var_within, NA, NA, NA, NA)
)

# Model 2 fixed effect
coef_m2  <- summary(m2_reml)$coefficients
ci_m2    <- confint(m2_reml, method = "Wald", parm = "beta_")
summary_rows <- rbind(summary_rows,
  add_row("Unconditional growth (M2)", "Annual growth (year_c)",
          coef_m2["year_c", "Estimate"],
          coef_m2["year_c", "Std. Error"],
          ci_m2["year_c", 1], ci_m2["year_c", 2],
          coef_m2["year_c", "Pr(>|t|)"])
)

# Model 3 fixed effects
summary_rows <- rbind(summary_rows,
  add_row("Conditional growth (M3)", "Intercept (non-MHI at mean year)",
          int_est, coef_m3["(Intercept)", "Std. Error"],
          ci_int[1], ci_int[2], p_int),
  add_row("Conditional growth (M3)", "Annual growth non-MHI (year_c)",
          time_est, coef_m3["year_c", "Std. Error"],
          ci_time[1], ci_time[2], p_time),
  add_row("Conditional growth (M3)", "MHI level gap (mhi)",
          mhi_est, coef_m3["mhi", "Std. Error"],
          ci_mhi[1], ci_mhi[2], p_mhi),
  add_row("Conditional growth (M3)", "MHI growth gap (year_c:mhi) [PRIMARY]",
          int_mhi_est, coef_m3["year_c:mhi", "Std. Error"],
          ci_int_mhi[1], ci_int_mhi[2], p_int_mhi)
)

# Format numeric columns for clean display; NA → empty string
fmt_num <- function(x, digits = 2) {
  ifelse(is.na(x), "", formatC(x, format = "f", digits = digits, big.mark = ","))
}
fmt_p <- function(x) {
  ifelse(is.na(x), "",
         ifelse(x < 0.001, "<0.001", formatC(x, format = "f", digits = 4)))
}

summary_rows_out <- data.frame(
  model      = summary_rows$model,
  term       = summary_rows$term,
  estimate   = fmt_num(summary_rows$estimate, 2),
  std_error  = fmt_num(summary_rows$std_error, 2),
  ci_lower   = fmt_num(summary_rows$ci_lower, 2),
  ci_upper   = fmt_num(summary_rows$ci_upper, 2),
  p_value    = fmt_p(summary_rows$p_value),
  n_obs      = summary_rows$n_obs,
  n_clusters = summary_rows$n_clusters,
  stringsAsFactors = FALSE
)

write.csv(summary_rows_out,
          file.path(out_dir, "lme4_growth_model_summary.csv"),
          row.names = FALSE)

# ── 7. Write lme4_lrt_summary.csv ─────────────────────────────────────────────
lrt_df <- data.frame(
  comparison   = c("M1 vs M2 (add time)", "M2 vs M3 (add MHI x time)"),
  df_diff      = c(lrt_12$Df[2],      lrt_23$Df[2]),
  AIC_reduced  = c(lrt_12$AIC[1],     lrt_23$AIC[1]),
  AIC_full     = c(lrt_12$AIC[2],     lrt_23$AIC[2]),
  BIC_reduced  = c(lrt_12$BIC[1],     lrt_23$BIC[1]),
  BIC_full     = c(lrt_12$BIC[2],     lrt_23$BIC[2]),
  logLik_reduced = c(as.numeric(lrt_12$logLik[1]), as.numeric(lrt_23$logLik[1])),
  logLik_full    = c(as.numeric(lrt_12$logLik[2]), as.numeric(lrt_23$logLik[2])),
  chisq        = c(lrt_12$Chisq[2],   lrt_23$Chisq[2]),
  p_value      = c(lrt_12[["Pr(>Chisq)"]][2], lrt_23[["Pr(>Chisq)"]][2]),
  stringsAsFactors = FALSE
)
write.csv(lrt_df,
          file.path(out_dir, "lme4_lrt_summary.csv"),
          row.names = FALSE)

# ── 8. Write lme4_variance_components.csv ────────────────────────────────────
# Variance components for each model
vc_rows <- data.frame(
  model           = character(),
  group           = character(),
  component       = character(),
  variance        = numeric(),
  std_dev         = numeric(),
  stringsAsFactors = FALSE
)

add_vc <- function(model_label, fit) {
  vc <- as.data.frame(VarCorr(fit))
  for (i in seq_len(nrow(vc))) {
    vc_rows <<- rbind(vc_rows, data.frame(
      model     = model_label,
      group     = vc$grp[i],
      component = ifelse(is.na(vc$var2[i]),
                         vc$var1[i],
                         paste0(vc$var1[i], ":", vc$var2[i])),
      variance  = vc$vcov[i],
      std_dev   = vc$sdcor[i],
      stringsAsFactors = FALSE
    ))
  }
}

add_vc("M1: Unconditional means",  m1_reml)
add_vc("M2: Unconditional growth", m2_reml)
add_vc("M3: Conditional growth",   m3_reml)

write.csv(vc_rows,
          file.path(out_dir, "lme4_variance_components.csv"),
          row.names = FALSE)

# ── 9. Print summary to console ───────────────────────────────────────────────
cat("\n\n=== THREE-STEP LME4 GROWTH MODEL RESULTS ===\n\n")

cat("── Model 1: Unconditional Means ─────────────────────────────────────────\n")
print(summary(m1_reml))
cat(sprintf("  ICC = %.4f  (%.1f%% of salary variance is between-faculty)\n\n",
            icc, 100 * icc))

cat("── Model 2: Unconditional Growth ────────────────────────────────────────\n")
print(summary(m2_reml))

cat("── Model 3: Conditional Growth ──────────────────────────────────────────\n")
print(summary(m3_reml))

cat("\n── LRT: Model 1 → Model 2 ───────────────────────────────────────────────\n")
print(lrt_12)
cat("\n── LRT: Model 2 → Model 3 ───────────────────────────────────────────────\n")
print(lrt_23)

cat(sprintf(
  "\n── Primary estimate: MHI growth gap (year_c:mhi)\n   %.2f/year  (95%% CI [%.2f, %.2f])  p = %.4f\n",
  int_mhi_est, ci_int_mhi[1], ci_int_mhi[2], p_int_mhi))

cat("\nOutput files written to analysis_output/:\n")
cat("  lme4_growth_model_summary.csv\n")
cat("  lme4_lrt_summary.csv\n")
cat("  lme4_variance_components.csv\n")
