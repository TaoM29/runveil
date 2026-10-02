mock_provider "aws" {
  mock_resource "aws_iam_policy" {
    defaults = { arn = "arn:aws:iam::123456789012:policy/test" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:eu-west-1:123456789012:secret:rds-test"
        secret_status = "active"
        kms_key_id    = "test-only"
      }]
    }
  }
  override_resource {
    target = aws_iam_role.task["api"]
    values = { arn = "arn:aws:iam::123456789012:role/api-task" }
  }
  override_resource {
    target = aws_iam_role.task["worker"]
    values = { arn = "arn:aws:iam::123456789012:role/worker-task" }
  }
  override_resource {
    target = aws_iam_role.task["relay"]
    values = { arn = "arn:aws:iam::123456789012:role/relay-task" }
  }
  override_resource {
    target = aws_iam_role.task["migration"]
    values = { arn = "arn:aws:iam::123456789012:role/migration-task" }
  }
  override_resource {
    target = aws_iam_role.execution["api"]
    values = { arn = "arn:aws:iam::123456789012:role/api-execution" }
  }
  override_resource {
    target = aws_iam_role.execution["worker"]
    values = { arn = "arn:aws:iam::123456789012:role/worker-execution" }
  }
  override_resource {
    target = aws_iam_role.execution["relay"]
    values = { arn = "arn:aws:iam::123456789012:role/relay-execution" }
  }
  override_resource {
    target = aws_iam_role.execution["migration"]
    values = { arn = "arn:aws:iam::123456789012:role/migration-execution" }
  }
}
variables {
  account_id             = "123456789012"
  region                 = "eu-west-1"
  environment            = "dev"
  availability_zones     = ["eu-west-1a", "eu-west-1b"]
  postgres_version       = "17.9"
  enable_private_runtime = true
  runtime_image_digest   = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
run "staged_runtime" {
  command = apply
  assert {
    condition     = length(aws_ecs_service.runtime) == 3 && alltrue([for service in aws_ecs_service.runtime : service.desired_count == 0 && !service.network_configuration[0].assign_public_ip && !service.enable_execute_command])
    error_message = "Services must remain private and stopped until explicit activation."
  }
  assert {
    condition     = length(aws_ecs_task_definition.runtime) == 4 && alltrue([for name, task in aws_ecs_task_definition.runtime : task.execution_role_arn == aws_iam_role.execution[name].arn && task.task_role_arn == aws_iam_role.task[name].arn && task.runtime_platform[0].cpu_architecture == "X86_64" && endswith(jsondecode(task.container_definitions)[0].image, var.runtime_image_digest) && jsondecode(task.container_definitions)[0].readonlyRootFilesystem && jsondecode(task.container_definitions)[0].user == "65532:65532"])
    error_message = "Every task must use its scoped identities and a non-root, read-only, digest-pinned image."
  }
  assert {
    condition     = toset(keys(aws_iam_role_policy_attachment.queue)) == toset(["worker", "relay"]) && alltrue([for actor in ["api", "worker", "relay"] : !contains(local.secret_access[actor], aws_db_instance.main.master_user_secret[0].secret_arn)]) && length(local.secret_access.api) == 2 && length(local.secret_access.worker) == 1 && length(local.secret_access.relay) == 1
    error_message = "Only relay/consumer have SQS authority; administrator credentials must never reach a service."
  }
  assert {
    condition     = alltrue([for actor, policy in aws_iam_role_policy.execution : jsondecode(policy.policy).Statement[1].Resource == aws_ecr_repository.runtime[0].arn && toset(jsondecode(policy.policy).Statement[3].Resource) == toset(local.secret_access[actor])]) && aws_ecr_repository.runtime[0].image_tag_mutability == "IMMUTABLE"
    error_message = "Execution role access must remain repository- and secret-scoped."
  }
  assert {
    condition     = length(aws_vpc_endpoint.interface) == 5 && alltrue([for endpoint in aws_vpc_endpoint.interface : endpoint.private_dns_enabled && length(endpoint.subnet_ids) == 1]) && aws_vpc_endpoint.image_layers[0].vpc_endpoint_type == "Gateway" && length(aws_route_table.isolated.route) == 0
    error_message = "Only the required private endpoints may be added; database isolation must remain unchanged."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.api[0].from_port == 8443 && aws_vpc_security_group_ingress_rule.api[0].referenced_security_group_id == aws_security_group.api_operator[0].id && alltrue([for rule in aws_vpc_security_group_egress_rule.endpoints : rule.to_port == 443 && rule.referenced_security_group_id == aws_security_group.endpoints[0].id])
    error_message = "API access must be private-group TLS only; endpoint egress cannot become generic Internet access."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.runtime["migration"].container_definitions)[0].command == ["migrate"] && !contains(keys(aws_ecs_service.runtime), "migration") && alltrue([for actor in ["api", "worker", "relay"] : jsondecode(aws_ecs_task_definition.runtime[actor].container_definitions)[0].command == [actor]])
    error_message = "Migration must remain an explicit task, never a service or automatic startup action."
  }
}
run "activate_after_migration" {
  command = plan
  variables {
    activate_runtime       = true
    migration_image_digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  assert {
    condition     = alltrue([for service in aws_ecs_service.runtime : service.desired_count == 1 && service.deployment_maximum_percent == 100])
    error_message = "Reviewed activation must start only one instance per service without surge."
  }
}
run "reject_unmigrated_activation" {
  command = plan
  variables { activate_runtime = true }
  expect_failures = [var.activate_runtime]
}
run "reject_mutable_image" {
  command = plan
  variables { runtime_image_digest = "latest" }
  expect_failures = [var.runtime_image_digest]
}
