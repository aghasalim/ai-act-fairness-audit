"""Draw the README figures from reports/*.csv and reports/audit.json.

Reads the saved audit only -- no model, no data download.

    python scripts/make_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

FOUR_FIFTHS = 0.8


def audit() -> dict:
    return json.loads((REPORTS / "audit.json").read_text())


def four_fifths(out: Path) -> Path:
    """Every segment against the four-fifths rule.

    The disparate-impact ratio is the smallest group selection rate over the
    largest. Below 0.8 is the conventional trigger for further scrutiny, and most
    segments here are far below it -- card type sits at 0.19.
    """
    segments = audit()["segments"]
    names = sorted(segments, key=lambda k: segments[k]["disparate_impact_ratio"])
    ratios = [segments[n]["disparate_impact_ratio"] for n in names]
    positions = np.arange(len(names))

    figure, ax = plt.subplots(figsize=(9.5, 4.8))
    colours = ["#b2182b" if r < FOUR_FIFTHS else "#1a9850" for r in ratios]
    ax.barh(positions, ratios, color=colours, edgecolor="0.3", lw=0.5)
    ax.axvline(FOUR_FIFTHS, color="0.25", ls="--", lw=1.6)
    ax.text(FOUR_FIFTHS, len(names) - 0.4, "  four-fifths rule", fontsize=9,
            color="0.3")
    ax.set_yticks(positions)
    ax.set_yticklabels([n.replace("_", " ") for n in names], fontsize=9)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("disparate impact ratio (min / max selection rate)")
    failing = sum(1 for r in ratios if r < FOUR_FIFTHS)
    ax.set_title(
        f"{failing} of {len(names)} segments fall below the four-fifths "
        "threshold.",
        fontsize=10,
    )
    ax.spines[["top", "right"]].set_visible(False)
    for index, name in enumerate(names):
        ax.text(ratios[index] + 0.015, index,
                f"{segments[name]['n_groups']} groups", va="center", fontsize=7.5,
                color="0.45")
    figure.tight_layout()
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def error_gaps(out: Path) -> Path:
    """False-positive and false-negative gaps, which the selection rate hides.

    Selection-rate parity says nothing about who bears the errors. The
    false-negative gap is an order of magnitude larger than the false-positive gap
    in every segment, and it is the one a customer actually experiences as being
    wrongly declined or wrongly missed.
    """
    segments = audit()["segments"]
    names = sorted(segments, key=lambda k: segments[k]["FNR_gap_pp"])
    positions = np.arange(len(names))

    figure, ax = plt.subplots(figsize=(10, 4.8))
    ax.barh(positions - 0.2, [segments[n]["FPR_gap_pp"] for n in names], 0.4,
            label="false-positive rate gap", color="#2166ac",
            edgecolor="0.3", lw=0.4)
    ax.barh(positions + 0.2, [segments[n]["FNR_gap_pp"] for n in names], 0.4,
            label="false-negative rate gap", color="#b2182b",
            edgecolor="0.3", lw=0.4)
    ax.set_yticks(positions)
    ax.set_yticklabels([n.replace("_", " ") for n in names], fontsize=9)
    ax.set_xlabel("gap between best and worst group (percentage points)")
    ax.set_title(
        "The error a customer experiences is not the one selection-rate parity "
        "measures.",
        fontsize=10,
    )
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def impossibility(out: Path) -> Path:
    """The three fairness criteria cannot hold at once, shown rather than cited.

    Equalising selection rate, equalising false-positive rate and keeping one
    global threshold are three different policies. Each satisfies its own
    criterion and breaks the others, because the base rates differ between groups.
    """
    table = pd.read_csv(REPORTS / "impossibility.csv")
    policies = list(dict.fromkeys(table.policy))
    groups = list(dict.fromkeys(table.group))

    figure, axes = plt.subplots(1, 3, figsize=(13.5, 4.4))
    for ax, (column, label) in zip(
        axes,
        [("selection_rate", "selection rate"), ("FPR", "false-positive rate"),
         ("precision", "precision")],
        strict=True,
    ):
        width = 0.8 / len(groups)
        for offset, group in enumerate(groups):
            rows = table[table.group == group].set_index("policy").loc[policies]
            ax.bar(np.arange(len(policies)) + (offset - (len(groups) - 1) / 2) * width,
                   rows[column], width, label=f"group {group}", edgecolor="0.3",
                   lw=0.4)
        ax.set_xticks(np.arange(len(policies)))
        ax.set_xticklabels([p.replace(" ", "\n") for p in policies], fontsize=8)
        ax.set_ylabel(label)
        ax.set_title(label, fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=8)
    figure.suptitle(
        "Each policy equalises its own column and breaks the others. That is the "
        "impossibility result,\nmeasured on this model rather than cited.",
        fontsize=10, y=0.02, color="0.35",
    )
    figure.tight_layout(rect=(0, 0.07, 1, 1))
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def within_segment(out: Path) -> Path:
    """The worst segment in full, group by group.

    A ratio compresses a segment into one number. This is what the number is made
    of: selection rate, error rates and AUC for each group of the segment with the
    largest disparity.
    """
    segments = audit()["segments"]
    worst = min(segments, key=lambda k: segments[k]["disparate_impact_ratio"])
    table = pd.read_csv(REPORTS / f"segment_{worst}.csv").sort_values("selection_rate")
    positions = np.arange(len(table))

    figure, axes = plt.subplots(1, 4, figsize=(14, 4.2), sharey=True)
    for ax, (column, label) in zip(
        axes,
        [("selection_rate", "selection rate"), ("FPR", "false-positive rate"),
         ("FNR", "false-negative rate"), ("AUC", "AUC")],
        strict=True,
    ):
        ax.barh(positions, table[column], color="#2166ac", edgecolor="0.3", lw=0.4)
        ax.set_xlabel(label)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yticks(positions)
    axes[0].set_yticklabels(
        [f"{g}\nn={n:,}" for g, n in zip(table.group, table.n, strict=True)],
        fontsize=8,
    )
    figure.suptitle(
        f"Segment `{worst}`, the largest disparity in the audit.",
        fontsize=10, y=0.02, color="0.35",
    )
    figure.tight_layout(rect=(0, 0.06, 1, 1))
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def calibration(out: Path) -> Path:
    """Calibration by group, across every segment.

    A calibration ratio of 1.0 means predicted risk matches realised risk for that
    group. Departures mean the same score means different things depending on who
    it is about, which is a different failure from an error-rate gap.
    """
    segments = audit()["segments"]
    frames = []
    for name in sorted(segments):
        path = REPORTS / f"segment_{name}.csv"
        if not path.exists():
            continue
        table = pd.read_csv(path)
        table["segment"] = name
        frames.append(table)
    table = pd.concat(frames)

    figure, ax = plt.subplots(figsize=(10.5, 5.2))
    labels, values, sizes = [], [], []
    for _, row in table.iterrows():
        labels.append(f"{row.segment.replace('_', ' ')} · {row.group}")
        values.append(row.calibration_ratio)
        sizes.append(row.n)
    order = np.argsort(values)
    positions = np.arange(len(order))
    colours = ["#b2182b" if abs(values[i] - 1) > 0.25 else "#2166ac" for i in order]
    ax.barh(positions, [values[i] for i in order], color=colours,
            edgecolor="0.3", lw=0.4)
    ax.axvline(1.0, color="0.2", ls="--", lw=1.6)
    ax.set_yticks(positions)
    ax.set_yticklabels([labels[i] for i in order], fontsize=6.5)
    ax.set_xlabel("calibration ratio (realised risk / predicted risk)")
    off = sum(1 for v in values if abs(v - 1) > 0.25)
    ax.set_title(
        f"{off} of {len(values)} groups are more than 25% off calibrated.\n"
        "The same score means different things depending on the group.",
        fontsize=10,
    )
    ax.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(figure)
    return out


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for path in (
        four_fifths(FIGURES / "four-fifths.png"),
        error_gaps(FIGURES / "error-gaps.png"),
        impossibility(FIGURES / "impossibility.png"),
        within_segment(FIGURES / "worst-segment.png"),
        calibration(FIGURES / "calibration.png"),
    ):
        print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
