data "aws_caller_identity" "current" {}

locals {
  name_prefix = "${var.project}-${var.environment}"

  # EKS Access Entries: if the user doesn't specify any admin principals, grant
  # cluster-admin to the Terraform caller identity by default. If the EKS module
  # is configured to bootstrap creator-admin permissions, EKS already creates an
  # access entry for the creator, so avoid duplicating it here.
  eks_admin_principal_arns = length(var.eks_admin_principal_arns) > 0 ? var.eks_admin_principal_arns : (
    var.bootstrap_cluster_creator_admin_permissions ? [] : [data.aws_caller_identity.current.arn]
  )

  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )
}

module "network" {
  source       = "../network"
  name_prefix  = local.name_prefix
  vpc_cidr     = var.vpc_cidr
  az_count     = var.az_count
  cluster_name = var.eks_cluster_name
  tags         = local.common_tags
}

module "eks_fargate" {
  source                                      = "../eks_fargate"
  cluster_name                                = var.eks_cluster_name
  kubernetes_version                          = var.kubernetes_version
  vpc_id                                      = module.network.vpc_id
  private_subnet_ids                          = module.network.private_subnet_ids
  bootstrap_cluster_creator_admin_permissions = var.bootstrap_cluster_creator_admin_permissions
  enable_system_fargate_profiles              = var.enable_system_fargate_profiles
  enable_workload_fargate_profile             = var.enable_workload_fargate_profile
  workload_namespaces                         = var.workload_namespaces
  workload_namespace_labels                   = var.workload_namespace_labels
  tags                                        = local.common_tags
}

module "eks_managed_nodes" {
  source = "../eks_managed_nodes"

  enable       = var.enable_eks_managed_node_groups
  cluster_name = module.eks_fargate.cluster_name
  subnet_ids   = module.network.private_subnet_ids

  capacity_type = var.eks_node_capacity_type
  disk_size     = var.eks_node_disk_size

  general_instance_types = var.eks_general_instance_types
  general_min_size       = var.eks_general_min_size
  general_desired_size   = var.eks_general_desired_size
  general_max_size       = var.eks_general_max_size

  sales_instance_types = var.eks_sales_instance_types
  sales_min_size       = var.eks_sales_min_size
  sales_desired_size   = var.eks_sales_desired_size
  sales_max_size       = var.eks_sales_max_size

  tags = local.common_tags
}

module "eks_access" {
  source         = "../eks_access"
  depends_on     = [module.eks_fargate]
  cluster_name   = module.eks_fargate.cluster_name
  principal_arns = local.eks_admin_principal_arns
  tags           = local.common_tags
}

module "alb_controller_irsa" {
  source               = "../alb_controller_irsa"
  name_prefix          = local.name_prefix
  cluster_name         = var.eks_cluster_name
  oidc_provider_arn    = module.eks_fargate.oidc_provider_arn
  oidc_provider_url    = module.eks_fargate.oidc_provider_url
  service_account_name = "aws-load-balancer-controller"
  service_account_ns   = "kube-system"
  tags                 = local.common_tags
}

module "argocd_image_updater_irsa" {
  source = "../irsa_role"

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

module "cluster_autoscaler_irsa" {
  source = "../irsa_role"

  role_name   = "${local.name_prefix}-cluster-autoscaler"
  policy_name = "${local.name_prefix}-cluster-autoscaler"

  oidc_provider_arn = module.eks_fargate.oidc_provider_arn
  oidc_provider_url = module.eks_fargate.oidc_provider_url

  service_account_name = "cluster-autoscaler"
  service_account_ns   = "kube-system"

  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AutoscalingWrite"
        Effect = "Allow"
        Action = [
          "autoscaling:SetDesiredCapacity",
          "autoscaling:TerminateInstanceInAutoScalingGroup",
          "autoscaling:UpdateAutoScalingGroup",
        ]
        Resource = "*"
      },
      {
        Sid    = "AutoscalingRead"
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeScalingActivities",
          "autoscaling:DescribeTags",
        ]
        Resource = "*"
      },
      {
        Sid    = "Ec2Read"
        Effect = "Allow"
        Action = [
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeImages",
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeLaunchTemplateVersions",
          "ec2:DescribeRouteTables",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeSubnets",
          "ec2:DescribeVpcs",
        ]
        Resource = "*"
      },
    ]
  })

  tags = local.common_tags
}

module "rds" {
  source             = "../rds"
  name_prefix        = local.name_prefix
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  eks_cluster_sg_id  = module.eks_fargate.cluster_security_group_id

  db_name              = var.db_name
  db_username          = var.db_username
  db_password          = var.db_password
  db_instance_class    = var.db_instance_class
  db_allocated_storage = var.db_allocated_storage
  db_engine_version    = var.db_engine_version
  publicly_accessible  = var.db_publicly_accessible

  tags = local.common_tags
}

