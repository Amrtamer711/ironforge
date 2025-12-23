/*
Uncomment this backend block AFTER you apply ./bootstrap to create the remote
state bucket and lock table. */

terraform {
  backend "s3" {
    bucket         = "mmg-global-terraform-state-bucket-t585"
    key            = "bootstrap/terraform.tfstate"
    region         = "eu-north-1"
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}

