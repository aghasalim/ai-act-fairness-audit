"""The fairness impossibility, measured on this model rather than cited.

When base rates differ between groups, you cannot simultaneously have equal
selection rates, equal false-positive rates, and a calibrated score
(Kleinberg et al. 2016; Chouldechova 2017). It is usually presented as a theorem
and left there, which makes it easy to nod at and then ask an engineer to "make
the model fair" anyway.

Base fraud rates here differ by roughly 5.7x across product lines, so the
constraint is live. This module builds three deployable threshold policies and
measures what each one costs, so the trade-off is a table a manager can choose
from rather than an abstraction:

1. **one global threshold**, what the model repo actually ships
2. **equalised selection rate**, every group flagged at the same rate
3. **equalised FPR**, every group's innocent customers wrongly blocked at the
   same rate

None of the three is "the fair one". Picking between them is a policy decision
about who absorbs the error, and the AI Act does not make it for you, it
requires that you examine it (Art. 10(2)(f)) and document what you chose.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, metrics


def _rates(y: np.ndarray, flag: np.ndarray) -> dict:
    tp, fp = int((flag & y).sum()), int((flag & ~y).sum())
    fn, tn = int((~flag & y).sum()), int((~flag & ~y).sum())
    return {
        "selection_rate": float(flag.mean()),
        "FPR": fp / (fp + tn) if fp + tn else np.nan,
        "TPR": tp / (tp + fn) if tp + fn else np.nan,
        "precision": tp / (tp + fp) if tp + fp else np.nan,
    }


def _threshold_for_selection(scores: np.ndarray, rate: float) -> float:
    return float(np.quantile(scores, 1 - rate))


def _threshold_for_fpr(scores: np.ndarray, y: np.ndarray, target: float) -> float:
    """Lowest threshold whose FPR on the negatives does not exceed `target`."""
    neg = scores[~y]
    if len(neg) == 0:
        return float(scores.max())
    return float(np.quantile(neg, 1 - target))


def run(df: pd.DataFrame, segment: str = "product_code",
        budget: float | None = None) -> tuple[pd.DataFrame, dict]:
    budget = config.ALERT_BUDGET if budget is None else budget
    global_thr = metrics.threshold_at_budget(df["pred"].to_numpy(), budget)

    groups = [(g, s) for g, s in df.groupby(segment, observed=True)
              if len(s) >= 500 and s["isFraud"].nunique() > 1]
    if len(groups) < 2:
        raise ValueError(f"not enough usable groups in {segment}")

    # Targets for the two equalising policies, taken from the global policy so
    # all three cost roughly the same review capacity and remain comparable.
    base = {g: _rates(s["isFraud"].to_numpy().astype(bool),
                      s["pred"].to_numpy() >= global_thr) for g, s in groups}
    target_sel = float(np.mean([v["selection_rate"] for v in base.values()]))
    target_fpr = float(np.mean([v["FPR"] for v in base.values()]))

    rows = []
    for g, s in groups:
        y = s["isFraud"].to_numpy().astype(bool)
        sc = s["pred"].to_numpy()
        policies = {
            "global threshold": global_thr,
            "equal selection rate": _threshold_for_selection(sc, target_sel),
            "equal FPR": _threshold_for_fpr(sc, y, target_fpr),
        }
        for name, thr in policies.items():
            r = _rates(y, sc >= thr)
            rows.append({
                "policy": name, "group": str(g), "n": len(s),
                "base_rate": float(y.mean()), "threshold": thr, **r,
                # Calibration under a per-group threshold: the same score now
                # means a different decision depending on group membership.
                "mean_pred_flagged": float(sc[sc >= thr].mean()) if (sc >= thr).any() else np.nan,
            })
    out = pd.DataFrame(rows)

    summary = {}
    for name, sub in out.groupby("policy", observed=True):
        summary[name] = {
            "selection_spread_pp": float((sub["selection_rate"].max()
                                          - sub["selection_rate"].min()) * 100),
            "FPR_spread_pp": float((sub["FPR"].max() - sub["FPR"].min()) * 100),
            "TPR_spread_pp": float((sub["TPR"].max() - sub["TPR"].min()) * 100),
            "threshold_spread": float(sub["threshold"].max() - sub["threshold"].min()),
            "same_score_same_decision": bool(sub["threshold"].nunique() == 1),
            "fraud_caught": int((sub["TPR"] * sub["base_rate"] * sub["n"]).sum()),
        }
    return out, {"segment": segment, "budget": budget,
                 "target_selection": target_sel, "target_fpr": target_fpr,
                 "policies": summary}
