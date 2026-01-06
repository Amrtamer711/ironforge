variable "aws_region" {
  type        = string
  description = "AWS region to create the remote state resources in."
  default     = "eu-north-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Globally-unique S3 bucket name to hold Terraform state."
  default     = "mmg-global-terraform-state-bucket-t588"
}

variable "lock_table_name" {
  type        = string
  description = "DynamoDB table name for Terraform state locking."
  default     = "terraform-state-lock-t588"
}

variable "tags" {
  type        = map(string)
  description = "Tags for the bootstrap resources."
  default = {
    ManagedBy = "terraform"
  }
}
