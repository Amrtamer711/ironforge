variable "aws_region" {
  type        = string
  description = "AWS region for ACM (must match ALB region)."
  default     = "eu-north-1"
}

variable "tags" {
  type        = map(string)
  description = "Extra tags applied to resources where supported."
  default     = {}
}

variable "platform_apex" {
  type        = string
  description = "Apex domain to manage in Route53, e.g. mmg-nova.com."
}

variable "argocd_hostname" {
  type        = string
  description = "Argo CD hostname under the apex, e.g. argocd.mmg-nova.com."
}

variable "serviceplatform_hostname" {
  type        = string
  description = "Unified UI hostname under the apex, e.g. serviceplatform.mmg-nova.com."
}

variable "create_hosted_zone" {
  type        = bool
  description = "Whether to create a Route53 public hosted zone for platform_apex."
  default     = true
}

variable "hosted_zone_id" {
  type        = string
  description = "Existing Route53 hosted zone ID for platform_apex (optional)."
  default     = ""
}

variable "wait_for_acm_validation" {
  type        = bool
  description = "Whether to wait for ACM DNS validation to complete."
  default     = true
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name used by AWS Load Balancer Controller tag (elbv2.k8s.aws/cluster)."
  default     = ""
}

variable "argocd_ingress_stack_tag" {
  type        = string
  description = "Tag value used by AWS Load Balancer Controller on the ALB (ingress.k8s.aws/stack) for the Argo CD Ingress."
  default     = "argocd/argocd-server"
}

variable "serviceplatform_ingress_stack_tag" {
  type        = string
  description = "Tag value used by AWS Load Balancer Controller on the ALB (ingress.k8s.aws/stack) for the Unified UI Ingress."
  default     = "unifiedui/unified-ui"
}
