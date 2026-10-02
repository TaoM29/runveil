resource "aws_ecr_repository" "runtime" {
  count                = var.enable_private_runtime ? 1 : 0
  name                 = "${local.name}-runtime"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}
resource "aws_ecr_lifecycle_policy" "runtime" {
  count      = var.enable_private_runtime ? 1 : 0
  repository = aws_ecr_repository.runtime[0].name
  policy = jsonencode({ rules = [{
    rulePriority = 1
    description  = "Expire untagged layers after seven days; preserve release tags for rollback"
    selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 }
    action       = { type = "expire" }
  }] })
}
resource "aws_secretsmanager_secret" "runtime" {
  for_each                = var.enable_private_runtime ? toset(["api-db", "worker-db", "relay-db", "api-access"]) : toset([])
  name                    = "${local.name}/${each.key}"
  recovery_window_in_days = 7
}
resource "aws_cloudwatch_log_group" "runtime" {
  for_each          = local.runtime_actors
  name              = "/runveil/${var.environment}/${each.key}"
  retention_in_days = var.environment == "prod" ? 30 : 7
}
resource "aws_ecs_cluster" "runtime" {
  count = var.enable_private_runtime ? 1 : 0
  name  = local.name
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}
locals {
  task_actors = var.runtime_image_digest == null ? toset([]) : local.runtime_actors
  task_secrets = var.enable_private_runtime ? {
    api = [
      { name = "RUNVEIL_DB_PASSWORD", valueFrom = "${aws_secretsmanager_secret.runtime["api-db"].arn}:password::" },
      { name = "RUNVEIL_TRACE_TOKEN", valueFrom = "${aws_secretsmanager_secret.runtime["api-access"].arn}:trace_token::" },
      { name = "RUNVEIL_TLS_CERTIFICATE", valueFrom = "${aws_secretsmanager_secret.runtime["api-access"].arn}:tls_certificate::" },
      { name = "RUNVEIL_TLS_KEY", valueFrom = "${aws_secretsmanager_secret.runtime["api-access"].arn}:tls_key::" }
    ]
    worker = [{ name = "RUNVEIL_DB_PASSWORD", valueFrom = "${aws_secretsmanager_secret.runtime["worker-db"].arn}:password::" }]
    relay  = [{ name = "RUNVEIL_DB_PASSWORD", valueFrom = "${aws_secretsmanager_secret.runtime["relay-db"].arn}:password::" }]
    migration = concat([
      { name = "RUNVEIL_DB_PASSWORD", valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::" },
      { name = "RUNVEIL_DB_USER", valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:username::" }
      ], [for actor in ["api", "worker", "relay"] : {
        name = "RUNVEIL_${upper(actor)}_PASSWORD", valueFrom = "${aws_secretsmanager_secret.runtime["${actor}-db"].arn}:password::"
    }])
  } : {}
}
resource "aws_ecs_task_definition" "runtime" {
  for_each                 = local.task_actors
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  volume { name = "temporary" }
  container_definitions = jsonencode([merge({
    name                   = each.key
    image                  = "${aws_ecr_repository.runtime[0].repository_url}@${var.runtime_image_digest}"
    essential              = true
    user                   = "65532:65532"
    readonlyRootFilesystem = true
    command                = [each.key == "migration" ? "migrate" : each.key]
    stopTimeout            = 120
    linuxParameters        = { initProcessEnabled = true, capabilities = { drop = ["ALL"] } }
    mountPoints            = [{ sourceVolume = "temporary", containerPath = "/tmp", readOnly = false }]
    environment = concat([
      { name = "RUNVEIL_DB_HOST", value = aws_db_instance.main.address },
      { name = "RUNVEIL_QUEUE_URL", value = aws_sqs_queue.notifications.url },
      { name = "AWS_REGION", value = var.region },
      { name = "AWS_DEFAULT_REGION", value = var.region },
      { name = "AWS_EC2_METADATA_DISABLED", value = "true" }
    ], each.key == "migration" ? [] : [{ name = "RUNVEIL_DB_USER", value = "runveil_${each.key}" }])
    secrets = local.task_secrets[each.key]
    logConfiguration = { logDriver = "awslogs", options = {
      awslogs-group         = aws_cloudwatch_log_group.runtime[each.key].name
      awslogs-region        = var.region
      awslogs-stream-prefix = "runtime"
      mode                  = "non-blocking"
      max-buffer-size       = "1m"
    } }
    }, { for key, value in {
      portMappings = [{ containerPort = 8443, protocol = "tcp" }]
      healthCheck = {
        command  = ["CMD", "python", "scripts/cloud_entrypoint.py", "healthcheck"]
        interval = 30, timeout = 5, retries = 3, startPeriod = 30
      }
  } : key => value if each.key == "api" })])
}
resource "aws_ecs_service" "runtime" {
  for_each                           = var.runtime_image_digest == null ? toset([]) : setsubtract(local.runtime_actors, toset(["migration"]))
  name                               = "${local.name}-${each.key}"
  cluster                            = aws_ecs_cluster.runtime[0].id
  task_definition                    = aws_ecs_task_definition.runtime[each.key].arn
  desired_count                      = var.activate_runtime ? 1 : 0
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  enable_execute_command             = false
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = [for subnet in aws_subnet.application : subnet.id]
    security_groups  = [aws_security_group.client[each.key].id]
    assign_public_ip = false
  }
  depends_on = [aws_iam_role_policy.execution, aws_iam_role_policy_attachment.queue, aws_vpc_endpoint.interface, aws_vpc_endpoint.image_layers]
}
output "private_runtime" {
  value = var.enable_private_runtime ? {
    repository              = aws_ecr_repository.runtime[0].repository_url
    cluster                 = aws_ecs_cluster.runtime[0].arn
    task_definitions        = { for name, task in aws_ecs_task_definition.runtime : name => task.arn }
    application_subnets     = [for subnet in aws_subnet.application : subnet.id]
    security_groups         = { for name in local.runtime_actors : name => aws_security_group.client[name].id }
    operator_security_group = aws_security_group.api_operator[0].id
    secrets                 = { for name, secret in aws_secretsmanager_secret.runtime : name => secret.arn }
  } : null
}
