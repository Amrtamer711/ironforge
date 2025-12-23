variable "name_prefix" {
  type        = string
  description = "Prefix for naming."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets for the DB subnet group."
}

variable "eks_cluster_sg_id" {
  type        = string
  description = "EKS cluster security group ID to allow DB access from workloads."
}

variable "db_name" {
  type        = string
  description = "Database name."
}

variable "db_username" {
  type        = string
  description = "Master username."
}

variable "db_password" {
  type        = string
  description = "Master password."
  sensitive   = true
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class."
}

variable "db_allocated_storage" {
  type        = number
  description = "Allocated storage (GB)."
}

variable "db_engine_version" {
  type        = string
  description = "PostgreSQL engine version."
}

variable "publicly_accessible" {
  type        = bool
  description = "Whether the DB is publicly accessible."
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
