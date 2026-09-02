"""Read API for the delay-risk dashboard.

Serves the same three views the static report shows, as JSON, so the Angular
front-end has something to call.

Data source is pluggable:
  * local / demo     -> reads data/curated/deliveries_risk.csv  (default)
  * deployed on AWS  -> set RISK_DATA_BACKEND=athena and it runs the queries in
                        athena_queries.sql against the Glue table via boto3.

Run locally:
    ./.venv/bin/uvicorn api.app:app --reload --port 8000

Endpoints:
    GET /api/health
    GET /api/risk-breakdown      -> [{risk_level, deliveries}]
    GET /api/supplier-on-time    -> [{supplier_name, total, at_risk, on_time_rate}]
    GET /api/at-risk?limit=50    -> [{po_id, supplier_name, part_desc, carrier,
                                      slip_hours, promised_delivery_ts, risk_level}]
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

AT_RISK = {"MEDIUM", "HIGH", "LATE"}
CURATED_CSV = Path(
    os.getenv("RISK_CURATED_CSV", "data/curated/deliveries_risk.csv")
)

app = FastAPI(title="JIT Parts Delay-Risk API", version="1.0.0")

# The front-end is served from a different origin (S3/CloudFront) in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("RISK_CORS_ORIGINS", "*").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _load() -> pd.DataFrame:
    backend = os.getenv("RISK_DATA_BACKEND", "csv").lower()
    if backend == "athena":
        return _load_from_athena()
    if not CURATED_CSV.exists():
        raise FileNotFoundError(
            f"{CURATED_CSV} not found - run the pipeline (make all) first"
        )
    df = pd.read_csv(CURATED_CSV)
    df["_at_risk"] = df["risk_level"].isin(AT_RISK)
    return df


def _load_from_athena() -> pd.DataFrame:  # pragma: no cover - needs AWS
    """Run the curated-table query in Athena and return the rows.

    Uses awswrangler if available (handles the S3 result staging); the Glue
    database and Athena workgroup come from Terraform outputs, passed as env.
    """
    import awswrangler as wr  # imported lazily so local runs need no boto3

    database = os.environ["RISK_GLUE_DATABASE"]
    workgroup = os.environ["RISK_ATHENA_WORKGROUP"]
    df = wr.athena.read_sql_query(
        "SELECT * FROM deliveries_risk",
        database=database,
        workgroup=workgroup,
        ctas_approach=False,
    )
    df["_at_risk"] = df["risk_level"].isin(AT_RISK)
    return df


@app.get("/api/health")
def health() -> dict:
    df = _load()
    return {"status": "ok", "rows": int(len(df)), "backend": os.getenv("RISK_DATA_BACKEND", "csv")}


@app.get("/api/risk-breakdown")
def risk_breakdown() -> list[dict]:
    df = _load()
    order = ["LOW", "ON_TIME", "MEDIUM", "HIGH", "LATE"]
    counts = df["risk_level"].value_counts()
    return [
        {"risk_level": lvl, "deliveries": int(counts[lvl])}
        for lvl in order
        if lvl in counts.index
    ]


@app.get("/api/supplier-on-time")
def supplier_on_time() -> list[dict]:
    df = _load()
    grouped = (
        df.groupby("supplier_name")
        .agg(total=("po_id", "count"), at_risk=("_at_risk", "sum"))
        .reset_index()
    )
    grouped["on_time_rate"] = (1 - grouped["at_risk"] / grouped["total"]).round(4)
    grouped = grouped.sort_values("on_time_rate")
    return [
        {
            "supplier_name": r.supplier_name,
            "total": int(r.total),
            "at_risk": int(r.at_risk),
            "on_time_rate": float(r.on_time_rate),
        }
        for r in grouped.itertuples()
    ]


@app.get("/api/at-risk")
def at_risk(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    df = _load()
    cols = [
        "po_id", "supplier_name", "part_desc", "carrier",
        "delivery_status", "slip_hours", "promised_delivery_ts", "risk_level",
    ]
    out = (
        df[df["risk_level"].isin(["HIGH", "MEDIUM", "LATE"])]
        .sort_values("slip_hours", ascending=False)
        .head(limit)[cols]
    )
    return out.where(out.notna(), None).to_dict(orient="records")


# AWS Lambda entrypoint (API Gateway HTTP API -> Mangum -> FastAPI)
try:  # pragma: no cover
    from mangum import Mangum

    handler = Mangum(app)
except ImportError:  # pragma: no cover
    handler = None
