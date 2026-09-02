"""AWS Glue (PySpark) version of the delay-risk ETL.

Same logic as the local etl.py, expressed in Spark so it runs on Glue against
data in S3 instead of local CSVs:

    raw/purchase_orders  +  raw/carrier_tracking  +  raw/dock_scans
        -> join on po_id
        -> derive delivery_status, slip_hours, risk_level
        -> write curated/deliveries_risk/  (and register/refresh the Glue table)

Job parameters (set as --key value in the Glue job default_arguments / Terraform):
    --raw_path              s3://bucket/raw/
    --curated_path          s3://bucket/curated/deliveries_risk/
    --risk_threshold_hours  12
    --glue_database         jit_parts_munich_dev_catalog

This file is uploaded to S3 by Terraform and referenced as the job's script_location.
It is not exercised by the local demo run (that uses etl.py); it is here so the
infrastructure points at real, reviewable job code.
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

ARGS = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "raw_path", "curated_path", "risk_threshold_hours", "glue_database"],
)

GRACE_HOURS = 2.0
threshold = float(ARGS["risk_threshold_hours"])

sc = SparkContext()
glue_ctx = GlueContext(sc)
spark = glue_ctx.spark_session
job = Job(glue_ctx)
job.init(ARGS["JOB_NAME"], ARGS)

raw = ARGS["raw_path"].rstrip("/")

orders = (
    spark.read.option("header", True).csv(f"{raw}/purchase_orders.csv")
    .withColumn("quantity", F.col("quantity").cast("int"))
    .withColumn("order_ts", F.to_timestamp("order_ts"))
    .withColumn("promised_delivery_ts", F.to_timestamp("promised_delivery_ts"))
)

tracking = (
    spark.read.option("header", True).csv(f"{raw}/carrier_tracking.csv")
    .select(
        "po_id",
        "carrier",
        "last_event",
        F.to_timestamp("current_eta_ts").alias("current_eta_ts"),
    )
)

scans = (
    spark.read.option("header", True).csv(f"{raw}/dock_scans.csv")
    .select(
        "po_id",
        F.to_timestamp("scan_ts").alias("scan_ts"),
        F.col("received_qty").cast("int").alias("received_qty"),
    )
)

df = orders.join(tracking, "po_id", "left").join(scans, "po_id", "left")

df = df.withColumn(
    "delivery_status",
    F.when(F.col("scan_ts").isNotNull(), F.lit("ARRIVED"))
    .when(F.col("current_eta_ts").isNotNull(), F.lit("IN_TRANSIT"))
    .otherwise(F.lit("NO_TRACKING")),
)

df = df.withColumn(
    "effective_arrival_ts", F.coalesce("scan_ts", "current_eta_ts")
)

df = df.withColumn(
    "slip_hours",
    F.round(
        (
            F.col("effective_arrival_ts").cast("long")
            - F.col("promised_delivery_ts").cast("long")
        )
        / 3600.0,
        1,
    ),
)

df = df.withColumn(
    "risk_level",
    F.when(
        F.col("delivery_status") == "ARRIVED",
        F.when(F.col("slip_hours") > GRACE_HOURS, F.lit("LATE")).otherwise(F.lit("ON_TIME")),
    )
    .when(
        (F.col("delivery_status") == "NO_TRACKING") | F.col("slip_hours").isNull(),
        F.lit("MEDIUM"),
    )
    .when(F.col("slip_hours") >= threshold, F.lit("HIGH"))
    .when(F.col("slip_hours") >= threshold / 2, F.lit("MEDIUM"))
    .otherwise(F.lit("LOW")),
)

df = (
    df.withColumn("short_shipment", F.col("received_qty").isNotNull() & (F.col("received_qty") < F.col("quantity")))
    .withColumn("risk_threshold_hours", F.lit(threshold))
    .withColumn("processed_ts", F.current_timestamp())
)

(
    df.coalesce(1)
    .write.mode("overwrite")
    .option("header", True)
    .csv(ARGS["curated_path"])
)

# Make the fresh data visible to Athena.
spark.sql(f"MSCK REPAIR TABLE `{ARGS['glue_database']}`.deliveries_risk")

job.commit()
