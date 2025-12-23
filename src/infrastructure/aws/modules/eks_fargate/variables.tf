variable "cluster_name" {
  type        = string
  description = "EKS cluster name."
}

variable "kubernetes_version" {
  type        = string
  description = "EKS Kubernetes version."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID for the cluster."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for the cluster."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
