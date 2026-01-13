locals {
  apex = trimsuffix(var.platform_apex, ".")

  hosted_zone_id = (
    length(trimspace(var.hosted_zone_id)) > 0
    ? trimspace(var.hosted_zone_id)
    : (
      var.create_hosted_zone ? aws_route53_zone.platform_apex[0].zone_id : data.aws_route53_zone.platform_apex_by_name[0].zone_id
    )
  )

  can_discover_albs = length(trimspace(var.cluster_name)) > 0
}

resource "aws_route53_zone" "platform_apex" {
  count = length(trimspace(var.hosted_zone_id)) == 0 && var.create_hosted_zone ? 1 : 0

  name = local.apex

  lifecycle {
    prevent_destroy = true
  }

  tags = var.tags
}

data "aws_route53_zone" "platform_apex_by_id" {
  count        = length(trimspace(var.hosted_zone_id)) > 0 ? 1 : 0
  zone_id      = trimspace(var.hosted_zone_id)
  private_zone = false
}

data "aws_route53_zone" "platform_apex_by_name" {
  count        = length(trimspace(var.hosted_zone_id)) == 0 && !var.create_hosted_zone ? 1 : 0
  name         = "${local.apex}."
  private_zone = false
}

resource "aws_acm_certificate" "platform_apex" {
  domain_name               = var.argocd_hostname
  subject_alternative_names = [var.serviceplatform_hostname]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = var.tags
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.platform_apex.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = local.hosted_zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.value]
}

resource "aws_acm_certificate_validation" "platform_apex" {
  count           = var.wait_for_acm_validation ? 1 : 0
  certificate_arn = aws_acm_certificate.platform_apex.arn
  validation_record_fqdns = [
    for record in aws_route53_record.cert_validation : record.fqdn
  ]
}

data "aws_resourcegroupstaggingapi_resources" "argocd_alb" {
  count = local.can_discover_albs ? 1 : 0

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
  argocd_alb_arn = local.can_discover_albs ? try(data.aws_resourcegroupstaggingapi_resources.argocd_alb[0].resource_tag_mapping_list[0].resource_arn, null) : null
}

data "aws_lb" "argocd" {
  count = local.argocd_alb_arn == null ? 0 : 1
  arn   = local.argocd_alb_arn
}

data "aws_resourcegroupstaggingapi_resources" "serviceplatform_alb" {
  count = local.can_discover_albs ? 1 : 0

  resource_type_filters = ["elasticloadbalancing:loadbalancer"]

  tag_filter {
    key    = "ingress.k8s.aws/stack"
    values = [var.serviceplatform_ingress_stack_tag]
  }

  tag_filter {
    key    = "elbv2.k8s.aws/cluster"
    values = [var.cluster_name]
  }
}

locals {
  serviceplatform_alb_arn = local.can_discover_albs ? try(data.aws_resourcegroupstaggingapi_resources.serviceplatform_alb[0].resource_tag_mapping_list[0].resource_arn, null) : null
}

data "aws_lb" "serviceplatform" {
  count = local.serviceplatform_alb_arn == null ? 0 : 1
  arn   = local.serviceplatform_alb_arn
}

resource "aws_route53_record" "argocd_a" {
  count = local.argocd_alb_arn == null ? 0 : 1

  zone_id = local.hosted_zone_id
  name    = var.argocd_hostname
  type    = "A"

  alias {
    name                   = data.aws_lb.argocd[0].dns_name
    zone_id                = data.aws_lb.argocd[0].zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "argocd_aaaa" {
  count = local.argocd_alb_arn == null ? 0 : 1

  zone_id = local.hosted_zone_id
  name    = var.argocd_hostname
  type    = "AAAA"

  alias {
    name                   = data.aws_lb.argocd[0].dns_name
    zone_id                = data.aws_lb.argocd[0].zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "serviceplatform_a" {
  count = local.serviceplatform_alb_arn == null ? 0 : 1

  zone_id = local.hosted_zone_id
  name    = var.serviceplatform_hostname
  type    = "A"

  alias {
    name                   = data.aws_lb.serviceplatform[0].dns_name
    zone_id                = data.aws_lb.serviceplatform[0].zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "serviceplatform_aaaa" {
  count = local.serviceplatform_alb_arn == null ? 0 : 1

  zone_id = local.hosted_zone_id
  name    = var.serviceplatform_hostname
  type    = "AAAA"

  alias {
    name                   = data.aws_lb.serviceplatform[0].dns_name
    zone_id                = data.aws_lb.serviceplatform[0].zone_id
    evaluate_target_health = true
  }
}
