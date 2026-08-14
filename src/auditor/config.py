"""Configuration for the audit.

The model under audit is the one from https://github.com/aghasalim/ieee-fraud-ml,
scored under its honest validation setup (chronological folds, 30-day embargo,
fold-local encodings). Auditing a model on predictions from a leaky split would
measure the leak, not the fairness.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

# Sibling checkout of the model repo. Only used by `make export`, which
# regenerates row-level predictions locally; nothing row-level is committed.
FRAUD_REPO = Path(os.getenv("FRAUD_REPO", Path.home() / "ieee-fraud-ml"))
SCORED = DATA / "scored.parquet"

SEED = 42

# Operating point. A fraud model is not used at p>0.5 -- a review team works a
# queue of fixed size, so every disparity below is measured at the threshold
# that flags this fraction of transactions. Fairness at an unused threshold is
# not a fairness result.
ALERT_BUDGET = float(os.getenv("ALERT_BUDGET", "0.01"))

# The four-fifths rule: a selection rate under 80% of the most-selected group's
# is the long-standing US evidentiary threshold for disparate impact. It has no
# formal status in the AI Act, which sets no numeric bar at all -- it is used
# here as a published reference point, and labelled as one.
FOUR_FIFTHS = 0.8

# Segments that are *proxies*, not protected attributes. IEEE-CIS contains no
# race, sex, age or nationality, which is the central finding of this audit
# rather than a caveat to it. See docs/ai_act_mapping.md and the README.
SEGMENTS = {
    "card_type": "debit vs credit — credit access tracks income and credit history",
    "email_class": "free webmail vs corporate/paid — a coarse socioeconomic proxy",
    "device_type": "mobile vs desktop — mobile-only users skew lower-income",
    "product_code": "product line; base fraud rate varies 5.7x across these",
    "identity_present": "whether the merchant collected identity data at all",
    "amount_band": "transaction size, a spending-power proxy",
    "region": "billing country (addr2)",
}
