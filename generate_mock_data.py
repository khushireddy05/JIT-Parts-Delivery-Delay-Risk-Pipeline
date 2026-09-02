"""Generate mock raw data for the JIT Parts Delivery Delay-Risk pipeline.

Simulates three raw sources that would exist in a real automotive plant:

  1. purchase_orders.csv  - SAP purchase orders (what parts were ordered, when they are due)
  2. carrier_tracking.csv  - carrier / freight-forwarder ETA feed (current estimated arrival)
  3. dock_scans.csv        - plant inbound dock scans (what has physically arrived)

Everything is deterministic given --seed so the pipeline is reproducible in a demo.

Usage:
    python generate_mock_data.py --out data/raw --orders 500 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

SUPPLIERS = [
    ("SUP-1001", "Bosch",            0.04),   # (id, name, base late-probability)
    ("SUP-1002", "Continental",      0.06),
    ("SUP-1003", "ZF Friedrichshafen", 0.09),
    ("SUP-1004", "Mahle",            0.12),
    ("SUP-1005", "Hella",            0.18),   # the unreliable one
]

PARTS = [
    ("PN-BRK-100", "Brake caliper"),
    ("PN-ALT-200", "Alternator"),
    ("PN-SNS-300", "Wheel speed sensor"),
    ("PN-HRN-400", "Wiring harness"),
    ("PN-LMP-500", "Headlamp module"),
]

CARRIERS = ["DHL Freight", "DB Schenker", "Kuehne+Nagel", "DSV"]


def daterange_start(days_back: int = 17) -> datetime:
    # anchor everything to a fixed "now" so output is stable
    now = datetime(2026, 3, 2, 6, 0, 0)
    return now - timedelta(days=days_back)


def generate(out_dir: Path, n_orders: int, seed: int) -> None:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    start = daterange_start()
    orders = []
    tracking = []
    scans = []

    for i in range(1, n_orders + 1):
        po_id = f"PO-{100000 + i}"
        sup_id, sup_name, base_late_p = rng.choice(SUPPLIERS)
        part_no, part_desc = rng.choice(PARTS)
        qty = rng.choice([12, 24, 48, 96, 144])

        order_date = start + timedelta(
            days=rng.randint(0, 14), hours=rng.randint(0, 9)
        )
        # promised lead time 3-7 days
        promised_date = order_date + timedelta(days=rng.randint(3, 7))

        orders.append(
            {
                "po_id": po_id,
                "supplier_id": sup_id,
                "supplier_name": sup_name,
                "part_no": part_no,
                "part_desc": part_desc,
                "quantity": qty,
                "order_ts": order_date.isoformat(timespec="seconds"),
                "promised_delivery_ts": promised_date.isoformat(timespec="seconds"),
                "plant_id": "munich",
            }
        )

        # ---- carrier tracking: a current ETA, sometimes already slipped ----
        is_late = rng.random() < base_late_p
        slip_hours = 0
        if is_late:
            slip_hours = rng.choice([6, 12, 18, 24, 36, 48])
        elif rng.random() < 0.15:
            # minor slip inside the grace window - not a real breach
            slip_hours = rng.choice([1, 2, 3])

        eta = promised_date + timedelta(hours=slip_hours)
        # a few shipments have no tracking yet (carrier hasn't scanned pickup)
        has_tracking = rng.random() > 0.05
        if has_tracking:
            tracking.append(
                {
                    "po_id": po_id,
                    "carrier": rng.choice(CARRIERS),
                    "tracking_no": f"TRK{rng.randint(10**9, 10**10 - 1)}",
                    "current_eta_ts": eta.isoformat(timespec="seconds"),
                    "last_event": rng.choice(
                        ["PICKED_UP", "IN_TRANSIT", "AT_HUB", "OUT_FOR_DELIVERY"]
                    ),
                    "last_event_ts": (
                        order_date + timedelta(days=rng.randint(1, 3))
                    ).isoformat(timespec="seconds"),
                }
            )

        # ---- dock scans: only for shipments that have actually arrived ----
        # arrived if ETA is in the past relative to our fixed "now"
        now = datetime(2026, 3, 2, 6, 0, 0)
        if eta <= now and rng.random() > 0.05:
            actual = eta + timedelta(hours=rng.choice([-4, -3, -2, -1, 0, 0, 1]))
            scans.append(
                {
                    "po_id": po_id,
                    "dock_door": f"D{rng.randint(1, 12):02d}",
                    "scan_ts": actual.isoformat(timespec="seconds"),
                    "received_qty": qty
                    if rng.random() > 0.03
                    else qty - rng.choice([1, 2, 4]),  # rare short shipment
                }
            )

    _write_csv(out_dir / "purchase_orders.csv", orders)
    _write_csv(out_dir / "carrier_tracking.csv", tracking)
    _write_csv(out_dir / "dock_scans.csv", scans)

    print(f"Wrote {len(orders)} purchase orders   -> {out_dir/'purchase_orders.csv'}")
    print(f"Wrote {len(tracking)} carrier records   -> {out_dir/'carrier_tracking.csv'}")
    print(f"Wrote {len(scans)} dock scans        -> {out_dir/'dock_scans.csv'}")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/raw", help="output directory for raw CSVs")
    ap.add_argument("--orders", type=int, default=500, help="number of purchase orders")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    args = ap.parse_args()
    generate(Path(args.out), args.orders, args.seed)


if __name__ == "__main__":
    main()
