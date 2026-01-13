output "argocd_acm_certificate_arn" {
  value = (
    local.argocd_dns_enabled
    ? (
      var.argocd_wait_for_acm_validation
      ? aws_acm_certificate_validation.argocd[0].certificate_arn
      : aws_acm_certificate.argocd[0].arn
    )
    : null
  )
  description = "ACM certificate ARN for the Argo CD hostname (use in the Ingress certificate annotation)."
}

output "argocd_acm_dns_validation_records" {
  value = local.argocd_dns_enabled ? [
    for dvo in aws_acm_certificate.argocd[0].domain_validation_options : {
      domain_name = dvo.domain_name
      name        = dvo.resource_record_name
      type        = dvo.resource_record_type
      value       = dvo.resource_record_value
    }
  ] : []
  description = "DNS validation records to create in your DNS provider (useful when argocd_dns_provider=external)."
}

output "argocd_external_dns_cname" {
  value = (
    local.argocd_dns_enabled && var.argocd_dns_provider == "external" ? {
      name  = var.argocd_hostname
      type  = "CNAME"
      value = try(data.aws_lb.argocd[0].dns_name, null)
    } : null
  )
  description = "Suggested external DNS record to point the Argo CD hostname to the ALB (requires your DNS provider to support the record type/name)."
}

output "argocd_alb_dns_name" {
  value       = local.argocd_alb_arn == null ? null : data.aws_lb.argocd[0].dns_name
  description = "DNS name of the ALB created for the Argo CD Ingress."
}

output "argocd_public_zone_id" {
  value       = local.argocd_route53_enabled ? local.argocd_public_zone_id : null
  description = "Route53 hosted zone ID used for argocd public DNS."
}

output "argocd_public_zone_name_servers" {
  value = (
    local.argocd_route53_enabled && var.create_argocd_public_zone
    ? aws_route53_zone.argocd_public[0].name_servers
    : null
  )
  description = "Name servers for the created hosted zone (set these at your domain registrar)."
}

