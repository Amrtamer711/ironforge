module "argocd_image_updater_irsa" {
  source = "./modules/irsa_role"

  role_name   = "${local.name_prefix}-argocd-image-updater"
  policy_name = "${local.name_prefix}-argocd-image-updater-ecr-read"

  oidc_provider_arn = module.eks_fargate.oidc_provider_arn
  oidc_provider_url = module.eks_fargate.oidc_provider_url

  service_account_name = "argocd-image-updater"
  service_account_ns   = "argocd"

  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:DescribeImages",
          "ecr:DescribeRepositories",
          "ecr:GetDownloadUrlForLayer",
          "ecr:ListImages",
        ]
        Resource = "*"
      },
    ]
  })

  tags = local.common_tags
}

