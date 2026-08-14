"""Tests for the audit maths. Every claim in the README comes out of these
functions, so a bug here rewrites the findings rather than crashing.

All synthetic: the audit runs on non-redistributable competition data, but the
arithmetic must be checkable by anyone.
"""
import numpy as np
import pandas as pd
import pytest

from src.auditor import impossibility, metrics


def frame(n=4000, seed=0):
    """Two groups with deliberately different base rates and a ranker that is
    genuinely better on one of them."""
    rng = np.random.default_rng(seed)
    g = np.where(rng.random(n) < 0.5, "A", "B")
    base = np.where(g == "A", 0.20, 0.04)
    y = rng.binomial(1, base)
    noise = np.where(g == "A", 1.0, 3.0)
    # Squashed through a logistic rather than clipped. Clipping piles mass on
    # exactly 0 and 1, and tied scores make an exact alert budget unreachable --
    # a quantile cannot split a tie. Real predicted probabilities are
    # continuous, so the fixture should be too.
    z = y * 2.0 + rng.normal(-2.0, noise, n)
    pred = 1.0 / (1.0 + np.exp(-z))
    return pd.DataFrame({"isFraud": y, "pred": pred, "product_code": g})


def test_threshold_flags_the_requested_fraction():
    d = frame()
    thr = metrics.threshold_at_budget(d["pred"].to_numpy(), 0.01)
    assert (d["pred"] >= thr).mean() == pytest.approx(0.01, abs=0.003)


def test_group_metrics_rates_are_consistent():
    d = frame()
    g = metrics.group_metrics(d, "product_code", metrics.threshold_at_budget(d["pred"], 0.05))
    assert len(g) == 2
    for _, r in g.iterrows():
        assert r["TPR"] + r["FNR"] == pytest.approx(1.0)
        assert 0 <= r["FPR"] <= 1 and 0 <= r["selection_rate"] <= 1


def test_tiny_groups_are_dropped_not_reported():
    """A false-positive rate over 50 rows is noise; publishing it as a
    disparity would manufacture a finding."""
    d = frame()
    d.loc[d.index[:40], "product_code"] = "tiny"
    g = metrics.group_metrics(d, "product_code", 0.5, min_n=500)
    assert "tiny" not in set(g["group"])


def test_disparate_impact_ratio_is_min_over_max():
    g = pd.DataFrame({
        "group": ["A", "B"], "selection_rate": [0.10, 0.05],
        "FPR": [0.02, 0.01], "FNR": [0.5, 0.6], "AUC": [0.8, 0.7]})
    d = metrics.disparity(g)
    assert d["disparate_impact_ratio"] == pytest.approx(0.5)
    assert not d["passes_four_fifths"]
    assert d["FPR_ratio"] == pytest.approx(2.0)


def test_four_fifths_passes_when_rates_are_close():
    g = pd.DataFrame({
        "group": ["A", "B"], "selection_rate": [0.10, 0.09],
        "FPR": [0.02, 0.02], "FNR": [0.5, 0.5], "AUC": [0.8, 0.8]})
    assert metrics.disparity(g)["passes_four_fifths"]


def test_equalising_selection_rate_actually_equalises_it():
    d = frame()
    out, s = impossibility.run(d, "product_code", budget=0.05)
    assert s["policies"]["equal selection rate"]["selection_spread_pp"] < 1.0


def test_equalising_fpr_actually_equalises_it():
    d = frame()
    out, s = impossibility.run(d, "product_code", budget=0.05)
    assert s["policies"]["equal FPR"]["FPR_spread_pp"] < 1.0


def test_only_the_global_policy_gives_one_decision_per_score():
    """The core of the impossibility: buying parity costs group-dependent
    thresholds, so an identical score decides differently by group."""
    d = frame()
    _, s = impossibility.run(d, "product_code", budget=0.05)
    assert s["policies"]["global threshold"]["same_score_same_decision"]
    assert not s["policies"]["equal selection rate"]["same_score_same_decision"]
    assert not s["policies"]["equal FPR"]["same_score_same_decision"]


def test_no_policy_equalises_both_at_once():
    """If one ever did, the README's central claim would be wrong."""
    d = frame()
    _, s = impossibility.run(d, "product_code", budget=0.05)
    assert not any(p["selection_spread_pp"] < 1.0 and p["FPR_spread_pp"] < 1.0
                   for p in s["policies"].values())
