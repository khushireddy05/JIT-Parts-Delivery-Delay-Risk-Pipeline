"""ETL for the JIT Parts Delivery Delay-Risk pipeline.

Extract : read the three raw CSV sources (purchase orders, carrier tracking, dock scans)
Transform:
    - join the sources on po_id
    - derive delivery status (ARRIVED / IN_TRANSIT / NO_TRACKING)
    - compute hours of schedule slip (ETA or actual arrival vs. promised)
    - assign a delay-risk level using a configurable threshold
Load    : write one curated CSV (deliveries_risk.csv) that the visualization layer reads

This is the ETL pattern: the transform happens here, in pandas, *before* the curated
result is written. See README section "ETL vs ELT" for the alternative.

Usage:
    python etl.py --raw data/raw --out data/curated --risk-threshold-hours 12
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

# Anchor "now" to the same fixed timestamp the mock generator uses, so the demo
# is deterministic. In a real pipeline this would be pd.Timestamp.utcnow().
NOW = pd.Timestamp("2026-03-02T06:00:00")

# deliveries arriving within this many hours of the promise are treated as on time
GRACE_HOURS = 2.0


def extract(raw_dir: Path) -> dict[str, pd.DataFrame]:
    def _read(name: str, parse_dates: list[str]) -> pd.DataFrame:
        path = raw_dir / name
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        return pd.read_csv(path, parse_dates=parse_dates)

    return {
        "orders": _read("purchase_orders.csv", ["order_ts", "promised_delivery_ts"]),
        "tracking": _read("carrier_tracking.csv", ["current_eta_ts", "last_event_ts"]),
        "scans": _read("dock_scans.csv", ["scan_ts"]),
    }


def transform(data: dict[str, pd.DataFrame], risk_threshold_hours: float) -> pd.DataFrame:
    orders = data["orders"]
    tracking = data["tracking"]
    scans = data["scans"]

    if orders.empty:
        raise ValueError("no purchase orders found - run generate_mock_data.py first")

    df = orders.merge(
        tracking[["po_id", "carrier", "current_eta_ts", "last_event"]],
        on="po_id",
        how="left",
    )
    df = df.merge(
        scans[["po_id", "scan_ts", "received_qty"]],
        on="po_id",
        how="left",
    )

    # --- delivery status ---
    def _status(row: pd.Series) -> str:
        if pd.notna(row["scan_ts"]):
            return "ARRIVED"
        if pd.notna(row["current_eta_ts"]):
            return "IN_TRANSIT"
        return "NO_TRACKING"

    df["delivery_status"] = df.apply(_status, axis=1)

    # --- effective arrival estimate: actual scan if arrived, else carrier ETA ---
    df["effective_arrival_ts"] = df["scan_ts"].fillna(df["current_eta_ts"])

    # --- schedule slip in hours (positive = late vs. promise) ---
    slip = (df["effective_arrival_ts"] - df["promised_delivery_ts"]).dt.total_seconds() / 3600.0
    df["slip_hours"] = slip.round(1)

    # --- risk level ---
    # ARRIVED late  -> already a problem (LATE)
    # no arrival estimate at all -> unknown, treat as MEDIUM (blind spot)
    # projected slip >= threshold      -> HIGH
    # projected slip >= threshold/2    -> MEDIUM
    # else                             -> LOW
    def _risk(row: pd.Series) -> str:
        status = row["delivery_status"]
        s = row["slip_hours"]
        if status == "ARRIVED":
            return "LATE" if s is not None and s > GRACE_HOURS else "ON_TIME"
        if status == "NO_TRACKING" or pd.isna(s):
            return "MEDIUM"
        if s >= risk_threshold_hours:
            return "HIGH"
        if s >= risk_threshold_hours / 2:
            return "MEDIUM"
        return "LOW"

    df["risk_level"] = df.apply(_risk, axis=1)
    df["risk_threshold_hours"] = risk_threshold_hours
    df["short_shipment"] = (
        df["received_qty"].notna() & (df["received_qty"] < df["quantity"])
    )
    df["processed_ts"] = NOW.isoformat()

    cols = [
        "po_id", "plant_id", "supplier_id", "supplier_name",
        "part_no", "part_desc", "quantity", "received_qty", "short_shipment",
        "order_ts", "promised_delivery_ts", "carrier", "last_event",
        "current_eta_ts", "scan_ts", "effective_arrival_ts",
        "delivery_status", "slip_hours", "risk_level",
        "risk_threshold_hours", "processed_ts",
    ]
    return df[cols].sort_values("promised_delivery_ts").reset_index(drop=True)


def load(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "deliveries_risk.csv"
    df.to_csv(out_path, index=False)
    return out_path


def _summary(df: pd.DataFrame) -> str:
    counts = df["risk_level"].value_counts().to_dict()
    at_risk = df["risk_level"].isin(["HIGH", "MEDIUM", "LATE"]).sum()
    lines = [
        f"  rows                : {len(df)}",
        f"  risk breakdown      : {counts}",
        f"  at-risk / late      : {at_risk} ({at_risk / len(df):.0%})",
        f"  suppliers tracked   : {df['supplier_id'].nunique()}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="data/raw", help="input dir with raw CSVs")
    ap.add_argument("--out", default="data/curated", help="output dir for curated CSV")
    ap.add_argument(
        "--risk-threshold-hours",
        type=float,
        default=12.0,
        help="projected slip (hours) at or above which a delivery is HIGH risk",
    )
    args = ap.parse_args()

    data = extract(Path(args.raw))
    df = transform(data, args.risk_threshold_hours)
    out_path = load(df, Path(args.out))

    print(f"Curated output -> {out_path}")
    print(_summary(df))


if __name__ == "__main__":
    main()
