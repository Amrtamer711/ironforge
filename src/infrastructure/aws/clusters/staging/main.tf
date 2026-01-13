terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.50"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0"
    }
    http = {
      source  = "hashicorp/http"
      version = ">= 3.4"
    }
  }

  backend "s3" {
    bucket       = "mmg-global-terraform-state-bucket-t588"
    key          = "clusters/staging/terraform.tfstate"
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}

module "cluster" {
  source = "../../modules/cluster_stack"

  project        = var.project
  environment    = var.environment
  tags           = var.tags
  vpc_cidr       = var.vpc_cidr
  az_count       = var.az_count
  eks_cluster_name = var.eks_cluster_name

  # Pass-through toggles (defaults match the demo cluster).
  enable_eks_managed_node_groups  = var.enable_eks_managed_node_groups
  enable_system_fargate_profiles  = var.enable_system_fargate_profiles
  enable_workload_fargate_profile = var.enable_workload_fargate_profile

  # RDS
  db_name              = var.db_name
  db_username          = var.db_username
  db_password          = var.db_password
  db_instance_class    = var.db_instance_class
  db_allocated_storage = var.db_allocated_storage
  db_engine_version    = var.db_engine_version
  db_publicly_accessible = var.db_publicly_accessible
}

