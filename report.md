# Project Report — JIT Parts Delivery Delay-Risk Pipeline

**Repository:** https://github.com/khushireddy05/JIT-Parts-Delivery-Delay-Risk-Pipeline
**Status:** Complete and running locally; CI green; not deployed to AWS (by design)

---

## 1. What this project is

A data pipeline for a **Just-in-Time (JIT) automotive parts delivery** problem.

A plant running JIT holds almost no buffer stock — parts arrive shortly before
they're needed on the line. A late delivery doesn't cause a warehouse shortfall,
it stops production. So the question that matters is not *"which deliveries were
late?"* but *"which deliveries are going to be late, while there's still time to
react?"*

This pipeline answers that. It combines three raw sources, joins them per
purchase order, projects how many hours each shipment will slip against its
promised time, and assigns a risk level.

```
 SAP purchase orders ─┐
 Carrier ETA feed  ───┼──► join on po_id ──► slip_hours ──► risk_level ──► curated dataset
 Plant dock scans  ───┘                                                          │
                                                                                 ▼
                                                              report chart + API + dashboard
```

### The core idea

The interesting column is **`slip_hours` on shipments that have not arrived yet**.

- If a dock scan exists, use the real arrival time.
- If not, fall back to the carrier's current ETA (`effective_arrival_ts`
  coalesces the two).
- Compare against the promised delivery time; the difference is the slip.
- Orders with no tracking at all are surfaced as a `NO_TRACKING` blind spot
  rather than silently dropped.

Risk levels are rule-based and explainable — deliberately not ML, because the
plant needs to know *why* something is red:

| Level | Meaning |
|---|---|
| `ON_TIME` | Arrived within the 2-hour grace window |
| `LATE` | Arrived, but past the grace window |
| `LOW` | In transit, projected slip below half the threshold |
| `MEDIUM` | In transit with meaningful slip, or no tracking data |
| `HIGH` | In transit, projected slip at or above the threshold (default 12h) |

### Current output

Running on 500 mock deliveries (seed 42):

```
rows                : 500
risk breakdown      : ON_TIME 336, LOW 107, LATE 39, HIGH 13, MEDIUM 5
at-risk / late      : 57 (11%)

Supplier on-time rate:
  Hella                 78.6%   ← flagged, below the 85% target
  Mahle                 85.4%
  ZF Friedrichshafen    86.7%
  Continental           94.3%
  Bosch                 99.0%
```

Everything runs on generated mock data, so the project needs no AWS account, no
SAP connection, and no company systems to demonstrate end to end.

---

## 2. Tech stack

| Layer | Technology | Role |
|---|---|---|
| **ETL** | Python 3, pandas | Local pipeline: extract → join → risk calculation → load |
| **ETL (cloud)** | PySpark on AWS Glue | Same logic as a Glue job reading/writing S3 |
| **Reporting** | matplotlib | Static PNG report (risk breakdown + supplier rates) |
| **API** | FastAPI, Mangum | Read API; CSV backend locally, Athena backend on Lambda |
| **Front-end** | Angular 17 (standalone components) | Dashboard; CSS-only charts, no chart library |
| **Storage** | AWS S3 | Data lake — `raw/`, `curated/`, `scripts/`, `athena-results/` |
| **Catalog / query** | AWS Glue Data Catalog, Athena | Schema registry and SQL query layer |
| **Compute** | AWS Glue job, AWS Lambda | Scheduled ETL, and the read API |
| **Delivery** | CloudFront + S3, API Gateway (HTTP API) | Dashboard CDN and API front door |
| **IaC** | Terraform ~> 1.5, AWS provider ~> 5.0 | Whole architecture, parameterized per plant |
| **CI/CD** | GitHub Actions | Lint, run pipeline, smoke-test API, build Angular, validate/apply Terraform |
| **Lint** | ruff | Python linting with a pinned rule set |

### Why these choices

