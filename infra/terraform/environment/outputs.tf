output "database" {
  value = {
    address          = aws_db_instance.main.address
    port             = aws_db_instance.main.port
    name             = aws_db_instance.main.db_name
    admin_secret_arn = aws_db_instance.main.master_user_secret[0].secret_arn
  }
}
output "network" {
  value = {
    vpc_id                    = aws_vpc.main.id
    database_subnet_ids       = [for subnet in aws_subnet.database : subnet.id]
    database_security_group   = aws_security_group.database.id
    client_security_group_ids = { for name, group in aws_security_group.client : name => group.id }
  }
}
output "queue" {
  value = {
    url         = aws_sqs_queue.notifications.url
    arn         = aws_sqs_queue.notifications.arn
    dead_letter = aws_sqs_queue.dead_letter.url
    policy_arns = { for name, policy in aws_iam_policy.queue : name => policy.arn }
  }
}
