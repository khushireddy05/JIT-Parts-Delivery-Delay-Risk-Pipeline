"""Visualization layer for the JIT Parts Delivery Delay-Risk pipeline.

Reads the curated CSV produced by etl.py and writes a single PNG with two panels:

  left  : delivery risk breakdown (count of deliveries by risk level)
  right : supplier on-time rate (share of that supplier's deliveries that are
          not HIGH risk / MEDIUM risk / LATE)

Usage:
    python visualize.py --curated data/curated/deliveries_risk.csv --out output/risk_report.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: works in CI with no display
import matplotlib.pyplot as plt
import pandas as pd

RISK_ORDER = ["LOW", "ON_TIME", "MEDIUM", "HIGH", "LATE"]
RISK_COLORS = {
    "LOW": "#2e7d32",
    "ON_TIME": "#66bb6a",
    "MEDIUM": "#f9a825",
    "HIGH": "#ef6c00",
    "LATE": "#c62828",
}
AT_RISK = {"MEDIUM", "HIGH", "LATE"}


def build_report(curated_csv: Path, out_path: Path) -> None:
    df = pd.read_csv(curated_csv)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.suptitle(
        "JIT Parts Delivery — Delay-Risk Report  "
        f"(plant: {df['plant_id'].iloc[0]}, "
        f"threshold: {df['risk_threshold_hours'].iloc[0]:.0f}h)",
        fontsize=13,
        fontweight="bold",
    )

    # ---- panel 1: risk breakdown ----
    counts = df["risk_level"].value_counts()
    levels = [lvl for lvl in RISK_ORDER if lvl in counts.index]
    values = [counts[lvl] for lvl in levels]
    ax1.bar(levels, values, color=[RISK_COLORS[lvl] for lvl in levels])
    for i, v in enumerate(values):
        ax1.text(i, v + max(values) * 0.01, str(v), ha="center", va="bottom", fontsize=9)
    ax1.set_title("Delivery risk breakdown")
    ax1.set_ylabel("deliveries")
    ax1.margins(y=0.15)

    # ---- panel 2: supplier on-time rate ----
    df["_at_risk"] = df["risk_level"].isin(AT_RISK)
    by_sup = (
        df.groupby("supplier_name")
        .agg(total=("po_id", "count"), at_risk=("_at_risk", "sum"))
        .assign(on_time_rate=lambda d: 1 - d["at_risk"] / d["total"])
        .sort_values("on_time_rate")
    )
    colors = ["#c62828" if r < 0.85 else "#2e7d32" for r in by_sup["on_time_rate"]]
    ax2.barh(by_sup.index, by_sup["on_time_rate"] * 100, color=colors)
    for i, row in enumerate(by_sup.itertuples()):
        ax2.text(
            row.on_time_rate * 100 + 1,
            i,
            f"{row.on_time_rate:.0%}  (n={row.total})",
            va="center",
            fontsize=8,
        )
    ax2.set_title("Supplier on-time rate")
    ax2.set_xlabel("% of deliveries not at risk")
    ax2.set_xlim(0, 115)
    ax2.axvline(85, color="grey", linestyle="--", linewidth=1)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    print(f"Report -> {out_path}")

    # also print the supplier table so the pipeline is useful headless
    print("\nSupplier on-time rate:")
    print(
        by_sup.assign(on_time_rate=lambda d: (d["on_time_rate"] * 100).round(1))
        .rename(columns={"on_time_rate": "on_time_%"})
        .to_string()
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--curated",
        default="data/curated/deliveries_risk.csv",
        help="curated CSV from etl.py",
    )
    ap.add_argument(
        "--out", default="output/risk_report.png", help="output PNG path"
    )
    args = ap.parse_args()
    build_report(Path(args.curated), Path(args.out))


if __name__ == "__main__":
    main()
