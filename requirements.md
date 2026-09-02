# Requirements Document

## Project: JIT Parts Delivery Delay-Risk Pipeline

**Purpose:** A working, runnable data pipeline that flags Just-in-Time automotive
parts deliveries at risk of arriving late to the production line, covering the
full stack — ingestion, transformation, storage design, infrastructure-as-code,
and CI/CD.

---

## 1. What this project is about

A pipeline for a Just-in-Time (JIT) automotive parts delivery problem: purchase
orders, carrier delivery tracking, and plant dock scans are combined to flag
which deliveries are at risk of arriving late to the production line. It models a
real data engineering task — multiple raw data sources, a transform/risk-calculation
step, a curated output, and a visualization layer — while running fully on mock
data so it needs no live AWS account or external systems to run.

The project is intentionally small in scope but touches every layer a real
production pipeline would have: ingestion, transformation, storage design,
infrastructure-as-code, and deployment automation.

## 2. Goal

Produce a working artifact (not just a design doc): runnable pipeline code, the
infrastructure it would run on in AWS, and the CI/CD that would deploy it.

## 3. Scope

### In scope
- Mock data generation simulating 3 real sources (SAP POs, carrier ETA, dock scans)
- ETL script: extract → transform (join + risk flag) → load
- Static visualization output (risk breakdown + supplier on-time rate)
- Read API (FastAPI) over the curated data — CSV locally, Athena when deployed
- Angular dashboard consuming the API (risk breakdown, supplier rates, at-risk table)
- Terraform definition of the target AWS architecture (S3, IAM, Glue, Data Catalog, Athena, Lambda, API Gateway, CloudFront)
- A CI/CD pipeline definition (GitHub Actions) that deploys the Terraform + ETL + front-end on push
- A short ELT variant note — same pipeline, alternate pattern (see section 7)
- README explaining the architecture

### Out of scope
- Live AWS deployment (code is written to be deploy-ready, not actually deployed)
- Real SAP/carrier API integration
- ML-based delay prediction (rule-based risk threshold only)

## 4. Components

| # | Component | Covers |
|---|---|---|
| 1 | `generate_mock_data.py` | Simulated raw data sources |
| 2 | `etl.py` | ETL: extract, transform, load, with a configurable risk threshold |
| 3 | `visualize.py` | Data analytics / static visualization output |
| 4 | `glue/glue_etl.py` | PySpark port of the ETL that the Glue job runs |
| 5 | `api/` | FastAPI read API over the curated data (CSV or Athena backend) |
| 6 | `frontend/` | Angular dashboard consuming the API |
| 7 | `terraform/` | AWS infra as code: S3, IAM, Glue job + Data Catalog, Athena, Lambda, API Gateway, CloudFront |
| 8 | `.github/workflows/deploy.yml` | CI/CD: validates and deploys infra + ETL + front-end on push |
| 9 | `athena_queries.sql` | Example queries against the curated table (ELT-side view) |
| 10 | `README.md` | Explains the project and architecture |
| 11 | `requirements.md` (this file) | Defines scope |

## 5. Tech stack

- **AWS** — S3 (data lake + static site), IAM (least-privilege), Glue (ETL + Data Catalog), Athena (query layer), Lambda + API Gateway (read API), CloudFront (dashboard CDN)
- **Terraform** — infrastructure as code, parameterized by `plant_id` and `environment` so it can redeploy to multiple plants
- **CI/CD** — GitHub Actions workflow running the pipeline, an API smoke test, the Angular build, and `terraform plan`/`apply` on push to `main`
- **Data Analytics / ETL** — Python + pandas for extract/transform/load logic; matplotlib for the static report
- **API** — FastAPI + Mangum (Lambda), pandas via the AWS SDK for pandas layer
- **Front-end** — Angular 17 (standalone components), CSS-only charts, no chart library
- **ELT variant** — an alternative pattern (raw data loaded first, transformed via SQL/Athena afterward)

## 6. Success criteria

- Pipeline runs end-to-end locally with one command per stage and produces a real chart
- API serves the curated data as JSON; Angular dashboard renders it
- Terraform is valid, reviewable code — not pseudo-code — even though not deployed
- CI/CD workflow is realistic and runs if pushed to a repo with AWS credentials configured

## 7. ETL vs. ELT — why this matters and how it's covered

- **ETL** (what's built): transform happens in Python/pandas *before* loading the curated result. Good for smaller, well-understood transformations like this risk calculation.
- **ELT** (the alternative, `athena_queries.sql`): raw data is loaded into S3 as-is first, and the transformation (joins, risk calc) happens afterward via SQL in Athena or a Glue Spark job reading directly from the raw layer. This is the more common pattern at scale, because it keeps raw data intact for reprocessing and pushes transform compute to the query engine.

## 8. Implementation notes

- The scope is deliberately kept to what can be verified end-to-end: no dependency
  on real AWS credentials or real SAP/carrier systems.
- Everything is structured to read like production code — least-privilege IAM,
  parameterized Terraform, configurable thresholds, incremental-friendly design —
  even at this scale.
