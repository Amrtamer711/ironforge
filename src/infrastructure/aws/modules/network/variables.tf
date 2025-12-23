variable "name_prefix" {
  type        = string
  description = "Prefix for naming network resources."
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block."
}

variable "az_count" {
  type        = number
  description = "Number of AZs to use."
  default     = 2
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name used for subnet discovery tags."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
