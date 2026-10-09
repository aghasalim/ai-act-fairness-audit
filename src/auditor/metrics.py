"""Group fairness metrics, measured at a realistic operating point.

Everything here is computed at a *single global threshold* chosen by alert
budget, because that is how a fraud model is deployed: one score cutoff, a
review queue of fixed size. Measuring parity at p>0.5, where almost nothing is
flagged, would report near-perfect fairness for a model nobody uses that way.

Which metric matters depends on who is harmed:

- **False positive rate**, a legitimate customer is blocked. In fraud this is
  the harm that lands on the innocent, so FPR parity is the headline.
- **False negative rate**, fraud gets through. The cost falls on the merchant
  or the bank, not the customer whose group it is.
- **Selection rate**, the share of a group flagged at all, regardless of
  correctness. Being flagged is the adverse outcome, so the disparate-impact
  ratio is built on its complement, the share of a group let through.
- **Calibration**, whether a score of 0.3 means the same thing in every group.

These cannot all be equalised at once when base rates differ. That is a theorem,
and `impossibility.py` measures it on this model rather than citing it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import config


def threshold_at_budget(scores: np.ndarray, budget: float | None = None) -> float:
    """Score cutoff that flags `budget` of all transactions."""
    budget = config.ALERT_BUDGET if budget is None else budget
    return float(np.quantile(scores, 1 - budget))


def group_metrics(df: pd.DataFrame, segment: str, threshold: float,
                  min_n: int = 500) -> pd.DataFrame:
    """Per-group confusion-matrix rates at one shared threshold.

    Groups below `min_n` are dropped rather than reported: a false-positive rate
    over 200 rows swings wildly, and publishing it as a disparity would be
    manufacturing a finding out of sampling noise.

    A group with no fraud is kept. Its FPR is well defined, and it is exactly
    the group where every flag is a false positive; only TPR, FNR and AUC are
    undefined there, and they come out as NaN.
    """
    rows = []
    for g, sub in df.groupby(segment, observed=True):
        if len(sub) < min_n or sub["isFraud"].all():
            continue
        y = sub["isFraud"].to_numpy().astype(bool)
        flag = sub["pred"].to_numpy() >= threshold
        tp, fp = int((flag & y).sum()), int((flag & ~y).sum())
        fn, tn = int((~flag & y).sum()), int((~flag & ~y).sum())
        rows.append({
            "group": str(g),
            "n": len(sub),
            "base_rate": y.mean(),
            "selection_rate": flag.mean(),
            "TPR": tp / (tp + fn) if tp + fn else np.nan,
            "FPR": fp / (fp + tn) if fp + tn else np.nan,
            "FNR": fn / (tp + fn) if tp + fn else np.nan,
            "precision": tp / (tp + fp) if tp + fp else np.nan,
            "AUC": roc_auc_score(y, sub["pred"]) if y.any() and not y.all() else np.nan,
            "mean_pred": sub["pred"].mean(),
            # >1 means the model under-predicts risk for this group.
            "calibration_ratio": y.mean() / sub["pred"].mean() if sub["pred"].mean() else np.nan,
        })
    return pd.DataFrame(rows).sort_values("FPR", ascending=False).reset_index(drop=True)


def disparity(g: pd.DataFrame) -> dict:
    """Summarise one segment's spread. Ratios, not just differences: a 2pp gap
    means something very different at a 1% base rate than at a 20% one."""
    if len(g) < 2:
        return {}
    sel, fpr, fnr = g["selection_rate"], g["FPR"], g["FNR"]
    out = {
        "n_groups": len(g),
        "selection_min": sel.min(), "selection_max": sel.max(),
        # The four-fifths rule compares rates of the favourable outcome. Here
        # that is not being flagged, so the ratio is on 1 - selection rate. On
        # the flag rate itself it would measure the adverse outcome instead.
        "disparate_impact_ratio": (1 - sel).min() / (1 - sel).max() if (1 - sel).max() else np.nan,
        "FPR_min": fpr.min(), "FPR_max": fpr.max(),
        "FPR_ratio": fpr.max() / fpr.min() if fpr.min() else np.inf,
        "FPR_gap_pp": (fpr.max() - fpr.min()) * 100,
        "FNR_gap_pp": (fnr.max() - fnr.min()) * 100,
        "AUC_min": g["AUC"].min(), "AUC_max": g["AUC"].max(),
        "worst_FPR_group": g.loc[fpr.idxmax(), "group"],
        "best_FPR_group": g.loc[fpr.idxmin(), "group"],
    }
    out["passes_four_fifths"] = bool(out["disparate_impact_ratio"] >= config.FOUR_FIFTHS)
    return out


def audit_all(df: pd.DataFrame, budget: float | None = None) -> tuple[dict, dict]:
    thr = threshold_at_budget(df["pred"].to_numpy(), budget)
    tables, summary = {}, {}
    for seg in config.SEGMENTS:
        if seg not in df.columns:
            continue
        g = group_metrics(df, seg, thr)
        if len(g) < 2:
            continue
        tables[seg] = g
        summary[seg] = disparity(g)
    return tables, {"threshold": thr, "segments": summary}
