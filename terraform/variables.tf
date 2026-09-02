variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-central-1"
}

variable "plant_id" {
  description = "Identifier of the production plant this pipeline serves (e.g. munich, regensburg)"
  type        = string
  default     = "munich"

  validation {
    condition     = can(regex("^[a-z0-9-]{2,20}$", var.plant_id))
    error_message = "plant_id must be 2-20 chars, lowercase letters, digits or hyphens."
  }
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "glue_worker_type" {
  description = "Glue job worker size"
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Number of Glue workers for the ETL job"
  type        = number
  default     = 2
}

variable "risk_threshold_hours" {
  description = "Projected slip (hours) at/above which a delivery is flagged HIGH risk. Passed to the Glue job as --risk_threshold_hours."
  type        = number
  default     = 12
}

variable "pandas_layer_arn" {
  description = "ARN of the AWS SDK for pandas Lambda layer (supplies pandas + awswrangler to the API). Region-specific; leave empty to skip attaching a layer. See https://aws-sdk-pandas.readthedocs.io/en/stable/layers.html"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Extra tags applied to every taggable resource"
  type        = map(string)
  default     = {}
}
