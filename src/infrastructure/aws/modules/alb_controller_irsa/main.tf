data "http" "alb_policy" {
  url = var.policy_url
}

locals {
  issuer_hostpath = replace(var.oidc_provider_url, "https://", "")
  sa_sub          = "system:serviceaccount:${var.service_account_ns}:${var.service_account_name}"
}

resource "aws_iam_policy" "this" {
  name        = "${var.name_prefix}-AWSLoadBalancerControllerIAMPolicy-t588"
  description = "Policy for AWS Load Balancer Controller (ALB) using IRSA."
  policy      = data.http.alb_policy.response_body
  tags        = var.tags
}

resource "aws_iam_role" "this" {
  name = "${var.name_prefix}-AmazonEKSLoadBalancerControllerRole-t588"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Federated = var.oidc_provider_arn }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.issuer_hostpath}:aud" = "sts.amazonaws.com"
          "${local.issuer_hostpath}:sub" = local.sa_sub
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "this" {
  role      = aws_iam_role.this.name
  policy_arn = aws_iam_policy.this.arn
}
