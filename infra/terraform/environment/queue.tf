resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.name}-notifications-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue" "notifications" {
  name                       = "${local.name}-notifications"
  fifo_queue                 = false
  sqs_managed_sse_enabled    = true
  max_message_size           = 1024
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 10
  visibility_timeout_seconds = 30
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 100
  })
}
resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  queue_url = aws_sqs_queue.dead_letter.url
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.notifications.arn]
  })
}
resource "aws_sqs_queue_policy" "tls" {
  for_each  = { notifications = aws_sqs_queue.notifications, dead_letter = aws_sqs_queue.dead_letter }
  queue_url = each.value.url
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Deny", Principal = "*", Action = "sqs:*", Resource = each.value.arn
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
resource "aws_iam_policy" "queue" {
  for_each = {
    relay    = ["sqs:SendMessage"]
    consumer = ["sqs:ReceiveMessage", "sqs:DeleteMessage"]
  }
  name = "${local.name}-${each.key}"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = each.value, Resource = aws_sqs_queue.notifications.arn }]
  })
}
resource "aws_cloudwatch_metric_alarm" "dead_letter" {
  alarm_name          = "${local.name}-dead-letter-messages"
  alarm_description   = "Investigate rejected or deferred notifications; no automatic redrive. Console-only until an alert destination is reviewed."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dead_letter.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}
