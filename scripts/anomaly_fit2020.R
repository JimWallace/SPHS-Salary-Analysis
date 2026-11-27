#!/usr/bin/env Rscript
# anomaly_fit2020.R
#
# Comparison-group test: does a Faculty of Health model fitted on 2020 salaries predict the subject's
# 2020 salary differently from the Working Group's University-wide model (test 1)?
#
# Fits the Stage 1 specification (no rating terms) on 2020 calendar-year salaries of Faculty of Health
# colleagues hired by 2019, professorial ranks only (one lecturer in the 2020 sample), excluding the subject.
# The 2020 disclosure lists only salaries of $100,000 or more, so the fit is also estimated as a truncated
# regression (normal errors, lower truncation at $100,000) by maximum likelihood.
#
# Input:  data/private/anomaly_inputs.csv, data/private/anomaly_wg2020_self.csv (test 1)
# Output: data/private/anomaly_fit2020.md and .csv (private: compared with the subject's own 2020 record)

options(stringsAsFactors = FALSE)
args <- commandArgs(trailingOnly = FALSE)
f <- grep("--file=", args, value = TRUE)
root <- if (length(f)) normalizePath(file.path(dirname(sub("--file=", "", f[1])), "..")) else getwd()
priv <- file.path(root, "data", "private")
WG_R <- 27711.54; WG_OPA <- 3881.91; THRESH <- 100000

d <- read.csv(file.path(priv, "anomaly_inputs.csv"))
for (v in c("hire_year", "lag", "salary_2020", "admin_flag_confirmed")) d[[v]] <- suppressWarnings(as.numeric(d[[v]]))
d <- d[d$in_health == 1 & (is.na(d$exclude_reason) | d$exclude_reason == ""), ]
d <- d[startsWith(d$hire_year_source, "collected") & !is.na(d$lag) & d$rank_at_hire != "" &
         !is.na(d$hire_year) & d$hire_year <= 2019, ]
subject <- d[d$is_subject == 1, ]
d <- d[d$is_subject != 1 & !is.na(d$salary_2020) & d$rank_2020 %in% c("Assistant", "Associate", "Professor"), ]
d$yrs <- 2020 - d$hire_year
subject$yrs <- 2020 - subject$hire_year
subject$rank_2020 <- "Associate"   # disclosed title 2019-2020

# Rank at hire: levels with fewer than 3 colleagues are pooled with Associate ("above Assistant").
tab <- table(d$rank_at_hire)
d$hire_grp <- ifelse(d$rank_at_hire == "Assistant", "Assistant", ifelse(d$rank_at_hire == "Lecturer", "Lecturer", "Above"))
if (sum(d$hire_grp == "Lecturer") < 3) d$hire_grp[d$hire_grp == "Lecturer"] <- "Assistant"
subject$hire_grp <- "Assistant"
d$rank <- factor(d$rank_2020, levels = c("Assistant", "Associate", "Professor"))
d$hire_grp <- factor(d$hire_grp, levels = c("Assistant", setdiff(unique(d$hire_grp), "Assistant")))
subject$rank <- factor(subject$rank_2020, levels = levels(d$rank))
subject$hire_grp <- factor(subject$hire_grp, levels = levels(d$hire_grp))

fml <- salary_2020 ~ lag + yrs + I(yrs^2) + rank + hire_grp
ols <- lm(fml, data = d)
X <- model.matrix(fml, d); y <- d$salary_2020
xs <- model.matrix(delete.response(terms(ols)), model.frame(delete.response(terms(ols)), subject, xlev = ols$xlevels))

# Estimated in thousands of dollars for numerical stability.
yk <- y / 1000; tk <- THRESH / 1000
negll <- function(par) {
  b <- par[-length(par)]; s <- exp(par[length(par)])
  mu <- as.vector(X %*% b)
  -sum(dnorm(yk, mu, s, log = TRUE) - pnorm(tk, mu, s, lower.tail = FALSE, log.p = TRUE))
}
start <- c(coef(ols) / 1000, log(summary(ols)$sigma / 1000))
fit <- optim(start, negll, method = "BFGS", control = list(maxit = 10000, reltol = 1e-14))
fit$par[-length(fit$par)] <- fit$par[-length(fit$par)] * 1000
fit$par[length(fit$par)] <- fit$par[length(fit$par)] + log(1000)
b_tr <- fit$par[-length(fit$par)]
pred_ols <- as.numeric(predict(ols, newdata = subject))
pred_tr <- as.numeric(xs %*% b_tr)

# Excluding confirmed administrative roles (stipends inflate paid salary).
d2 <- d[d$admin_flag_confirmed != 1, ]
ols2 <- lm(fml, data = d2)
pred_ols2 <- as.numeric(predict(ols2, newdata = subject))

