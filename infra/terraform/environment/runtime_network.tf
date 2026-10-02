locals {
  runtime_actors = var.enable_private_runtime ? toset(["api", "worker", "relay", "migration"]) : toset([])
  interface_services = var.enable_private_runtime ? toset([
    "ecr.api", "ecr.dkr", "logs", "secretsmanager", "sqs"
  ]) : toset([])
}
resource "aws_subnet" "application" {
  for_each                = var.enable_private_runtime ? { for index, az in var.availability_zones : az => index } : {}
  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, each.value + 16)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-application-${each.key}" }
}
resource "aws_route_table" "application" {
  count  = var.enable_private_runtime ? 1 : 0
  vpc_id = aws_vpc.main.id
}
resource "aws_route_table_association" "application" {
  for_each       = aws_subnet.application
  subnet_id      = each.value.id
  route_table_id = aws_route_table.application[0].id
}
resource "aws_security_group" "endpoints" {
  count       = var.enable_private_runtime ? 1 : 0
  name        = "${local.name}-endpoints"
  description = "HTTPS from the four deployment identities only"
  vpc_id      = aws_vpc.main.id
}
resource "aws_vpc_security_group_ingress_rule" "endpoints" {
  for_each                     = local.runtime_actors
  security_group_id            = aws_security_group.endpoints[0].id
  referenced_security_group_id = aws_security_group.client[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}
resource "aws_vpc_security_group_egress_rule" "endpoints" {
  for_each                     = local.runtime_actors
  security_group_id            = aws_security_group.client[each.key].id
  referenced_security_group_id = aws_security_group.endpoints[0].id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}
resource "aws_vpc_endpoint" "interface" {
  for_each            = local.interface_services
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for az in(var.environment == "prod" ? var.availability_zones : slice(var.availability_zones, 0, 1)) : aws_subnet.application[az].id]
  security_group_ids  = [aws_security_group.endpoints[0].id]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = each.key == "sqs" ? [
      { Effect = "Allow", Principal = { AWS = [aws_iam_role.task["relay"].arn] }, Action = ["sqs:SendMessage"], Resource = [aws_sqs_queue.notifications.arn] },
      { Effect = "Allow", Principal = { AWS = [aws_iam_role.task["worker"].arn] }, Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage"], Resource = [aws_sqs_queue.notifications.arn] }
      ] : [{
        Effect    = "Allow"
        Principal = { AWS = [for role in aws_iam_role.execution : role.arn] }
        Action    = each.key == "secretsmanager" ? ["secretsmanager:GetSecretValue"] : each.key == "logs" ? ["logs:CreateLogStream", "logs:PutLogEvents"] : ["ecr:GetAuthorizationToken", "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
        Resource  = each.key == "secretsmanager" ? concat([for secret in aws_secretsmanager_secret.runtime : secret.arn], [aws_db_instance.main.master_user_secret[0].secret_arn]) : each.key == "logs" ? [for log in aws_cloudwatch_log_group.runtime : "${log.arn}:*"] : ["*"]
    }]
  })
}
resource "aws_vpc_endpoint" "image_layers" {
  count             = var.enable_private_runtime ? 1 : 0
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.application[0].id]
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = "*", Action = "s3:GetObject", Resource = "arn:aws:s3:::prod-${var.region}-starport-layer-bucket/*" }]
  })
}
resource "aws_vpc_security_group_egress_rule" "image_layers" {
  for_each          = local.runtime_actors
  security_group_id = aws_security_group.client[each.key].id
  prefix_list_id    = aws_vpc_endpoint.image_layers[0].prefix_list_id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
resource "aws_security_group" "api_operator" {
  count       = var.enable_private_runtime ? 1 : 0
  name        = "${local.name}-api-operator"
  description = "Unattached private API client boundary; attaching it is an operator privilege"
  vpc_id      = aws_vpc.main.id
}
resource "aws_vpc_security_group_egress_rule" "api_operator" {
  count                        = var.enable_private_runtime ? 1 : 0
  security_group_id            = aws_security_group.api_operator[0].id
  referenced_security_group_id = aws_security_group.client["api"].id
  ip_protocol                  = "tcp"
  from_port                    = 8443
  to_port                      = 8443
}
resource "aws_vpc_security_group_ingress_rule" "api" {
  count                        = var.enable_private_runtime ? 1 : 0
  security_group_id            = aws_security_group.client["api"].id
  referenced_security_group_id = aws_security_group.api_operator[0].id
  ip_protocol                  = "tcp"
  from_port                    = 8443
  to_port                      = 8443
}
