resource "aws_s3_bucket" "tf_state_store" {
  bucket = var.state_bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "tf_state_store" {
  bucket = aws_s3_bucket.tf_state_store.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state_store" {
  bucket = aws_s3_bucket.tf_state_store.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state_store" {
  bucket                  = aws_s3_bucket.tf_state_store.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = var.tags
}

output "state_bucket_name" {
  value = aws_s3_bucket.tf_state_store.bucket
}

output "lock_table_name" {
  value = aws_dynamodb_table.tf_lock.name
}
