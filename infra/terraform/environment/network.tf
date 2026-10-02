resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = local.name }
  lifecycle {
    precondition {
      condition     = terraform.workspace == "default"
      error_message = "Use separate environment state roots, not workspaces."
    }
  }
}
resource "aws_default_security_group" "closed" {
  vpc_id = aws_vpc.main.id
}
resource "aws_subnet" "database" {
  for_each                = { for index, az in var.availability_zones : az => index }
  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, each.value)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-database-${each.key}" }
}
resource "aws_route_table" "isolated" { vpc_id = aws_vpc.main.id }
resource "aws_route_table_association" "database" {
  for_each       = aws_subnet.database
  subnet_id      = each.value.id
  route_table_id = aws_route_table.isolated.id
}
resource "aws_security_group" "client" {
  for_each    = toset(["api", "worker", "migration"])
  name        = "${local.name}-${each.key}-database-client"
  description = "Database-only access boundary for ${each.key}; no attached compute in Phase 12A"
  vpc_id      = aws_vpc.main.id
}
resource "aws_security_group" "database" {
  name        = "${local.name}-database"
  description = "PostgreSQL from explicit application security groups only"
  vpc_id      = aws_vpc.main.id
}
resource "aws_vpc_security_group_ingress_rule" "postgres" {
  for_each                     = aws_security_group.client
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = each.value.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
resource "aws_vpc_security_group_egress_rule" "postgres" {
  for_each                     = aws_security_group.client
  security_group_id            = each.value.id
  referenced_security_group_id = aws_security_group.database.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
