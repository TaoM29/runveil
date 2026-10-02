terraform {
  required_version = "= 1.13.5"
  backend "s3" {
    key          = "foundation/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.16.0" }
  }
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags {
    tags = { Project = "runveil", Environment = var.environment, ManagedBy = "terraform" }
  }
}
locals { name = "runveil-${var.environment}" }
