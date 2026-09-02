########################################################################
# JIT Parts Delivery Delay-Risk Pipeline — target AWS architecture
#
# Layout mirrors the local pipeline:
#   local  data/raw       ->  s3://<bucket>/raw/
#   local  etl.py         ->  Glue job (Spark/Python shell) reading raw, writing curated
#   local  data/curated   ->  s3://<bucket>/curated/
#   Glue Data Catalog     ->  makes curated data queryable from Athena
#
# Parameterized by plant_id + environment so the same config redeploys per plant.
# Written to be valid, reviewable HCL. Not applied as part of this demo.
########################################################################

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      {
        Project     = "jit-parts-delay-risk"
        Plant       = var.plant_id
        Environment = var.environment
        ManagedBy   = "terraform"
      },
      var.tags,
    )
  }
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "jit-parts-${var.plant_id}-${var.environment}"
  # S3 bucket names are globally unique; suffix with account id
  data_bucket = "${local.name_prefix}-data-${data.aws_caller_identity.current.account_id}"
  glue_db     = replace("${local.name_prefix}-catalog", "-", "_")

  # Schema of the curated deliveries_risk dataset, kept in version control
  # instead of being inferred by a Glue crawler.
  curated_columns = [
    { name = "po_id", type = "string" },
    { name = "plant_id", type = "string" },
    { name = "supplier_id", type = "string" },
    { name = "supplier_name", type = "string" },
    { name = "part_no", type = "string" },
    { name = "part_desc", type = "string" },
    { name = "quantity", type = "int" },
    { name = "received_qty", type = "int" },
    { name = "short_shipment", type = "boolean" },
    { name = "order_ts", type = "timestamp" },
    { name = "promised_delivery_ts", type = "timestamp" },
    { name = "carrier", type = "string" },
    { name = "last_event", type = "string" },
    { name = "current_eta_ts", type = "timestamp" },
    { name = "scan_ts", type = "timestamp" },
    { name = "effective_arrival_ts", type = "timestamp" },
    { name = "delivery_status", type = "string" },
    { name = "slip_hours", type = "double" },
    { name = "risk_level", type = "string" },
    { name = "risk_threshold_hours", type = "double" },
    { name = "processed_ts", type = "timestamp" },
  ]
}

########################################################################
# S3 — the data lake (raw + curated + Glue script + Athena results)
########################################################################

resource "aws_s3_bucket" "data" {
  bucket = local.data_bucket
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "expire-athena-results"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = 30
    }
  }

  rule {
    id     = "raw-to-ia"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    transition {
      days          = 60
      storage_class = "STANDARD_IA"
    }
  }
}

# Upload the Glue ETL script so the job has something to run.
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.data.id
  key    = "scripts/glue_etl.py"
  source = "${path.module}/../glue/glue_etl.py"
  etag   = filemd5("${path.module}/../glue/glue_etl.py")
}

########################################################################
# IAM — least-privilege role for the Glue job
########################################################################

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${local.name_prefix}-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

# Scoped S3 access: only this project's bucket, and write only to curated/ + scripts/ read.
data "aws_iam_policy_document" "glue_s3" {
  statement {
    sid       = "ListProjectBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }

  statement {
    sid     = "ReadRawAndScripts"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/raw/*",
      "${aws_s3_bucket.data.arn}/scripts/*",
    ]
  }

  statement {
    sid     = "WriteCuratedAndTemp"
    actions = ["s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/curated/*",
      "${aws_s3_bucket.data.arn}/tmp/*",
    ]
  }
}

resource "aws_iam_role_policy" "glue_s3" {
  name   = "s3-access"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_s3.json
}

# Glue Data Catalog + CloudWatch Logs access, scoped to this database / log group.
data "aws_iam_policy_document" "glue_catalog" {
  statement {
    sid = "GlueCatalog"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartitions",
      "glue:BatchCreatePartition",
      "glue:CreateTable",
      "glue:UpdateTable",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/${local.glue_db}",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${local.glue_db}/*",
    ]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws-glue/*"]
  }
}

resource "aws_iam_role_policy" "glue_catalog" {
  name   = "catalog-and-logs"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_catalog.json
}

########################################################################
# Glue — Data Catalog database + the ETL job
########################################################################

resource "aws_glue_catalog_database" "this" {
  name        = local.glue_db
  description = "Curated JIT parts delivery delay-risk data for plant ${var.plant_id} (${var.environment})"
}

# Table over the curated output. In a real setup a Glue crawler could infer this;
# defining it explicitly keeps the schema under version control.
resource "aws_glue_catalog_table" "deliveries_risk" {
  name          = "deliveries_risk"
  database_name = aws_glue_catalog_database.this.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification           = "csv"
    "skip.header.line.count" = "1"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data.id}/curated/deliveries_risk/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.OpenCSVSerde"
      parameters = {
        "separatorChar" = ","
        "quoteChar"     = "\""
      }
    }

    dynamic "columns" {
      for_each = local.curated_columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}

resource "aws_glue_job" "etl" {
  name         = "${local.name_prefix}-etl"
  role_arn     = aws_iam_role.glue.arn
  glue_version = "4.0"

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.data.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--raw_path"                         = "s3://${aws_s3_bucket.data.id}/raw/"
    "--curated_path"                     = "s3://${aws_s3_bucket.data.id}/curated/deliveries_risk/"
    "--risk_threshold_hours"             = tostring(var.risk_threshold_hours)
    "--glue_database"                    = aws_glue_catalog_database.this.name
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://${aws_s3_bucket.data.id}/tmp/"
  }

  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 15
  max_retries       = 1
}

# Kick the job off on a schedule (hourly) — JIT risk needs to be fresh.
resource "aws_glue_trigger" "hourly" {
  name     = "${local.name_prefix}-hourly"
  type     = "SCHEDULED"
  schedule = "cron(0 * * * ? *)"
  enabled  = var.environment == "prod"

  actions {
    job_name = aws_glue_job.etl.name
  }
}

########################################################################
# Athena — workgroup pointed at the results prefix (query layer)
########################################################################

resource "aws_athena_workgroup" "this" {
  name = local.name_prefix

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.data.id}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_alias.athena.target_key_arn
      }
    }
  }
}

resource "aws_kms_key" "athena" {
  description             = "Encrypts Athena results for ${local.name_prefix}"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "athena" {
  name          = "alias/${local.name_prefix}-athena"
  target_key_id = aws_kms_key.athena.key_id
}
