variable "enable" {
  type        = bool
  description = "Whether to create EKS managed node groups."
  default     = false
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnet IDs for the node groups (typically private subnets)."
}

variable "node_role_name" {
  type        = string
  description = "IAM role name for EC2 worker nodes."
  default     = null
}

variable "enable_ssm" {
  type        = bool
  description = "Whether to attach AmazonSSMManagedInstanceCore to the node role."
  default     = true
}

variable "capacity_type" {
  type        = string
  description = "Capacity type for node groups: ON_DEMAND or SPOT."
  default     = "ON_DEMAND"

  validation {
    condition     = contains(["ON_DEMAND", "SPOT"], var.capacity_type)
    error_message = "capacity_type must be one of: ON_DEMAND, SPOT."
  }
}

variable "disk_size" {
  type        = number
  description = "Disk size in GiB for nodes (EBS root volume)."
  default     = 50
}

variable "general_enabled" {
  type        = bool
  description = "Whether to create the general-purpose node group."
  default     = true
}

variable "general_name" {
  type        = string
  description = "Name suffix for the general-purpose node group."
  default     = "general"
}

variable "general_instance_types" {
  type        = list(string)
  description = "EC2 instance types for the general-purpose node group."
  default     = ["m6i.xlarge"]
}

variable "general_min_size" {
  type        = number
  description = "Minimum size for the general-purpose node group."
  default     = 2
}

variable "general_desired_size" {
  type        = number
  description = "Desired size for the general-purpose node group."
  default     = 2
}

variable "general_max_size" {
  type        = number
  description = "Maximum size for the general-purpose node group."
  default     = 4
}

variable "general_labels" {
  type        = map(string)
  description = "Kubernetes labels applied to nodes in the general-purpose node group."
  default     = { workload = "general" }
}

variable "general_taints" {
  type = list(object({
    key    = string
    value  = string
    effect = string
  }))
  description = "Kubernetes taints applied to nodes in the general-purpose node group."
  default     = []
}

variable "sales_enabled" {
  type        = bool
  description = "Whether to create the dedicated sales node group."
  default     = true
}

variable "sales_name" {
  type        = string
  description = "Name suffix for the sales node group."
  default     = "sales"
}

variable "sales_instance_types" {
  type        = list(string)
  description = "EC2 instance types for the sales node group."
  default     = ["r6i.2xlarge"]
}

variable "sales_min_size" {
  type        = number
  description = "Minimum size for the sales node group."
  default     = 1
}

variable "sales_desired_size" {
  type        = number
  description = "Desired size for the sales node group."
  default     = 1
}

variable "sales_max_size" {
  type        = number
  description = "Maximum size for the sales node group."
  default     = 3
}

variable "sales_labels" {
  type        = map(string)
  description = "Kubernetes labels applied to nodes in the sales node group."
  default     = { workload = "sales" }
}

variable "sales_taints" {
  type = list(object({
    key    = string
    value  = string
    effect = string
  }))
  description = "Kubernetes taints applied to nodes in the sales node group."
  default = [
    {
      key    = "dedicated"
      value  = "sales"
      effect = "NO_SCHEDULE"
    }
  ]
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources where supported."
  default     = {}
}
