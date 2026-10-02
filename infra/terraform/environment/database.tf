resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = [for subnet in aws_subnet.database : subnet.id]
}
resource "aws_db_parameter_group" "main" {
  name   = "${local.name}-postgres17"
  family = "postgres17"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}
resource "aws_db_instance" "main" {
  identifier                      = local.name
  engine                          = "postgres"
  port                            = 5432
  engine_version                  = var.postgres_version
  instance_class                  = "db.t4g.micro"
  allocated_storage               = 20
  max_allocated_storage           = 0
  storage_type                    = "gp3"
  storage_encrypted               = true
  db_name                         = "runveil"
  username                        = "runveil_admin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.main.name
  parameter_group_name            = aws_db_parameter_group.main.name
  vpc_security_group_ids          = [aws_security_group.database.id]
  publicly_accessible             = false
  multi_az                        = var.environment == "prod"
  backup_retention_period         = var.environment == "prod" ? 14 : 7
  backup_window                   = "02:00-03:00"
  maintenance_window              = "sun:04:00-sun:05:00"
  auto_minor_version_upgrade      = false
  allow_major_version_upgrade     = false
  apply_immediately               = false
  deletion_protection             = !var.allow_database_destroy
  skip_final_snapshot             = false
  final_snapshot_identifier       = "${local.name}-final-${var.final_snapshot_suffix}"
  copy_tags_to_snapshot           = true
  delete_automated_backups        = false
  enabled_cloudwatch_logs_exports = []
}