wg <- read.csv(file.path(priv, "anomaly_wg2020_self.csv"))
wg_fit <- as.numeric(wg$fitted_2020[1]); r_own <- as.numeric(wg$r_average[1])
base_lo <- as.numeric(wg$base_salary_2020_05_01[1]); base_hi <- as.numeric(wg$base_salary_2020_05_01[2])
wg_avg0 <- wg_fit + (1.6 - r_own) * WG_R                 # a colleague like me rated 1.6, no OPAs
wg_avg1 <- wg_avg0 + WG_OPA                               # ... with one OPA (upper end of the unit's average)

money <- function(x) formatC(round(x), format = "d", big.mark = ",")
ratio <- function(pred) sprintf("%.1f%% to %.1f%%", 100 * base_lo / pred, 100 * base_hi / pred)
rows <- data.frame(
  prediction = c("Health 2020 fit, OLS (no rating terms)", "Health 2020 fit, truncated regression",
                 "Health 2020 fit, OLS, excluding confirmed admin roles",
                 "University model, my own ratings (test 1)", "University model, rated 1.6, no OPAs",
                 "University model, rated 1.6, one OPA"),
  predicted = c(pred_ols, pred_tr, pred_ols2, wg_fit, wg_avg0, wg_avg1))
rows$actual_over_predicted <- sapply(rows$predicted, ratio)
rows$flagged_at_low_base <- (rows$predicted - base_lo > 5000) & (base_lo < 0.9 * rows$predicted)
write.csv(rows, file.path(priv, "anomaly_fit2020.csv"), row.names = FALSE)

co <- summary(ols)$coefficients
md <- c("# 2020 comparison-group test (PRIVATE)", "",
        sprintf("Faculty of Health colleagues hired by 2019 with a 2020 disclosure, professorial ranks: n = %d.", nrow(d)),
        sprintf("OLS adjusted R^2 = %.2f, residual SD = %s. Truncated-regression SD = %s (converged: %s).",
                summary(ols)$adj.r.squared, money(summary(ols)$sigma), money(exp(fit$par[length(fit$par)])),
                fit$convergence == 0),
        "", "| Term | OLS estimate | SE | Truncated estimate |", "|---|---|---|---|",
        sprintf("| %s | %s | %s | %s |", rownames(co), money(co[, 1]), money(co[, 2]), money(b_tr[rownames(co)])),
        "", sprintf("My 1 May 2020 base salary: %s to %s.", money(base_lo), money(base_hi)), "",
        "| Prediction for me, 2020 | Predicted | Actual / predicted | Flagged (low base) |", "|---|---|---|---|",
        sprintf("| %s | %s | %s | %s |", rows$prediction, money(rows$predicted), rows$actual_over_predicted,
                ifelse(rows$flagged_at_low_base, "Yes", "No")))
writeLines(md, file.path(priv, "anomaly_fit2020.md"))
cat(md, sep = "\n")

# Report macros (private: they rest on the subject's own 2020 base range and ratings).
wgc <- read.csv(file.path(root, "data", "wg2021_table4_coefficients.csv"))
wg_prem <- wgc$estimate[wgc$term == "Current.Rank:Professor"] - wgc$estimate[wgc$term == "Current.Rank:Associate Professor"]
c25 <- read.csv(file.path(root, "analysis_output", "anomaly_coefficients.csv"))
c25 <- c25[c25$spec == "S1_main", ]
prem25 <- c25$estimate[c25$term == "rankProfessor"] - c25$estimate[c25$term == "rankAssociate"]
prem20 <- coef(ols)[["rankProfessor"]] - coef(ols)[["rankAssociate"]]
tex_money <- function(x) paste0("\\$", gsub(",", "{,}", money(x)))
mac <- c("% Generated by scripts/anomaly_fit2020.R from private inputs. Do not edit or publish.",
         sprintf("\\newcommand{\\FTwentyN}{%d}", nrow(d)),
         sprintf("\\newcommand{\\FTwentyPred}{%s}", tex_money(pred_ols)),
         sprintf("\\newcommand{\\FTwentyPredTr}{%s}", tex_money(pred_tr)),
         sprintf("\\newcommand{\\FTwentyRatioLo}{%.1f}", 100 * base_lo / pred_ols),
         sprintf("\\newcommand{\\FTwentyRatioHi}{%.1f}", 100 * base_hi / pred_ols),
         sprintf("\\newcommand{\\FTwentyPrem}{%s}", tex_money(prem20)),
         sprintf("\\newcommand{\\FTwentyFivePrem}{%s}", tex_money(prem25)),
         sprintf("\\newcommand{\\WGPrem}{%s}", tex_money(wg_prem)))
writeLines(mac, file.path(priv, "anomaly_fit2020.tex"))
