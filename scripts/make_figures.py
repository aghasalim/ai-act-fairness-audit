"""Draw the README figures from reports/*.csv and reports/audit.json.

Reads the saved audit only, no model and no data download. Every number on
every axis comes out of a committed file, so a figure cannot disagree with the
numbers quoted in the README.

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
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, NullFormatter

from style import PALETTE, titled

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

FOUR_FIFTHS = 0.8

# Red is a failed check and green is a passed one, the way the README reads the
# tables. Blue is the neutral series where nothing has passed or failed yet.
FAIL, PASSES, NEUTRAL = PALETTE[1], PALETTE[2], PALETTE[0]

# Most of these quantities span three or four decades. Every wide axis here is
# log, and everything on one is a dot, because a bar length on a log axis means
# nothing.
BUDGET = "at a fixed 1 percent alert budget"


def audit() -> dict:
    return json.loads((REPORTS / "audit.json").read_text())


def _plain_log(axis) -> None:
    """Decade ticks written as numbers, because 0.001 reads better than 10^-3."""
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    axis.set_minor_formatter(NullFormatter())


def _rows(ax, positions) -> None:
    """Faint guide per category row, so the eye can cross a wide log axis."""
    ax.set_yticks(positions)
    ax.grid(axis="y", color="#ececec", linewidth=0.7)
    ax.set_axisbelow(True)


def four_fifths(out: Path) -> Path:
    """Every segment against the four-fifths rule.

    The disparate-impact ratio is the smallest group selection rate over the
    largest. Below 0.8 is the conventional trigger for further scrutiny. The
    ratios run over three decades, so they sit on a log axis as dots rather than
    as bars whose length would be meaningless.
    """
    segments = audit()["segments"]
    names = sorted(segments, key=lambda k: segments[k]["disparate_impact_ratio"])
    ratios = [segments[n]["disparate_impact_ratio"] for n in names]
    positions = np.arange(len(names))

    figure, ax = plt.subplots(figsize=(9.5, 4.6))
    ax.set_xscale("log")
    ax.set_xlim(6e-4, 1.7)
    _rows(ax, positions)

    for index, ratio in enumerate(ratios):
        colour = PASSES if ratio >= FOUR_FIFTHS else FAIL
        ax.plot([ratio], [index], "o", markersize=9, color=colour, zorder=3)
        ax.annotate(f"{ratio:.3g}", (ratio, index), xytext=(10, 0),
                    textcoords="offset points", fontsize=9, color="#5a5a5a",
                    va="center")

    ax.axvline(FOUR_FIFTHS, color="#333333", linestyle="--", linewidth=1.4, zorder=2)
    ax.text(FOUR_FIFTHS * 1.12, (len(names) - 1) / 2, "four-fifths rule", fontsize=9,
            color="#333333", va="center", rotation=90, ha="left")

    ax.set_yticklabels([f"{n.replace('_', ' ')}\n{segments[n]['n_groups']} groups"
                        for n in names])
    _plain_log(ax.xaxis)
    ax.set_xlabel("disparate impact ratio, min / max group selection rate "
                  "(unitless, log scale)")
    titled(ax, f"Every segment falls below four-fifths, "
               f"{names[0].replace('_', ' ')} by {FOUR_FIFTHS / ratios[0]:.0f}x",
           f"{len(names)} proxy segments of {audit()['n']:,} transactions, {BUDGET}")
    figure.tight_layout()
    figure.savefig(out)
    plt.close(figure)
    return out


def error_gaps(out: Path) -> Path:
    """False-positive and false-negative gaps, which the selection rate hides.

    Selection-rate parity says nothing about who bears the errors. The two gaps
    differ by a factor of forty or more in every segment, which is a ratio, so
    the axis is log and each segment is drawn as the span between its two dots.
    """
    segments = audit()["segments"]
    names = sorted(segments, key=lambda k: segments[k]["FNR_gap_pp"])
    positions = np.arange(len(names))
    fpr = np.array([segments[n]["FPR_gap_pp"] for n in names])
    fnr = np.array([segments[n]["FNR_gap_pp"] for n in names])

    figure, ax = plt.subplots(figsize=(9.8, 4.6))
    ax.set_xscale("log")
    ax.set_xlim(0.07, 90)
    _rows(ax, positions)

    ax.hlines(positions, fpr, fnr, color="#c4c4c4", linewidth=1.6, zorder=2)
    ax.plot(fpr, positions, "o", markersize=8.5, color=NEUTRAL, zorder=3,
            label="false-positive rate gap, wrongly flagged")
    ax.plot(fnr, positions, "o", markersize=8.5, color=FAIL, zorder=3,
            label="false-negative rate gap, fraud missed")
    for index, (low, high) in enumerate(zip(fpr, fnr, strict=True)):
        ax.annotate(f"{high / low:.0f}x wider", (high, index), xytext=(11, 0),
                    textcoords="offset points", fontsize=9, color="#5a5a5a",
                    va="center")

    ax.set_yticklabels([n.replace("_", " ") for n in names])
    _plain_log(ax.xaxis)
    ax.set_xlabel("gap between the best and the worst group "
                  "(percentage points, log scale)")
    titled(ax, f"The gap in missed fraud is {(fnr / fpr).min():.0f}x to "
               f"{(fnr / fpr).max():.0f}x the gap in false alarms",
           f"a customer feels the missed error, an audit measures the other one, {BUDGET}")
    # Under the axes: every row spans the full width, so there is no free corner.
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=2)
    figure.tight_layout()
    figure.savefig(out)
    plt.close(figure)
    return out


def impossibility(out: Path) -> Path:
    """The three fairness criteria cannot hold at once, shown rather than cited.

    Equalising selection rate, equalising false-positive rate and keeping one
    global threshold are three different policies. Each line is one product code
    carried across the three, so a policy that flattens its own panel and fans
    out the next two is visible in one read.
    """
    table = pd.read_csv(REPORTS / "impossibility.csv")
    policies = list(dict.fromkeys(table.policy))
    groups = list(dict.fromkeys(table.group))
    spread = audit()["impossibility"]["policies"]
    x = np.arange(len(policies))

    figure, axes = plt.subplots(1, 3, figsize=(13.6, 5.0))
    panels = [
        ("selection_rate", "selection rate\n(% of transactions flagged, log scale)",
         True, "Only one policy flattens selection rate",
         "each line is one product code group"),
        ("FPR", "false-positive rate\n(% of legitimate transactions, log scale)",
         True, "The FPR gap more than doubles",
         "who is wrongly flagged"),
        ("precision", "precision (% of flags that really are fraud)",
         False, "No policy leaves precision alone",
         "what a flag turns out to be worth"),
    ]
    for ax, (column, label, log, title, subtitle) in zip(axes, panels, strict=True):
        for offset, group in enumerate(groups):
            rows = table[table.group == group].set_index("policy").loc[policies]
            ax.plot(x, rows[column] * 100, marker="o", color=PALETTE[offset],
                    linewidth=1.8, label=f"product code {group}")
        if log:
            ax.set_yscale("log")
            _plain_log(ax.yaxis)
        ax.set_xticks(x)
        ax.set_xticklabels([p.replace(" ", "\n") for p in policies], fontsize=9)
        ax.set_xlim(-0.35, len(policies) - 0.65)
        ax.set_ylabel(label)
        titled(ax, title, subtitle)

    # Stated rather than eyeballed off the log axis, and read from audit.json.
    axes[1].annotate(
        f"FPR spread {spread['global threshold']['FPR_spread_pp']:.2f}pp"
        f" -> {spread['equal selection rate']['FPR_spread_pp']:.2f}pp",
        xy=(0.5, 0.03), xycoords="axes fraction", fontsize=9, color="#5a5a5a",
        ha="center")

    handles = [Line2D([], [], color=PALETTE[i], marker="o", linewidth=1.8,
                      label=f"product code {g}") for i, g in enumerate(groups)]
    figure.legend(handles=handles, loc="lower center", ncol=len(groups),
                  bbox_to_anchor=(0.5, 0.0))
    figure.tight_layout(rect=(0, 0.075, 1, 1))
    figure.savefig(out)
    plt.close(figure)
    return out


def within_segment(out: Path) -> Path:
    """The worst segment in full, group by group.

    A ratio compresses a segment into one number. This is what the number is made
    of. The two rate panels are log because product code W is flagged four
    decades less often than product code C.
    """
    segments = audit()["segments"]
    worst = min(segments, key=lambda k: segments[k]["disparate_impact_ratio"])
    table = pd.read_csv(REPORTS / f"segment_{worst}.csv").sort_values("selection_rate")
    positions = np.arange(len(table))
    biggest = table.loc[table.n.idxmax()]

    figure, axes = plt.subplots(1, 4, figsize=(14, 4.4), sharey=True)
    panels = [
        ("selection_rate", 100, "selection rate\n(% flagged, log scale)", True),
        ("FPR", 100, "false-positive rate\n(% of legitimate, log scale)", True),
        ("TPR", 100, "fraud caught\n(% of fraud in the group)", False),
        ("AUC", 1, "AUC (0.5 is a coin flip)", False),
    ]
    for ax, (column, scale, label, log) in zip(axes, panels, strict=True):
        ax.plot(table[column] * scale, positions, "o", markersize=9,
                color=NEUTRAL, zorder=3)
        if log:
            ax.set_xscale("log")
            _plain_log(ax.xaxis)
            ax.set_xlim(table[column].min() * scale / 3, table[column].max() * scale * 3)
        elif column == "TPR":
            ax.set_xlim(0, None)
        else:
            ax.set_xlim(0.45, 1.0)
            ax.axvline(0.5, color="#bbbbbb", linestyle="--", linewidth=1.0, zorder=1)
        ax.set_xlabel(label)
        ax.grid(axis="y", color="#ececec", linewidth=0.7)
        ax.set_axisbelow(True)

    axes[0].set_yticks(positions)
    axes[0].set_yticklabels(
        [f"{g}\nn={n:,}" for g, n in zip(table.group, table.n, strict=True)],
        fontsize=9,
    )
    share = biggest.n / audit()["n"]
    # Lay the panels out first and reserve the top band, then write the header
    # into it. Letting tight_layout see a header wider than one panel makes it
    # give up on the whole row.
    figure.tight_layout(rect=(0, 0, 1, 0.86))
    titled(axes[0],
           f"Product code {biggest.group} is {share:.0%} of traffic and is barely "
           f"flagged at all",
           f"segment `{worst}`, the largest disparity in the audit, group by group, {BUDGET}")
    figure.savefig(out)
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
    table = pd.concat(frames).sort_values("calibration_ratio")
    values = table.calibration_ratio.to_numpy()
    positions = np.arange(len(table))

    figure, ax = plt.subplots(figsize=(10, 7.2))
    ax.axvspan(0.75, 1.25, color="#f0f0f0", zorder=0)
    ax.axvline(1.0, color="#333333", linestyle="--", linewidth=1.4, zorder=2)
    # Dot area carries the group size, which is the difference between a real
    # miscalibration and one group of 977 rows.
    sizes = 20 + 300 * np.sqrt(table.n.to_numpy() / table.n.max())
    colours = [FAIL if abs(v - 1) > 0.25 else NEUTRAL for v in values]
    ax.scatter(values, positions, s=sizes, c=colours, zorder=3, linewidths=0)

    _rows(ax, positions)
    ax.set_yticklabels(
        [f"{s.replace('_', ' ')}: {g}"
         for s, g in zip(table.segment, table.group, strict=True)],
        fontsize=8.5,
    )
    ax.set_xlim(0.38, 2.78)
    ax.set_ylim(-0.8, len(table) - 0.2)
    ax.set_xlabel("calibration ratio, realised risk / predicted risk "
                  "(unitless, 1.0 is calibrated)")
    ax.text(1.0, -0.7, "  calibrated", fontsize=9, color="#333333", va="center")
    off = int((np.abs(values - 1) > 0.25).sum())
    titled(ax, "The same score means different risk depending on the group",
           f"{off} of {len(values)} groups sit more than 25 percent from "
           f"calibrated, dot area is the group size")
    figure.tight_layout()
    figure.savefig(out)
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
        print(f"-> {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
