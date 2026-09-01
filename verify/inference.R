# Does the audit's headline finding survive its own sampling error?
#
# Every rate in reports/ is a point estimate from a finite number of rows, and
# the Python never put an interval on any of them. The four-fifths verdict in
# particular is a comparison of two ratios of counts, and product W contributes
# 29 flagged rows out of 355,414. A finding that rests on 29 rows deserves an
# interval before it is written down as a fact.
#
# This rebuilds the integer confusion matrix behind each published row, then
# uses exact binomial intervals rather than the normal approximation, because
# some of these counts are small enough for the approximation to be wrong.
#
# It reports, per segment:
#   - a 95% Clopper-Pearson interval on the selection rate of the most and
#     least flagged group,
#   - the most favourable disparate-impact ratio consistent with those
#     intervals, which is the strongest case that can be made for the model,
#   - whether the false-positive rate difference between the extreme groups is
#     distinguishable from zero,
#   - the ratio of the false-negative gap to the false-positive gap, which the
#     README claims is an order of magnitude in every segment.
#
# Base R only. Run with: Rscript verify/inference.R <repo root>

args <- commandArgs(trailingOnly = TRUE)
root <- if (length(args) > 0) args[1] else "."

segments <- c("amount_band", "card_type", "device_type", "email_class",
              "identity_present", "product_code", "region")

failures <- 0
fail <- function(...) {
  cat("  FAIL ", paste0(...), "\n", sep = "")
  failures <<- failures + 1
}

# Rebuild the counts. A rate is a ratio of integers; recover them.
counts <- function(r) {
  n <- as.integer(r$n)
  P <- round(r$base_rate * n); N <- n - P
  TP <- round(r$TPR * P); FP <- round(r$FPR * N)
  list(n = n, P = P, N = N, TP = TP, FP = FP, FN = P - TP, TN = N - FP,
       flagged = TP + FP)
}

ci <- function(x, n) binom.test(x, n)$conf.int  # Clopper-Pearson, exact

worst_ratio <- 0
min_gap_ratio <- Inf

for (seg in segments) {
  f <- file.path(root, "reports", paste0("segment_", seg, ".csv"))
  d <- read.csv(f, check.names = FALSE, stringsAsFactors = FALSE)
  cnt <- lapply(seq_len(nrow(d)), function(i) counts(d[i, ]))

  # Whichever groups sit at the ends of the selection rate.
  hi <- which.max(d$selection_rate); lo <- which.min(d$selection_rate)
  ci_hi <- ci(cnt[[hi]]$flagged, cnt[[hi]]$n)
  ci_lo <- ci(cnt[[lo]]$flagged, cnt[[lo]]$n)

  # The kindest reading of the data: the least flagged group as high as its
  # interval allows, the most flagged as low as its interval allows.
  best_case <- ci_lo[2] / ci_hi[1]
  point <- d$selection_rate[lo] / d$selection_rate[hi]
  if (best_case >= 0.8)
    fail(seg, ": the four-fifths failure is inside sampling error, best case ",
         signif(best_case, 4))
  worst_ratio <- max(worst_ratio, best_case)

  # Is the false-positive difference between the extreme FPR groups real?
  ph <- which.max(d$FPR); pl <- which.min(d$FPR)
  tab <- matrix(c(cnt[[ph]]$FP, cnt[[ph]]$TN, cnt[[pl]]$FP, cnt[[pl]]$TN),
                nrow = 2, dimnames = list(c("FP", "TN"), c("worst", "best")))
  p <- suppressWarnings(chisq.test(tab)$p.value)
  if (!is.finite(p) || p >= 0.05)
    fail(seg, ": the FPR difference between ", d$group[ph], " and ", d$group[pl],
         " is not distinguishable from zero, p = ", signif(p, 3))

  # The README's claim that false-negative gaps dwarf false-positive gaps.
  fnr_gap <- (max(d$FNR) - min(d$FNR)) * 100
  fpr_gap <- (max(d$FPR) - min(d$FPR)) * 100
  min_gap_ratio <- min(min_gap_ratio, fnr_gap / fpr_gap)

  cat(sprintf("  %-17s DI %.5f  95%% best case %.5f   FPR %s vs %s p=%.3g   FNR gap %.1fx FPR gap\n",
              seg, point, best_case, d$group[ph], d$group[pl], p, fnr_gap / fpr_gap))
}

if (min_gap_ratio < 10)
  fail("a segment has a false-negative gap under 10x its false-positive gap, ",
       "which contradicts the order-of-magnitude claim: ", signif(min_gap_ratio, 4))

# Base rates must genuinely differ for the impossibility to apply at all.
d <- read.csv(file.path(root, "reports", "segment_product_code.csv"),
              check.names = FALSE, stringsAsFactors = FALSE)
cnt <- lapply(seq_len(nrow(d)), function(i) counts(d[i, ]))
tab <- rbind(sapply(cnt, function(c) c$P), sapply(cnt, function(c) c$N))
colnames(tab) <- d$group
h <- suppressWarnings(chisq.test(tab))
if (h$p.value >= 0.05)
  fail("product-code base rates are not distinguishable, so the impossibility ",
       "premise is not established: p = ", signif(h$p.value, 3))
cat(sprintf("  product-code base rates differ: chi-squared %.0f on %d df, p = %.3g\n",
            h$statistic, h$parameter, h$p.value))

if (failures > 0) {
  cat("R: ", failures, " failure(s)\n", sep = "")
  quit(status = 1)
}
cat(sprintf(paste0("R: all 7 segments fail four-fifths on the most favourable reading",
                   " of their exact intervals (worst case %.4f, still under 0.8),\n",
                   "   every extreme FPR pair separates, smallest false-negative to",
                   " false-positive gap ratio %.0fx\n"),
            worst_ratio, min_gap_ratio))
