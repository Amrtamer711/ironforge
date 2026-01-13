variable "aws_region" {
  type        = string
  description = "AWS region to deploy into."
  default     = "eu-north-1"
}

variable "project" {
  type        = string
  description = "Project prefix used for naming."
  default     = "mmg"
}

variable "environment" {
  type        = string
  description = "Environment name."
  default     = "staging"
}

variable "tags" {
  type        = map(string)
  description = "Extra tags applied to all resources where supported."
  default     = {}
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block."
  default     = "10.10.0.0/16"
}

variable "az_count" {
  type        = number
  description = "How many AZs to use (2-3 typical)."
  default     = 2
}

variable "eks_cluster_name" {
  type        = string
  description = "EKS cluster name."
  default     = "mmg-staging-cluster-1-t588"
}

variable "enable_eks_managed_node_groups" {
  type        = bool
  description = "Whether to create EKS managed node groups (EC2 workers)."
  default     = true
}

variable "enable_system_fargate_profiles" {
  type        = bool
  description = "Whether to create the kube-system Fargate profiles (CoreDNS + AWS Load Balancer Controller)."
  default     = false
}

variable "enable_workload_fargate_profile" {
  type        = bool
  description = "Whether to create a Fargate profile for workloads (argocd/backends/unifiedui)."
  default     = false
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

