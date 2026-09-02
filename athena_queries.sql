-- Example Athena queries against the curated Glue table.
-- Workgroup + database come from the Terraform outputs (athena_workgroup, glue_database).
-- These are the ELT-side of the story: the same risk logic could live here as SQL
-- instead of in pandas/Spark, running directly on the raw layer.

-- 1. Current delay-risk breakdown
SELECT risk_level, COUNT(*) AS deliveries
FROM deliveries_risk
GROUP BY risk_level
ORDER BY deliveries DESC;

-- 2. Supplier on-time rate (share of deliveries not MEDIUM/HIGH/LATE)
SELECT
  supplier_name,
  COUNT(*)                                                              AS total,
  SUM(CASE WHEN risk_level IN ('MEDIUM', 'HIGH', 'LATE') THEN 1 ELSE 0 END) AS at_risk,
  ROUND(
    1.0 - (SUM(CASE WHEN risk_level IN ('MEDIUM','HIGH','LATE') THEN 1 ELSE 0 END) * 1.0 / COUNT(*)),
    3
  ) AS on_time_rate
FROM deliveries_risk
GROUP BY supplier_name
ORDER BY on_time_rate ASC;

-- 3. The parts most exposed right now (in transit + HIGH risk), worst slip first
SELECT po_id, supplier_name, part_desc, carrier, slip_hours, promised_delivery_ts
FROM deliveries_risk
WHERE delivery_status = 'IN_TRANSIT' AND risk_level = 'HIGH'
ORDER BY slip_hours DESC;
