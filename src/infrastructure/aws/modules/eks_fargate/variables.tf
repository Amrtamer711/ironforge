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

variable "bootstrap_cluster_creator_admin_permissions" {
  type        = bool
  description = "Whether EKS should automatically grant the cluster creator admin permissions (creates an access entry/policy association for the creator)."
  default     = true
}

variable "enable_system_fargate_profiles" {
  type        = bool
  description = "Whether to create the kube-system Fargate profiles (CoreDNS + AWS Load Balancer Controller)."
  default     = true
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