- **Glue over ECS/Fargate for ETL** — Glue *is* the managed Spark runtime and
  integrates directly with the Data Catalog and job bookmarks. Containers would
  add operational surface with nothing to gain at this scale.
- **Lambda over ECS for the API** — a handful of JSON endpoints with bursty,
  near-zero traffic. ECS would mean an always-on task plus an ALB for work
  Lambda handles for cents.
- **S3 + CloudFront over a server for the dashboard** — it's static files.
- **No chart library in Angular** — CSS bars keep the bundle at 180 KB
  (54 KB transferred) and the dependency tree small.
- **Rule-based risk, not ML** — explainability matters more than accuracy here,
  and there's no labelled history to train on.

---

## 3. What is done

Everything below is built **and verified**, not just written.

### Pipeline — verified end to end

| Component | Status |
|---|---|
| `generate_mock_data.py` | ✅ Generates 3 deterministic raw CSVs (500 POs, 483 carrier records, 471 dock scans) |
| `etl.py` | ✅ Runs; produces `data/curated/deliveries_risk.csv` with correct risk distribution |
| `visualize.py` | ✅ Runs headless; produces `output/risk_report.png` |
| `glue/glue_etl.py` | ⚠️ Written and reviewed — **never executed on real Spark** |

Supplier ranking comes out as designed (Hella worst at 78.6%, Bosch best at
99.0%), which confirms the risk logic behaves sensibly rather than just running
without error.

### API — verified

`api/app.py` serves four endpoints, all confirmed returning correct data locally:

- `GET /api/health` → `{"status":"ok","rows":500,"backend":"csv"}`
- `GET /api/risk-breakdown`
- `GET /api/supplier-on-time`
- `GET /api/at-risk?limit=N`

Backend is pluggable: reads the curated CSV locally, runs Athena queries when
`RISK_DATA_BACKEND=athena`. A Mangum handler makes the same app run on Lambda.

### Front-end — builds, not yet viewed

`frontend/` is an Angular 17 standalone app with three components (risk-breakdown
bars, supplier on-time bars, at-risk table with risk pills) calling the API via a
typed service.

✅ `ng build` succeeds — 180 KB initial bundle, 54 KB transferred.
⚠️ **The page has never been opened in a browser.** See §4.

### Infrastructure — valid Terraform

`terraform/` defines the full target architecture and **`terraform validate`
passes** against the real AWS provider:

- **S3 data lake** — versioned, KMS-encrypted, public access blocked, lifecycle
  rules (raw → Infrequent Access at 60 days, Athena results expire at 30)
- **IAM** — least-privilege Glue role: lists only this bucket, reads only `raw/`
  and `scripts/`, writes only `curated/` and `tmp/`, Catalog access scoped to one
  database. Separate scoped role for the API Lambda.
- **Glue** — Spark ETL job, Data Catalog database, and an explicit
  `deliveries_risk` table schema kept in version control rather than
  crawler-inferred. Hourly trigger, enabled in `prod`.
- **Athena** — workgroup with an enforced, encrypted result location
- **Lambda + HTTP API Gateway** — the read API
- **S3 + CloudFront** — private bucket with Origin Access Control for the
  dashboard; `/api/*` is a second CloudFront origin pointed at API Gateway, so
  the browser talks to a single domain

Parameterized by `plant_id` and `environment` — `terraform apply
-var="plant_id=regensburg" -var="environment=prod"` produces a fully isolated
stack.

### CI/CD — green

`.github/workflows/deploy.yml`, all four jobs passing:

1. **python-pipeline** — ruff lint, full pipeline run, assertions on the curated
   output (500 rows, valid risk levels), API smoke test, chart uploaded
2. **frontend** — `npm install` + `ng build`; on `main` with credentials, bakes in
   the real API URL, syncs to S3, invalidates CloudFront
3. **terraform** — `fmt -check`, `init`, `validate`, then `plan`/`apply` if
   credentials exist
