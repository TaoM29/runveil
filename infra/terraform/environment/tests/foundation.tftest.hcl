mock_provider "aws" {
  mock_resource "aws_db_instance" {
    defaults = {
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:eu-west-1:123456789012:secret:test-only"
        secret_status = "active"
        kms_key_id    = "test-only"
      }]
    }
  }
}

variables {
  account_id         = "123456789012"
  region             = "eu-west-1"
  environment        = "dev"
  availability_zones = ["eu-west-1a", "eu-west-1b"]
  postgres_version   = "17.9"
}

run "private_foundation" {
  command = apply
  assert {
    condition     = length(aws_ecs_service.runtime) == 0 && length(aws_vpc_endpoint.interface) == 0 && length(aws_ecr_repository.runtime) == 0 && length(aws_secretsmanager_secret.runtime) == 0
    error_message = "Existing foundation users must not opt into compute costs implicitly."
  }

  assert {
    condition     = !aws_db_instance.main.publicly_accessible && aws_db_instance.main.storage_encrypted && aws_db_instance.main.manage_master_user_password && aws_db_instance.main.password == null
    error_message = "RDS must stay private, encrypted and use an AWS-managed administrator secret."
  }
  assert {
    condition     = aws_db_instance.main.deletion_protection && !aws_db_instance.main.skip_final_snapshot && aws_db_instance.main.backup_retention_period >= 7 && !aws_db_instance.main.delete_automated_backups
    error_message = "Default deletion and recovery protections must remain enabled."
  }
  assert {
    condition     = !aws_db_instance.main.multi_az && aws_db_instance.main.allocated_storage == 20 && aws_db_instance.main.max_allocated_storage == 0 && !aws_db_instance.main.auto_minor_version_upgrade
    error_message = "Development cost and engine drift boundaries changed."
  }
  assert {
    condition     = length(aws_route_table.isolated.route) == 0 && alltrue([for subnet in aws_subnet.database : !subnet.map_public_ip_on_launch]) && length(aws_default_security_group.closed.ingress) == 0 && length(aws_default_security_group.closed.egress) == 0
    error_message = "The database network must have no external routes, public addressing or default-group access."
  }
  assert {
    condition     = alltrue([for rule in aws_vpc_security_group_ingress_rule.postgres : rule.from_port == 5432 && rule.to_port == 5432 && rule.ip_protocol == "tcp" && rule.cidr_ipv4 == null && rule.cidr_ipv6 == null && rule.security_group_id == aws_security_group.database.id]) && length(aws_vpc_security_group_ingress_rule.postgres) == 3
    error_message = "Only the three explicit client groups may reach PostgreSQL."
  }
  assert {
    condition     = alltrue([for name, rule in aws_vpc_security_group_ingress_rule.postgres : rule.referenced_security_group_id == aws_security_group.client[name].id]) && alltrue([for rule in aws_vpc_security_group_egress_rule.postgres : rule.referenced_security_group_id == aws_security_group.database.id && rule.from_port == 5432 && rule.to_port == 5432])
    error_message = "Database ingress and client egress must be reciprocal and group-scoped."
  }
  assert {
    condition     = contains([for parameter in aws_db_parameter_group.main.parameter : "${parameter.name}=${parameter.value}"], "rds.force_ssl=1")
    error_message = "RDS must reject plaintext connections."
  }
  assert {
    condition     = !aws_sqs_queue.notifications.fifo_queue && aws_sqs_queue.notifications.max_message_size == 1024 && aws_sqs_queue.notifications.visibility_timeout_seconds == 30 && aws_sqs_queue.notifications.receive_wait_time_seconds == 10 && aws_sqs_queue.notifications.sqs_managed_sse_enabled && aws_sqs_queue.dead_letter.sqs_managed_sse_enabled
    error_message = "Queue settings must match the bounded Standard-queue adapter and use encryption."
  }
  assert {
    condition     = jsondecode(aws_sqs_queue.notifications.redrive_policy).deadLetterTargetArn == aws_sqs_queue.dead_letter.arn && jsondecode(aws_sqs_queue.notifications.redrive_policy).maxReceiveCount == 100 && aws_sqs_queue.dead_letter.message_retention_seconds > aws_sqs_queue.notifications.message_retention_seconds && jsondecode(aws_sqs_queue_redrive_allow_policy.dead_letter.redrive_allow_policy).sourceQueueArns == [aws_sqs_queue.notifications.arn]
    error_message = "Redrive must be bounded, environment-local and retain evidence longer than the source queue."
  }
  assert {
    condition     = jsondecode(aws_iam_policy.queue["relay"].policy).Statement[0].Action == ["sqs:SendMessage"] && toset(jsondecode(aws_iam_policy.queue["consumer"].policy).Statement[0].Action) == toset(["sqs:ReceiveMessage", "sqs:DeleteMessage"]) && alltrue([for policy in aws_iam_policy.queue : jsondecode(policy.policy).Statement[0].Resource == aws_sqs_queue.notifications.arn])
    error_message = "Relay and consumer must have separate queue-scoped permissions without administrative or DLQ access."
  }
  assert {
    condition     = alltrue([for policy in aws_sqs_queue_policy.tls : jsondecode(policy.policy).Statement[0].Effect == "Deny" && jsondecode(policy.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"])
    error_message = "Both queues must deny insecure transport."
  }
}

run "production_protection" {
  command = plan
  variables { environment = "prod" }
  assert {
    condition     = aws_db_instance.main.multi_az && aws_db_instance.main.backup_retention_period == 14 && aws_db_instance.main.deletion_protection
    error_message = "Production requires Multi-AZ, retained backups and deletion protection."
  }
  assert {
    condition     = aws_db_instance.main.identifier == "runveil-prod" && aws_sqs_queue.notifications.name == "runveil-prod-notifications"
    error_message = "Resource identities must remain environment-specific."
  }
}
run "reject_production_destroy" {
  command = plan
  variables {
    environment            = "prod"
    allow_database_destroy = true
  }
  expect_failures = [var.allow_database_destroy]
}
run "reject_mixed_region_subnets" {
  command = plan
  variables { availability_zones = ["eu-west-1a", "us-east-1a"] }
  expect_failures = [var.availability_zones]
}
run "reject_unsupported_partition" {
  command = plan
  variables {
    region             = "cn-north-1"
    availability_zones = ["cn-north-1a", "cn-north-1b"]
  }
  expect_failures = [var.region]
}
