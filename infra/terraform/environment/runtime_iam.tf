locals {
  task_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = var.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:ecs:${var.region}:${var.account_id}:*" }
      }
    }]
  })
  secret_access = var.enable_private_runtime ? {
    api       = [aws_secretsmanager_secret.runtime["api-db"].arn, aws_secretsmanager_secret.runtime["api-access"].arn]
    worker    = [aws_secretsmanager_secret.runtime["worker-db"].arn]
    relay     = [aws_secretsmanager_secret.runtime["relay-db"].arn]
    migration = [aws_db_instance.main.master_user_secret[0].secret_arn, aws_secretsmanager_secret.runtime["api-db"].arn, aws_secretsmanager_secret.runtime["worker-db"].arn, aws_secretsmanager_secret.runtime["relay-db"].arn]
  } : {}
}
resource "aws_iam_role" "task" {
  for_each           = local.runtime_actors
  name               = "${local.name}-${each.key}-task"
  assume_role_policy = local.task_trust
}
resource "aws_iam_role" "execution" {
  for_each           = local.runtime_actors
  name               = "${local.name}-${each.key}-execution"
  assume_role_policy = local.task_trust
}
resource "aws_iam_role_policy_attachment" "queue" {
  for_each   = var.enable_private_runtime ? { worker = "consumer", relay = "relay" } : {}
  role       = aws_iam_role.task[each.key].name
  policy_arn = aws_iam_policy.queue[each.value].arn
}
resource "aws_iam_role_policy" "execution" {
  for_each = local.runtime_actors
  role     = aws_iam_role.execution[each.key].id
  name     = "image-logs-secrets"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = aws_ecr_repository.runtime[0].arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.runtime[each.key].arn}:*" },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = local.secret_access[each.key] }
    ]
  })
}
