variable "project" {
  type        = string
  description = "Project prefix used for naming."
}

variable "environment" {
  type        = string
  description = "Environment name (e.g., dev, staging, production)."
}

variable "tags" {
  type        = map(string)
  description = "Extra tags applied to all resources where supported."
  default     = {}
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block."
}

variable "az_count" {
  type        = number
  description = "How many AZs to use (2-3 typical)."
  default     = 2
}

variable "eks_cluster_name" {
  type        = string
  description = "EKS cluster name."
}

variable "kubernetes_version" {
  type        = string
  description = "EKS Kubernetes version."
  default     = "1.34"
}

variable "bootstrap_cluster_creator_admin_permissions" {
  type        = bool
  description = "Whether EKS should automatically grant the cluster creator admin permissions."
  default     = true
}

variable "eks_admin_principal_arns" {
  type        = list(string)
  description = "List of IAM principal ARNs (users/roles) that should have cluster-admin access via EKS Access Entries."
  default     = []
}

variable "enable_workload_fargate_profile" {
  type        = bool
  description = "Whether to create a Fargate profile for workload_namespaces."
  default     = false
}

variable "enable_system_fargate_profiles" {
  type        = bool
  description = "Whether to create the kube-system Fargate profiles (CoreDNS + AWS Load Balancer Controller)."
  default     = false
}

variable "workload_namespaces" {
  type        = list(string)
  description = "Kubernetes namespaces to schedule onto Fargate for workloads."
  default     = ["argocd", "unifiedui", "backends"]
}

variable "workload_namespace_labels" {
  type        = map(map(string))
  description = "Optional label selectors per workload namespace (namespace => labels map)."
  default     = {}
}

variable "enable_eks_managed_node_groups" {
  type        = bool
  description = "Whether to create EKS managed node groups (EC2 workers)."
  default     = true
}

variable "eks_node_capacity_type" {
  type        = string
  description = "Capacity type for node groups: ON_DEMAND or SPOT."
  default     = "ON_DEMAND"
}

variable "eks_node_disk_size" {
  type        = number
  description = "Disk size in GiB for EC2 nodes (EBS root volume)."
  default     = 50
}

variable "eks_general_instance_types" {
  type        = list(string)
  description = "EC2 instance types for the general-purpose node group."
  default     = ["m6i.xlarge"]
}

variable "eks_general_min_size" {
  type        = number
  description = "Minimum size for the general-purpose node group."
  default     = 1
}

variable "eks_general_desired_size" {
  type        = number
  description = "Desired size for the general-purpose node group."
  default     = 1
}

variable "eks_general_max_size" {
  type        = number
  description = "Maximum size for the general-purpose node group."
  default     = 6
}

variable "eks_sales_instance_types" {
  type        = list(string)
  description = "EC2 instance types for the dedicated sales node group."
  default     = ["r6i.2xlarge"]
}

variable "eks_sales_min_size" {
  type        = number
  description = "Minimum size for the dedicated sales node group."
  default     = 1
}

variable "eks_sales_desired_size" {
  type        = number
  description = "Desired size for the dedicated sales node group."
  default     = 1
}

variable "eks_sales_max_size" {
  type        = number
  description = "Maximum size for the dedicated sales node group."
  default     = 6
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
