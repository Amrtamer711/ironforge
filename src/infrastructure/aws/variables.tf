variable "aws_region" {
  type        = string
  description = "AWS region to deploy into."
  default     = "eu-north-1"
}

variable "project" {
  type        = string
  description = "Project prefix used for naming."
  default     = "example"
}

variable "environment" {
  type        = string
  description = "Environment name (e.g., dev, stage, prod)."
  default     = "dev"
}

variable "tags" {
  type        = map(string)
  description = "Extra tags applied to all resources where supported."
  default     = {}
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block."
  default     = "10.0.0.0/16"
}

variable "az_count" {
  type        = number
  description = "How many AZs to use (2-3 typical)."
  default     = 2
}

variable "s3_bucket_names" {
  type        = list(string)
  description = "S3 bucket names to create."
  default = [
    "mmg-global-ingest-bucket-1-t586",
    "mmg-global-corpus-bucket-1-t586",
    "mmg-global-data-bucket-1-t586",
    "mmg-global-data-bucket-2-t586",
    "mmg-global-data-bucket-3-t586"
  ]
}

variable "ecr_repository_names" {
  type        = list(string)
  description = "ECR repository names to create."
  default = [
    "asset_library",
    "proposalsandbookings",
    "crm",
    "assetmaintenance",
    "staticcampaigns",
    "digitalcampaigns",
    "policyqa",
    "salescampaignsupport",
    "marketingcampaigns",
    "revenuerecognition",
    "accountsreceivable",
    "salesordermanagement",
    "testapprepo"
  ]
}

variable "eks_cluster_name" {
  type        = string
  description = "EKS cluster name."
  default     = "mmg-test-cluster-1-t586"
}

variable "kubernetes_version" {
  type        = string
  description = "EKS Kubernetes version."
  default     = "1.34"
}

variable "eks_admin_principal_arns" {
  type        = list(string)
  description = "List of IAM principal ARNs (users/roles) that should have cluster-admin access to the EKS cluster via EKS Access Entries. If empty, defaults to the Terraform caller identity ARN."
  default     = []
}

# RDS (RBAC database)
variable "db_name" {
  type        = string
  description = "Initial database name."
  default     = "rbac"
}

variable "db_username" {
  type        = string
  description = "Master username."
  default     = "rbac_admin"
}

variable "db_password" {
  type        = string
  description = "Master password (set via TF_VAR_db_password or -var)."
  sensitive   = true
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class."
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  type        = number
  description = "Allocated storage in GB."
  default     = 20
}

variable "db_engine_version" {
  type        = string
  description = "PostgreSQL engine version."
  default     = "17.7"
}

variable "db_publicly_accessible" {
  type        = bool
  description = "Whether the RDS instance is publicly accessible (recommended false)."
  default     = false
}
