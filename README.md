# JIT Parts Delivery — Delay-Risk Pipeline

A small but end-to-end data pipeline for a Just-in-Time automotive parts problem:
combine purchase orders, carrier tracking, and plant dock scans to flag which
inbound deliveries are at risk of arriving late to the production line.

Runs entirely on mock data — no AWS account or company systems needed — but every
layer is structured the way a production pipeline would be: ingestion, transform,
storage design, infrastructure-as-code, and CI/CD.

See [requirements.md](requirements.md) for the full scope.

---

## What's here

| Path | Role |
|---|---|
| [generate_mock_data.py](generate_mock_data.py) | Simulates 3 raw sources: SAP POs, carrier ETA feed, dock scans |
| [etl.py](etl.py) | **ETL**: extract CSVs → join + derive delay-risk → load one curated CSV |
| [visualize.py](visualize.py) | Data-analytics layer: risk breakdown + supplier on-time-rate chart |
| [glue/glue_etl.py](glue/glue_etl.py) | The same ETL as a PySpark AWS Glue job (what the infra runs) |
| [api/](api/) | FastAPI read API over the curated data (CSV locally, Athena when deployed) |
| [frontend/](frontend/) | Angular dashboard calling the API — risk breakdown, supplier rates, at-risk table |
| [terraform/](terraform/) | Target AWS architecture as code — S3, IAM, Glue, Data Catalog, Athena, Lambda, API Gateway, CloudFront |
| [.github/workflows/deploy.yml](.github/workflows/deploy.yml) | CI/CD: lint + pipeline, API smoke test, Angular build, `terraform validate`/`plan`/`apply`, deploy |
| [athena_queries.sql](athena_queries.sql) | Example queries against the curated table (the ELT-side view) |

## Run it locally

```bash
make setup      # create .venv, install pandas + matplotlib
make all        # generate_mock_data.py -> etl.py -> visualize.py
# output/risk_report.png is the result
```

Or per stage, with a configurable risk threshold:

```bash
make data
make etl RISK_THRESHOLD=8
make viz
```

### Web dashboard (local)

```bash
make all                                             # produce the curated CSV
./.venv/bin/pip install -r api/requirements.txt
./.venv/bin/uvicorn api.app:app --port 8000          # read API on :8000

cd frontend && npm install && npm start              # Angular dev server on :4200
```

Open http://localhost:4200 — the Angular app calls the API, which serves the
curated CSV. When deployed, the same API runs on Lambda with
`RISK_DATA_BACKEND=athena` and queries the Glue table instead.

### Example output

`etl.py` prints a summary; `visualize.py` writes `output/risk_report.png`:

```
  rows                : 500
  risk breakdown      : {'ON_TIME': 336, 'LOW': 107, 'LATE': 39, 'HIGH': 13, 'MEDIUM': 5}
  at-risk / late      : 57 (11%)

Supplier on-time rate:
  Hella                 78.6%   <- flagged, below 85% target
  Mahle                 85.4%
  ZF Friedrichshafen    86.7%
  Continental           94.3%
  Bosch                 99.0%
```

---

## Architecture (target AWS)

```
 SAP POs ─┐
 Carrier ─┼─► s3://…/raw/ ──► Glue job (glue_etl.py) ──► s3://…/curated/deliveries_risk/
 Scans  ─┘                                                      │
                                                                ▼
                                        Glue Data Catalog (deliveries_risk table)
                                                                │
                              ┌─────────────────────────────────┤
                              ▼                                  ▼
                    Athena (athena_queries.sql)      Lambda API (api/app.py, via Athena)
                              │                                  │
                              ▼                                  ▼
                       analysts / BI              API Gateway ─► CloudFront ─► Angular dashboard
                                                                 ▲
                                                     S3 (static Angular build)
```

- **S3** — one bucket per `plant_id` + `environment`, versioned, KMS-encrypted, public
  access blocked, lifecycle rules for raw→IA and Athena-result expiry. Prefixes:
  `raw/`, `curated/`, `scripts/`, `athena-results/`, `tmp/`.
- **IAM** — a dedicated Glue role with **least-privilege** policies: list only this
  bucket, read only `raw/` + `scripts/`, write only `curated/` + `tmp/`, and Catalog
  access scoped to this one database.
- **Glue** — a `glueetl` (Spark) job running `glue_etl.py`, plus a Data Catalog
  database and an explicit `deliveries_risk` table definition (schema in version
  control rather than crawler-inferred). Hourly scheduled trigger, enabled in `prod`.
- **Athena** — a workgroup with an enforced, encrypted result location — the query
  layer for analysts and for the API.
- **API** — `api/app.py` (FastAPI) on Lambda behind an HTTP API Gateway, with a
  least-privilege role scoped to Athena + the Glue database + the results prefix.
  pandas comes from the AWS SDK for pandas managed layer (`pandas_layer_arn` var).
- **Dashboard** — the Angular build in a private S3 bucket, served through
  CloudFront (Origin Access Control); `/api/*` is a second CloudFront origin
  pointed at the API Gateway, so the browser talks to one domain.

### Parameterized for multiple plants

Everything keys off `plant_id` and `environment`:

```bash
cd terraform
terraform apply -var="plant_id=regensburg" -var="environment=prod"
```

produces an isolated stack (`jit-parts-regensburg-prod-…`) with its own bucket,
role, Glue DB and job. See [terraform/terraform.tfvars.example](terraform/terraform.tfvars.example).

---

## CI/CD

`.github/workflows/deploy.yml` runs on every push/PR:

1. **python-pipeline** — `ruff` lint, run the full pipeline end-to-end, assert the
   curated output has 500 rows and valid `risk_level` values, smoke-test the API
   with `fastapi.testclient`, upload the chart.
2. **frontend** — `npm install` + `ng build` the Angular app; on `main` with creds,
   bake in the real API URL, `aws s3 sync` to the dashboard bucket, invalidate
   CloudFront.
3. **terraform** — `terraform fmt -check`, `init -backend=false`, `validate`. If an
   `AWS_DEPLOY_ROLE_ARN` secret is present it also assumes the role via OIDC and runs
   `plan` (and `apply` on `main`). With no secret it stops after `validate` — so the
   workflow is green in a fork with no cloud account.
4. **package-etl** (main only) — zips the Glue script and syncs it to
   `s3://…/scripts/` so the deployed job always runs the committed code.

To make it deploy for real: create an IAM role trusting GitHub's OIDC provider, add
its ARN as the `AWS_DEPLOY_ROLE_ARN` repo secret, uncomment the `backend "s3"` block
in [terraform/versions.tf](terraform/versions.tf), and create the state bucket.

---

## ETL vs. ELT

**ETL (what runs here):** the join and risk calculation happen in pandas / Spark
*before* the curated result is written. Good for well-understood transforms at
modest volume — like this one.

**ELT (the alternative, [athena_queries.sql](athena_queries.sql)):** load the raw
sources into S3 untouched, then transform with SQL in Athena (or a Glue Spark job
reading the raw layer). More common at scale — raw data stays intact for
reprocessing and the transform compute moves to the query engine. Query #2 in
`athena_queries.sql` is the supplier on-time-rate metric expressed the ELT way.

The architecture supports both: raw lands in `s3://…/raw/` regardless; ETL writes
`curated/`, ELT would point Athena views straight at `raw/`.

---

## Deliberately out of scope

Live AWS deployment, real SAP/carrier API integration, and ML-based prediction
(rule-based threshold only). The code — pipeline, API, dashboard, Terraform — is
written to be deploy-ready, not deployed. See [requirements.md](requirements.md) §3.
