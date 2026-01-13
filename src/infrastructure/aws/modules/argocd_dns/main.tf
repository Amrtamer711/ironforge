locals {
  argocd_dns_enabled     = var.enable_argocd_public_dns
  argocd_route53_enabled = local.argocd_dns_enabled && var.argocd_dns_provider == "route53"

  argocd_zone_name = (
    local.argocd_route53_enabled
    ? (
      endswith(var.argocd_public_zone_name, ".")
      ? var.argocd_public_zone_name
      : "${var.argocd_public_zone_name}."
    )
    : null
  )

  argocd_zone_id = local.argocd_route53_enabled && length(trimspace(var.argocd_public_zone_id)) > 0 ? trimspace(var.argocd_public_zone_id) : null
}

data "aws_route53_zone" "argocd_public_by_id" {
  count        = local.argocd_zone_id == null ? 0 : 1
  zone_id      = local.argocd_zone_id
  private_zone = false
}

resource "aws_route53_zone" "argocd_public" {
  count = (
    local.argocd_route53_enabled
    && local.argocd_zone_id == null
    && var.create_argocd_public_zone
  ) ? 1 : 0

  name = trimsuffix(local.argocd_zone_name, ".")

  lifecycle {
    prevent_destroy = true
  }
}

data "aws_route53_zone" "argocd_public_by_name" {
  count = (
    local.argocd_route53_enabled
    && local.argocd_zone_id == null
    && !var.create_argocd_public_zone
  ) ? 1 : 0

  name         = local.argocd_zone_name
  private_zone = false
}

locals {
  argocd_public_zone_id = local.argocd_route53_enabled ? (
    local.argocd_zone_id != null ? data.aws_route53_zone.argocd_public_by_id[0].zone_id : (
      var.create_argocd_public_zone ? aws_route53_zone.argocd_public[0].zone_id : data.aws_route53_zone.argocd_public_by_name[0].zone_id
    )
  ) : null
}

resource "aws_acm_certificate" "argocd" {
  count = local.argocd_dns_enabled ? 1 : 0

  domain_name       = var.argocd_hostname
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "argocd_cert_validation" {
  for_each = local.argocd_route53_enabled ? {
    for dvo in aws_acm_certificate.argocd[0].domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  } : {}

  zone_id = local.argocd_public_zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.value]
}

resource "aws_acm_certificate_validation" "argocd" {
  count = local.argocd_dns_enabled && var.argocd_wait_for_acm_validation ? 1 : 0

  certificate_arn = aws_acm_certificate.argocd[0].arn
  validation_record_fqdns = (
    local.argocd_route53_enabled
    ? [for record in aws_route53_record.argocd_cert_validation : record.fqdn]
    : [for dvo in aws_acm_certificate.argocd[0].domain_validation_options : dvo.resource_record_name]
  )
}

# The ALB is created by AWS Load Balancer Controller from the `argocd-server` Ingress.
# We discover it via tags so Route53 can alias to it without hardcoding the generated ALB name.
data "aws_resourcegroupstaggingapi_resources" "argocd_alb" {
  count = local.argocd_dns_enabled ? 1 : 0

  resource_type_filters = ["elasticloadbalancing:loadbalancer"]

  tag_filter {
    key    = "ingress.k8s.aws/stack"
    values = [var.argocd_ingress_stack_tag]
  }

  tag_filter {
    key    = "elbv2.k8s.aws/cluster"
    values = [var.cluster_name]
  }
}

locals {
  argocd_alb_arn = local.argocd_dns_enabled ? try(data.aws_resourcegroupstaggingapi_resources.argocd_alb[0].resource_tag_mapping_list[0].resource_arn, null) : null
}

data "aws_lb" "argocd" {
  count = local.argocd_alb_arn == null ? 0 : 1
  arn   = local.argocd_alb_arn
}

resource "aws_route53_record" "argocd_a" {
  count = local.argocd_route53_enabled && local.argocd_alb_arn != null ? 1 : 0

  zone_id = local.argocd_public_zone_id
  name    = var.argocd_hostname
  type    = "A"

  alias {
    name                   = data.aws_lb.argocd[0].dns_name
    zone_id                = data.aws_lb.argocd[0].zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "argocd_aaaa" {
  count = local.argocd_route53_enabled && local.argocd_alb_arn != null ? 1 : 0

  zone_id = local.argocd_public_zone_id
  name    = var.argocd_hostname
  type    = "AAAA"

  alias {
    name                   = data.aws_lb.argocd[0].dns_name
    zone_id                = data.aws_lb.argocd[0].zone_id
    evaluate_target_health = true
  }
}

