"""Run the audit and write the findings."""
from __future__ import annotations

import json

import pandas as pd

from . import config, impossibility, metrics


def load() -> pd.DataFrame:
    if not config.SCORED.exists():
        raise SystemExit(
            f"{config.SCORED} not found. Run `make export` (needs a checkout of "
            "ieee-fraud-ml with its data), or `make demo-data` for the synthetic "
            "stand-in that exercises the same code paths."
        )
    return pd.read_parquet(config.SCORED)


def main() -> None:
    df = load()
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    print(f"rows={len(df):,}  fraud={df['isFraud'].mean():.3%}  "
          f"alert budget={config.ALERT_BUDGET:.1%}")

    tables, summary = metrics.audit_all(df)
    print(f"threshold at budget: {summary['threshold']:.4f}\n")

    worst = []
    for seg, g in tables.items():
        d = summary["segments"][seg]
        print(f"== {seg} ==  ({config.SEGMENTS[seg]})")
        print(g[["group", "n", "base_rate", "selection_rate", "FPR", "TPR",
                 "precision", "AUC"]].to_string(index=False,
                                                float_format=lambda x: f"{x:.4f}"))
        print(f"   FPR {d['FPR_min']:.4f}-{d['FPR_max']:.4f} "
              f"({d['FPR_ratio']:.1f}x, {d['FPR_gap_pp']:.2f}pp) | "
              f"disparate impact ratio {d['disparate_impact_ratio']:.3f} "
              f"{'PASSES' if d['passes_four_fifths'] else 'FAILS'} four-fifths\n")
        g.to_csv(config.REPORTS / f"segment_{seg}.csv", index=False)
        worst.append((d["FPR_ratio"], seg, d))

    worst.sort(reverse=True)
    print("segments by FPR ratio (worst first):")
    for r, seg, d in worst:
        print(f"  {seg:18s} {r:6.1f}x   worst={d['worst_FPR_group']!r:22s} "
              f"best={d['best_FPR_group']!r}")

    imp, imp_sum = impossibility.run(df, segment="product_code")
    imp.to_csv(config.REPORTS / "impossibility.csv", index=False)
    print("\n== the three policies you can actually deploy ==")
    for name, s in imp_sum["policies"].items():
        print(f"  {name:22s} selection spread {s['selection_spread_pp']:5.2f}pp | "
              f"FPR spread {s['FPR_spread_pp']:5.2f}pp | "
              f"same score same decision: {s['same_score_same_decision']}")

    with open(config.REPORTS / "audit.json", "w") as f:
        json.dump({"n": len(df), "budget": config.ALERT_BUDGET,
                   **summary, "impossibility": imp_sum}, f, indent=2, default=float)
    print(f"\n-> {config.REPORTS}")


if __name__ == "__main__":
    main()
