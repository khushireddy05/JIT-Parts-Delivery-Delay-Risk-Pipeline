terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # For a real deployment, store state remotely so CI and humans share it.
  # Left commented so `terraform init` works locally with no S3 bucket.
  #
  # backend "s3" {
  #   bucket = "jit-parts-tfstate"
  #   key    = "jit-parts/terraform.tfstate"
  #   region = "eu-central-1"
  # }
}
