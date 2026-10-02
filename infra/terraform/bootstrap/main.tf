terraform {
  required_version = "= 1.13.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.16.0" }
  }
}

variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Use the explicitly approved 12-digit AWS account ID."
  }
}
variable "region" {
  type = string
  validation {
    condition     = can(regex("^(us|eu|ap|ca|sa|af|me|il|mx)-[a-z]+-[0-9]+$", var.region))
    error_message = "Use a commercial AWS region supported by the SQS adapter."
  }
}
variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Choose dev, staging or prod; use separate accounts for production."
  }
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags {
    tags = { Project = "runveil", Environment = var.environment, ManagedBy = "terraform" }
  }
}
locals {
  bucket = "runveil-${var.account_id}-${var.region}-${var.environment}-state"
}
resource "aws_s3_bucket" "state" {
  bucket        = local.bucket
  force_destroy = false
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = terraform.workspace == "default"
      error_message = "Use separate state roots, not Terraform workspaces."
    }
  }
}
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
output "bucket" { value = aws_s3_bucket.state.id }
