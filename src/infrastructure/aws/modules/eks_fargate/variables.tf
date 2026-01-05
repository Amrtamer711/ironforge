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

variable "enable_workload_fargate_profile" {
  type        = bool
  description = "Whether to create additional Fargate profiles for workload_namespaces."
  default     = false
}

variable "workload_namespaces" {
  type        = list(string)
  description = "Kubernetes namespaces to schedule onto Fargate for workloads."
  default     = []
}

variable "workload_namespace_labels" {
  type        = map(map(string))
  description = "Optional label selectors per workload namespace (namespace => labels map)."
  default     = {}
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
