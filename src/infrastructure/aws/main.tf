locals {
  name_prefix = "${var.project}-${var.environment}"

  # EKS Access Entries: if the user doesn't specify any admin principals, grant
  # cluster-admin to the Terraform caller identity by default.
  eks_admin_principal_arns = length(var.eks_admin_principal_arns) > 0 ? var.eks_admin_principal_arns : [data.aws_caller_identity.current.arn]

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
  source       = "./modules/network"
  name_prefix  = local.name_prefix
  vpc_cidr     = var.vpc_cidr
  az_count     = var.az_count
  cluster_name = var.eks_cluster_name
  tags         = local.common_tags
}

module "s3_buckets" {
  source       = "./modules/s3_buckets"
  bucket_names = var.s3_bucket_names
  tags         = local.common_tags
}

module "ecr" {
  source            = "./modules/ecr"
  repository_names  = var.ecr_repository_names
  tags              = local.common_tags
}

module "eks" {
  source               = "./modules/eks_fargate"
  cluster_name         = var.eks_cluster_name
  kubernetes_version   = var.kubernetes_version
  vpc_id               = module.network.vpc_id
  private_subnet_ids   = module.network.private_subnet_ids
  tags                 = local.common_tags
}

module "eks_access" {
  source         = "./modules/eks_access"
  depends_on = [module.eks]
  cluster_name   = module.eks.cluster_name
  principal_arns = local.eks_admin_principal_arns
  tags           = local.common_tags
}

module "alb_controller_irsa" {
  source                 = "./modules/alb_controller_irsa"
  name_prefix            = local.name_prefix
  cluster_name           = var.eks_cluster_name
  oidc_provider_arn      = module.eks.oidc_provider_arn
  oidc_provider_url      = module.eks.oidc_provider_url
  service_account_name   = "aws-load-balancer-controller"
  service_account_ns     = "kube-system"
  tags                   = local.common_tags
}

module "rds" {
  source                 = "./modules/rds"
  name_prefix            = local.name_prefix
  vpc_id                 = module.network.vpc_id
  private_subnet_ids     = module.network.private_subnet_ids
  eks_cluster_sg_id      = module.eks.cluster_security_group_id

  db_name                = var.db_name
  db_username            = var.db_username
  db_password            = var.db_password
  db_instance_class      = var.db_instance_class
  db_allocated_storage   = var.db_allocated_storage
  db_engine_version      = var.db_engine_version
  publicly_accessible    = var.db_publicly_accessible

  tags                   = local.common_tags
}
