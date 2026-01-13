variable "enable_argocd_public_dns" {
  type        = bool
  description = "Whether to create Route53 + ACM resources for exposing Argo CD with a real hostname + TLS."
  default     = false
}

variable "argocd_dns_provider" {
  type        = string
  description = "DNS provider mode: 'route53' manages validation + alias records in Route53; 'external' outputs DNS records to add in an external DNS provider (e.g. GoDaddy)."
  default     = "route53"

  validation {
    condition     = contains(["route53", "external"], var.argocd_dns_provider)
    error_message = "argocd_dns_provider must be one of: route53, external."
  }
}

variable "create_argocd_public_zone" {
  type        = bool
  description = "Whether to create a new public Route53 hosted zone for argocd_public_zone_name (route53 mode only)."
  default     = false
}

variable "argocd_public_zone_name" {
  type        = string
  description = "Public Route53 hosted zone name (trailing dot optional), e.g. example.com or example.com."
  default     = ""

  validation {
    condition = (
      !var.enable_argocd_public_dns
      || var.argocd_dns_provider != "route53"
      || length(trimspace(var.argocd_public_zone_id)) > 0
      || length(trimspace(var.argocd_public_zone_name)) > 0
    )
    error_message = "In route53 mode, either argocd_public_zone_name or argocd_public_zone_id must be set when enable_argocd_public_dns=true."
  }
}

variable "argocd_public_zone_id" {
  type        = string
  description = "Public Route53 hosted zone ID (preferred, avoids name ambiguity), e.g. Z1234567890ABC."
  default     = ""
}

variable "argocd_hostname" {
  type        = string
  description = "Argo CD public hostname to create in Route53, e.g. argocd.example.com."
  default     = ""

  validation {
    condition     = !var.enable_argocd_public_dns || length(trimspace(var.argocd_hostname)) > 0
    error_message = "argocd_hostname must be set when enable_argocd_public_dns=true."
  }
}

variable "argocd_wait_for_acm_validation" {
  type        = bool
  description = "Whether Terraform should wait for ACM DNS validation to complete (can be disabled while you delegate name servers at your registrar)."
  default     = true
}

variable "argocd_ingress_stack_tag" {
  type        = string
  description = "Tag value used by AWS Load Balancer Controller on the ALB (ingress.k8s.aws/stack) for the Argo CD Ingress."
  default     = "argocd/argocd-server"
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name used by AWS Load Balancer Controller tag (elbv2.k8s.aws/cluster). Required when enable_argocd_public_dns=true."
  default     = ""

  validation {
    condition     = !var.enable_argocd_public_dns || length(trimspace(var.cluster_name)) > 0
    error_message = "cluster_name must be set when enable_argocd_public_dns=true."
  }
}

