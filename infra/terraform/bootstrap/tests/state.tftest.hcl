mock_provider "aws" {
  override_resource {
    target          = aws_s3_bucket.state
    override_during = plan
    values = {
      id  = "runveil-123456789012-eu-west-1-dev-state"
      arn = "arn:aws:s3:::runveil-123456789012-eu-west-1-dev-state"
    }
  }
}
variables {
  account_id  = "123456789012"
  region      = "eu-west-1"
  environment = "dev"
}
run "protected_state" {
  command = plan
  assert {
    condition     = aws_s3_bucket.state.bucket == "runveil-123456789012-eu-west-1-dev-state" && !aws_s3_bucket.state.force_destroy && aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "State must have an environment-specific identity, versions and no forced deletion."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_acls && aws_s3_bucket_public_access_block.state.block_public_policy && aws_s3_bucket_public_access_block.state.ignore_public_acls && aws_s3_bucket_public_access_block.state.restrict_public_buckets && aws_s3_bucket_ownership_controls.state.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "All public access and ACL paths must be disabled."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256" && jsondecode(aws_s3_bucket_policy.state.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false" && jsondecode(aws_s3_bucket_policy.state.policy).Statement[0].Effect == "Deny"
    error_message = "State must be encrypted and reject insecure transport."
  }
}
