variable "cluster_name" {
  type        = string
  description = "EKS cluster name to manage access entries for."
}

variable "principal_arns" {
  type        = list(string)
  description = "IAM principal ARNs (users/roles) to grant cluster-admin access."
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply where supported."
  default     = {}
}
