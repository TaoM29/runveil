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
variable "availability_zones" {
  type = list(string)
  validation {
    condition     = length(var.availability_zones) == 2 && length(toset(var.availability_zones)) == 2 && alltrue([for az in var.availability_zones : can(regex("^${var.region}[a-z]$", az))])
    error_message = "Supply two distinct standard availability zones in the selected region."
  }
}
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 8, 1)) && can(regex("^10\\.[0-9]+\\.0\\.0/16$", var.vpc_cidr))
    error_message = "Use a canonical private 10.x.0.0/16 network."
  }
}
variable "postgres_version" {
  description = "Explicit RDS PostgreSQL 17 minor version, verified available in the target region before apply."
  type        = string
  validation {
    condition     = can(regex("^17\\.[0-9]+$", var.postgres_version))
    error_message = "Pin a PostgreSQL 17 minor version, matching the local major version."
  }
}
variable "allow_database_destroy" {
  type    = bool
  default = false
  validation {
    condition     = !var.allow_database_destroy || var.environment != "prod"
    error_message = "Production deletion protection requires a reviewed code change."
  }
}
variable "final_snapshot_suffix" {
  type    = string
  default = "retained"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{0,19}$", var.final_snapshot_suffix))
    error_message = "Use a short alphanumeric suffix beginning with a letter."
  }
}

variable "enable_private_runtime" {
  description = "Provision private compute dependencies. Creates chargeable VPC endpoints even at zero replicas."
  type        = bool
  default     = false
}
variable "runtime_image_digest" {
  description = "Digest of the reviewed linux/amd64 image pushed to this environment's ECR repository."
  type        = string
  default     = null
  validation {
    condition     = var.runtime_image_digest == null ? true : can(regex("^sha256:[0-9a-f]{64}$", var.runtime_image_digest)) && var.enable_private_runtime
    error_message = "Enable the runtime and provide an immutable sha256 digest, never a tag."
  }
}
variable "migration_image_digest" {
  description = "Operator attestation: the migration task for exactly this image exited successfully."
  type        = string
  default     = null
}
variable "activate_runtime" {
  description = "Start one API, relay and consumer after the matching migration task succeeds."
  type        = bool
  default     = false
  validation {
    condition     = !var.activate_runtime || (var.enable_private_runtime && var.runtime_image_digest != null && var.migration_image_digest == var.runtime_image_digest)
    error_message = "Activation requires the deployed image's successful migration attestation."
  }
}
