/*
Remote state backend (S3 + DynamoDB locking)

Keep this commented out so a plain `terraform init` works without AWS access.
After applying `./bootstrap`, uncomment this block and run
`terraform init -reconfigure`. */

terraform {
  backend "s3" {
    bucket         = "mmg-global-terraform-state-bucket-t585"
    key            = "bootstrap/terraform.tfstate"
    region         = "eu-north-1"
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}
