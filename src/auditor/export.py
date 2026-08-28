"""Regenerate out-of-fold predictions from the model repo, joined to segments.

Run locally; the output is gitignored. IEEE-CIS data is not redistributable, so
this repo commits only aggregated audit results. The synthetic fallback in
`data.py` keeps the analysis code runnable and testable without it.

Predictions come from the model repo's *honest* configuration, chronological
folds with a 30-day embargo, because auditing predictions from a leaky split
would measure the leak.
"""
from __future__ import annotations

import subprocess
import sys

import pandas as pd

from . import config

FREE_MAIL = {
    "gmail.com", "yahoo.com", "hotmail.com", "aol.com", "outlook.com",
    "live.com", "msn.com", "icloud.com", "mail.com", "gmx.de", "web.de",
    "yahoo.co.uk", "hotmail.co.uk", "live.com.mx", "yahoo.com.mx",
    "hotmail.fr", "hotmail.es", "hotmail.de", "yahoo.fr", "yahoo.es",
    "yahoo.de", "outlook.es", "protonmail.com", "juno.com", "aim.com",
}


def _segments(fraud_repo) -> pd.DataFrame:
    """Read the raw string columns the model never sees as strings."""
    tx = pd.read_csv(fraud_repo / "data/raw/train_transaction.csv",
                     usecols=["TransactionID", "ProductCD", "card4", "card6",
                              "addr2", "P_emaildomain", "TransactionAmt"])
    idf = pd.read_csv(fraud_repo / "data/raw/train_identity.csv",
                      usecols=["TransactionID", "DeviceType"])
    df = tx.merge(idf, on="TransactionID", how="left")

    out = pd.DataFrame({"TransactionID": df["TransactionID"]})
    out["product_code"] = df["ProductCD"].fillna("unknown")
    out["card_network"] = df["card4"].fillna("unknown")
    out["card_type"] = df["card6"].where(df["card6"].isin(["debit", "credit"]), "unknown")

    dom = df["P_emaildomain"].str.lower()
    out["email_class"] = pd.Series("corporate/other", index=df.index)
    out.loc[dom.isin(FREE_MAIL), "email_class"] = "free webmail"
    out.loc[dom.isna(), "email_class"] = "missing"

    out["device_type"] = df["DeviceType"].fillna("unknown")
    out["identity_present"] = df["DeviceType"].notna().map({True: "yes", False: "no"})
    # addr2 is a country code; 87 dominates. Anything else is grouped, since a
    # segment with a handful of rows produces noise, not evidence.
    vc = df["addr2"].value_counts()
    big = set(vc[vc >= 2000].index)
    out["region"] = df["addr2"].where(df["addr2"].isin(big), other=-1).astype("Int64").astype(str)
    out["amount_band"] = pd.qcut(df["TransactionAmt"], 4,
                                 labels=["Q1 lowest", "Q2", "Q3", "Q4 highest"]).astype(str)
    return out


def main() -> None:
    repo = config.FRAUD_REPO
    if not (repo / "data/raw/train_transaction.csv").exists():
        sys.exit(
            f"Model repo data not found under {repo}.\n"
            "  git clone https://github.com/aghasalim/ieee-fraud-ml && cd ieee-fraud-ml\n"
            "  make setup && make data\n"
            "  then re-run with FRAUD_REPO=/path/to/ieee-fraud-ml"
        )
    # Run inside the model repo, using its own interpreter. Importing it here
    # would collide: both repos have a top-level `src` package: and this way
    # the audit depends on the model's *output*, not on its dependencies.
    print("regenerating out-of-fold predictions (honest split, 30-day embargo)...")
    raw = config.DATA / "_oof_raw.parquet"
    config.DATA.mkdir(parents=True, exist_ok=True)
    script = (
        "from src.fraud import error_analysis;"
        "d = error_analysis.oof_predictions();"
        f"d[['TransactionID','isFraud','pred','TransactionDT']].to_parquet(r'{raw}', index=False);"
        "print('oof rows', len(d))"
    )
    py = repo / ".venv/bin/python"
    proc = subprocess.run([str(py) if py.exists() else sys.executable, "-c", script],
                          cwd=str(repo), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit("model repo failed to produce predictions:\n"
                 + (proc.stderr or proc.stdout)[-2000:])
    print("  " + [l for l in proc.stdout.splitlines() if l.startswith("oof rows")][-1])
    keep = pd.read_parquet(raw)

    seg = _segments(repo)
    out = keep.merge(seg, on="TransactionID", how="left")
    config.DATA.mkdir(parents=True, exist_ok=True)
    out.to_parquet(config.SCORED, index=False)
    print(f"wrote {config.SCORED}  rows={len(out):,}  fraud={out['isFraud'].mean():.3%}")
    for s in config.SEGMENTS:
        print(f"  {s:18s} {out[s].nunique()} groups")


if __name__ == "__main__":
    main()
