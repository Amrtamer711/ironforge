output "hosted_zone_id" {
  value       = local.hosted_zone_id
  description = "Route53 hosted zone ID for the platform apex."
}

output "name_servers" {
  value = (
    length(aws_route53_zone.platform_apex) > 0
    ? aws_route53_zone.platform_apex[0].name_servers
    : (
      length(data.aws_route53_zone.platform_apex_by_id) > 0
      ? data.aws_route53_zone.platform_apex_by_id[0].name_servers
      : (length(data.aws_route53_zone.platform_apex_by_name) > 0 ? data.aws_route53_zone.platform_apex_by_name[0].name_servers : null)
    )
  )
  description = "Name servers for the created hosted zone (set these at your registrar if you register elsewhere)."
}

output "acm_certificate_arn" {
  value = (
    var.wait_for_acm_validation
    ? aws_acm_certificate_validation.platform_apex[0].certificate_arn
    : aws_acm_certificate.platform_apex.arn
  )
  description = "ACM certificate ARN covering argocd + serviceplatform hostnames."
}

output "acm_dns_validation_records" {
  value = [
    for dvo in aws_acm_certificate.platform_apex.domain_validation_options : {
      domain_name = dvo.domain_name
      name        = dvo.resource_record_name
      type        = dvo.resource_record_type
      value       = dvo.resource_record_value
    }
  ]
  description = "DNS validation records for ACM (useful for troubleshooting)."
}

output "argocd_alb_dns_name" {
  value       = local.argocd_alb_arn == null ? null : data.aws_lb.argocd[0].dns_name
  description = "Discovered ALB DNS name for Argo CD (requires cluster_name)."
}

output "serviceplatform_alb_dns_name" {
  value       = local.serviceplatform_alb_arn == null ? null : data.aws_lb.serviceplatform[0].dns_name
  description = "Discovered ALB DNS name for Unified UI (requires cluster_name)."
}
