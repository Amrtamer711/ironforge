variable "name_prefix" {
  type        = string
  description = "Prefix for naming."
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name (used for naming only)."
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
  description = "Kubernetes ServiceAccount name for the controller."
  default     = "aws-load-balancer-controller"
}

variable "service_account_ns" {
  type        = string
  description = "Kubernetes namespace for the ServiceAccount."
  default     = "kube-system"
}

variable "policy_url" {
  type        = string
  description = "URL to the official aws-load-balancer-controller IAM policy JSON."
  default     = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.14.1/docs/install/iam_policy.json"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to IAM resources."
  default     = {}
}
