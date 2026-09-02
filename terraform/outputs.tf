output "data_bucket" {
  description = "S3 data-lake bucket name"
  value       = aws_s3_bucket.data.id
}

output "raw_prefix" {
  description = "Where the mock/raw sources land"
  value       = "s3://${aws_s3_bucket.data.id}/raw/"
}

output "curated_prefix" {
  description = "Where the Glue job writes the curated delay-risk dataset"
  value       = "s3://${aws_s3_bucket.data.id}/curated/deliveries_risk/"
}

output "glue_job_name" {
  description = "Name of the Glue ETL job"
  value       = aws_glue_job.etl.name
}

output "glue_database" {
  description = "Glue Data Catalog database backing Athena queries"
  value       = aws_glue_catalog_database.this.name
}

output "athena_workgroup" {
  description = "Athena workgroup for querying the curated data"
  value       = aws_athena_workgroup.this.name
}

output "dashboard_url" {
  description = "CloudFront URL of the Angular dashboard"
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "dashboard_bucket" {
  description = "S3 bucket the Angular build is uploaded to"
  value       = aws_s3_bucket.site.id
}

output "api_base_url" {
  description = "HTTP API base URL (set as the front-end apiBaseUrl, or reached via CloudFront /api/*)"
  value       = aws_apigatewayv2_api.api.api_endpoint
}
