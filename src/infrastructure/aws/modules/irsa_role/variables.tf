variable "role_name" {
  type        = string
  description = "IAM role name."
}

variable "policy_name" {
  type        = string
  description = "IAM policy name to create and attach to the role."
}

variable "oidc_provider_arn" {
  type        = string
  description = "IAM OIDC provider ARN for the EKS cluster."
}

variable "oidc_provider_url" {
  type        = string
  description = "OIDC provider URL (issuer), e.g. https://oidc.eks.<region>.amazonaws.com/id/XXXX"
}

variable "service_account_name" {
  type        = string
  description = "Kubernetes ServiceAccount name."
}

variable "service_account_ns" {
  type        = string
  description = "Kubernetes namespace for the ServiceAccount."
}

variable "policy_json" {
  type        = string
  description = "IAM policy JSON document."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to IAM resources."
  default     = {}
}