4. **package-etl** — bundles the Glue script and syncs it to `s3://…/scripts/`

Authentication uses **GitHub OIDC role assumption**, not long-lived access keys.
Deploy steps self-skip when no `AWS_DEPLOY_ROLE_ARN` secret is present, so the
workflow stays green in a fork with no cloud account.

### Documentation

`README.md` (architecture and run instructions), `requirements.md` (scope),
`athena_queries.sql` (the ELT-side view of the same metrics), and this report.

Generated `data/` and `output/` are committed so the repository can be browsed
without running anything.

---

## 4. What is left

### Immediate — worth doing now

**Open the dashboard in a browser.** This is the only gap between "code that
builds" and "thing that has been seen working."

```bash
make api      # terminal 1 → API on :8000
make web      # terminal 2 → http://localhost:4200
```

Layout issues, a broken binding, or a CORS surprise are all still possible.

### Known untested paths

| Gap | Risk |
|---|---|
| `glue/glue_etl.py` never run on Spark | The `.coalesce(1).write.csv` path and the `MSCK REPAIR TABLE` call are the likely first failures |
| Nothing deployed to AWS | Expect the usual first-apply friction: bucket name collisions, IAM propagation delays, Glue version specifics |
| `environment.prod.ts` uses an `__API_BASE_URL__` placeholder | Only substituted by the CI deploy step — a hand-run build and manual upload would ship a broken API URL |
| No unit tests | Only CI smoke assertions exist; there is no `pytest` suite |

### To run live on AWS (~half a day)

1. Create an IAM role trusting GitHub's OIDC provider; add its ARN as the
   `AWS_DEPLOY_ROLE_ARN` repository secret
2. Create the Terraform state bucket; uncomment the `backend "s3"` block in
   `terraform/versions.tf`; `terraform init -migrate-state`
3. `terraform apply -var="plant_id=munich" -var="environment=dev"`
4. `aws s3 sync data/raw/ s3://<bucket>/raw/`
5. `aws glue start-job-run --job-name jit-parts-munich-dev-etl` — debug the
   PySpark script here
6. Query `deliveries_risk` in Athena; open the CloudFront dashboard URL

### Production hardening (days — scope, not oversight)

- **Data-quality gate** — row counts, null rates, schema drift checked before
  curated data is published; the job should fail rather than publish bad data
- **Incremental processing** — currently a full refresh every run; real version
  needs Glue bookmarks or date-partitioned raw data
- **Parquet + partitioning** for the curated layer — typed, compressed, and
  cheaper Athena scans than CSV
- **Real clock** — both ETL scripts hardcode `2026-03-02T06:00:00` so demo output
  is deterministic
- **Alerting** — CloudWatch alarm on a spike in HIGH-risk deliveries
- **Real source integration** — SAP (IDoc/OData) and carrier (EDI/API) feeds are
  the hardest real-world part and are entirely mocked here

### Explicitly out of scope

Live AWS deployment, real SAP/carrier integration, and ML-based delay prediction.
The code is written to be deploy-ready, not deployed.

---

## 5. Design notes worth knowing

**ETL vs. ELT.** What runs here is ETL — the join and risk calculation happen in
pandas/Spark *before* the curated result is written. Good for a stable,
well-understood transform at modest volume. The ELT alternative is in
`athena_queries.sql`: land raw data in S3 untouched and transform with SQL in
Athena. That's more common at scale because raw data stays intact for
reprocessing and the transform compute moves to the query engine. The
architecture supports both — raw lands in `s3://…/raw/` either way.

**Idempotency.** The job overwrites the curated output each run, so a corrected
dock scan is picked up on the next hourly run without special handling for
late-arriving data.

**Scaling path.** Partition raw and curated by date, switch the Glue job to
incremental via bookmarks, and lean ELT — push the joins into Athena or Spark SQL
over partitioned Parquet instead of loading everything.