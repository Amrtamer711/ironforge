/*
Terraform root module for the MMG Service Platform AWS infrastructure.

Goal: keep this directory minimal (single `main.tf`), with reusable modules in `./modules/**`.
*/

/*
Remote state backend (S3 + DynamoDB locking)

Note: this requires the state bucket + lock table to exist (see the bootstrap stack).
*/
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.50"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0"
    }
    http = {
      source  = "hashicorp/http"
      version = ">= 3.4"
    }
  }

  backend "s3" {
    bucket       = "mmg-global-terraform-state-bucket-t588"
    key          = "bootstrap/terraform.tfstate"
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

variable "aws_region" {
  type        = string
  description = "AWS region to deploy into."
  default     = "eu-north-1"
}

variable "project" {
  type        = string
  description = "Project prefix used for naming."
  default     = "example"
}

variable "environment" {
  type        = string
  description = "Environment name (e.g., dev, stage, prod)."
  default     = "dev"
}

variable "tags" {
  type        = map(string)
  description = "Extra tags applied to all resources where supported."
  default     = {}
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block."
  default     = "10.0.0.0/16"
}

variable "az_count" {
  type        = number
  description = "How many AZs to use (2-3 typical)."
  default     = 2
}

variable "s3_bucket_names" {
  type        = list(string)
  description = "S3 bucket names to create."
  default = [
    "mmg-global-ingest-bucket-1-t588",
    "mmg-global-corpus-bucket-1-t588",
    "mmg-global-data-bucket-1-t588",
    "mmg-global-data-bucket-2-t588",
    "mmg-global-data-bucket-3-t588"
  ]
}

variable "ecr_repository_names" {
  type        = list(string)
  description = "ECR repository names to create."
  default = [
    "asset_library",
    "proposalsandbookings",
    "crm",
    "assetmaintenance",
    "staticcampaigns",
    "digitalcampaigns",
    "policyqa",
    "salescampaignsupport",
    "marketingcampaigns",
    "revenuerecognition",
    "accountsreceivable",
    "salesordermanagement",
    "testapprepo",
    "proposal-bot",
    "security-service",
    "unifiedui",
    "video-critique"
  ]
}

variable "ecr_force_delete" {
  type        = bool
  description = "Whether to force delete ECR repositories on destroy (deletes all images)."
  default     = false
}

variable "enable_gitlab_ci_ecr_push_policy" {
  type        = bool
  description = "Whether Terraform should attach an inline ECR push policy to the GitLab OIDC CI role (AWS_ROLE_ARN) so CI can push images to repos in ecr_repository_names."
  default     = false
}

variable "gitlab_ci_role_name" {
  type        = string
  description = "IAM role name used by GitLab CI via OIDC (AWS_ROLE_ARN). Terraform will attach the ECR push policy to this role when enable_gitlab_ci_ecr_push_policy=true."
  default     = "GitLabOidcEcrPusher"
}

variable "eks_cluster_name" {
  type        = string
  description = "EKS cluster name."
  default     = "mmg-test-cluster-1-t588"
}

variable "kubernetes_version" {
  type        = string
  description = "EKS Kubernetes version."
  default     = "1.34"
}

variable "bootstrap_cluster_creator_admin_permissions" {
  type        = bool
  description = "Whether EKS should automatically grant the cluster creator admin permissions (creates an access entry/policy association for the creator)."
  default     = true
}

variable "eks_admin_principal_arns" {
  type        = list(string)
  description = "List of IAM principal ARNs (users/roles) that should have cluster-admin access to the EKS cluster via EKS Access Entries. If empty, defaults to the Terraform caller identity ARN."
  default     = []
}

variable "enable_workload_fargate_profile" {
  type        = bool
  description = "Whether to create a Fargate profile for workload_namespaces."
  default     = true
}

variable "enable_system_fargate_profiles" {
  type        = bool
  description = "Whether to create the kube-system Fargate profiles (CoreDNS + AWS Load Balancer Controller)."
  default     = true
}

variable "enable_eks_managed_node_groups" {
  type        = bool
  description = "Whether to create EKS managed node groups (EC2 workers)."
  default     = false
}

variable "eks_node_capacity_type" {
  type        = string
  description = "Capacity type for node groups: ON_DEMAND or SPOT."
  default     = "ON_DEMAND"
}

variable "eks_node_disk_size" {
  type        = number
  description = "Disk size in GiB for EC2 nodes (EBS root volume)."
  default     = 50
}

variable "eks_general_instance_types" {
  type        = list(string)
  description = "EC2 instance types for the general-purpose node group."
  default     = ["m6i.large"]
}

variable "eks_general_min_size" {
  type        = number
  description = "Minimum size for the general-purpose node group."
  default     = 1
}

variable "eks_general_desired_size" {
  type        = number
  description = "Desired size for the general-purpose node group."
  default     = 1
}

variable "eks_general_max_size" {
  type        = number
  description = "Maximum size for the general-purpose node group."
  default     = 6
}

variable "eks_sales_instance_types" {
  type        = list(string)
  description = "EC2 instance types for the dedicated sales node group (start with r6i.xlarge)."
  default     = ["r6i.xlarge"]
}

variable "eks_sales_min_size" {
  type        = number
  description = "Minimum size for the dedicated sales node group."
  default     = 1
}

variable "eks_sales_desired_size" {
  type        = number
  description = "Desired size for the dedicated sales node group."
  default     = 1
}

variable "eks_sales_max_size" {
  type        = number
  description = "Maximum size for the dedicated sales node group."
  default     = 6
}

variable "workload_namespaces" {
  type        = list(string)
  description = "Kubernetes namespaces to schedule onto Fargate for workloads (apps + platform controllers like ArgoCD)."
  default     = ["argocd", "unifiedui", "backends"]

  validation {
    condition = (
      length(var.workload_namespaces) == length(distinct(var.workload_namespaces))
      && alltrue([
        for ns in var.workload_namespaces :
        length(ns) <= 63 && can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", ns))
      ])
    )
    error_message = "workload_namespaces must be unique and each namespace must be a valid Kubernetes namespace name (RFC1123 label): <=63 chars, lowercase alphanumeric or '-', start/end with alphanumeric."
  }
}

variable "workload_namespace_labels" {
  type        = map(map(string))
  description = "Optional label selectors per workload namespace (namespace => labels map). If omitted for a namespace, all pods in that namespace match."
  default     = {}
}

# RDS (RBAC database)
variable "db_name" {
  type        = string
  description = "Initial database name."
  default     = "rbac"
}

variable "db_username" {
  type        = string
  description = "Master username."
  default     = "rbac_admin"
}

variable "db_password" {
  type        = string
  description = "Master password (set via TF_VAR_db_password or -var)."
  sensitive   = true
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class."
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  type        = number
  description = "Allocated storage in GB."
  default     = 20
}

variable "db_engine_version" {
  type        = string
  description = "PostgreSQL engine version."
  default     = "17.7"
}

variable "db_publicly_accessible" {
  type        = bool
  description = "Whether the RDS instance is publicly accessible (recommended false)."
  default     = false
}

# Argo CD public DNS (legacy flow; dedicated platform apex is preferred)
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
  source           = "./modules/ecr"
  repository_names = var.ecr_repository_names
  force_delete     = var.ecr_force_delete
  tags             = local.common_tags
}

locals {
  ecr_repository_arns = [
    for repo_name in var.ecr_repository_names :
    "arn:${data.aws_partition.current.partition}:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${repo_name}"
  ]
}

# GitLab CI role (OIDC): allow pushing images to ECR.
# This is intentionally separate from the EKS cluster auth (Access Entries).
resource "aws_iam_role_policy" "gitlab_ci_ecr_push" {
  count = var.enable_gitlab_ci_ecr_push_policy ? 1 : 0

  name = "${local.name_prefix}-gitlab-ci-ecr-push"
  role = var.gitlab_ci_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcrGetAuthToken"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
      {
        Sid    = "EcrPushToRepos"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:CompleteLayerUpload",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource = local.ecr_repository_arns
      },
      {
        Sid    = "EcrReadRepoMetadata"
        Effect = "Allow"
        Action = [
          "ecr:DescribeRepositories",
          "ecr:DescribeImages",
          "ecr:ListImages",
        ]
        Resource = local.ecr_repository_arns
      },
    ]
  })
}

module "eks_fargate" {
  source                                      = "./modules/eks_fargate"
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
  source = "./modules/eks_managed_nodes"

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
  source         = "./modules/eks_access"
  depends_on     = [module.eks_fargate]
  cluster_name   = module.eks_fargate.cluster_name
  principal_arns = local.eks_admin_principal_arns
  tags           = local.common_tags
}

module "alb_controller_irsa" {
  source               = "./modules/alb_controller_irsa"
  name_prefix          = local.name_prefix
  cluster_name         = var.eks_cluster_name
  oidc_provider_arn    = module.eks_fargate.oidc_provider_arn
  oidc_provider_url    = module.eks_fargate.oidc_provider_url
  service_account_name = "aws-load-balancer-controller"
  service_account_ns   = "kube-system"
  tags                 = local.common_tags
}

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

module "cluster_autoscaler_irsa" {
  source = "./modules/irsa_role"

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

module "argocd_dns" {
  source = "./modules/argocd_dns"

  enable_argocd_public_dns       = var.enable_argocd_public_dns
  argocd_dns_provider            = var.argocd_dns_provider
  create_argocd_public_zone      = var.create_argocd_public_zone
  argocd_public_zone_id          = var.argocd_public_zone_id
  argocd_public_zone_name        = var.argocd_public_zone_name
  argocd_hostname                = var.argocd_hostname
  argocd_wait_for_acm_validation = var.argocd_wait_for_acm_validation
  argocd_ingress_stack_tag       = var.argocd_ingress_stack_tag
  cluster_name                   = module.eks_fargate.cluster_name
}

# State migration: Argo CD DNS/TLS resources were moved into `module.argocd_dns`.
# The next `terraform apply` will automatically move state using these blocks (no infra changes expected).
moved {
  from = aws_route53_zone.argocd_public
  to   = module.argocd_dns.aws_route53_zone.argocd_public
}

moved {
  from = aws_acm_certificate.argocd
  to   = module.argocd_dns.aws_acm_certificate.argocd
}

moved {
  from = aws_route53_record.argocd_cert_validation
  to   = module.argocd_dns.aws_route53_record.argocd_cert_validation
}

moved {
  from = aws_acm_certificate_validation.argocd
  to   = module.argocd_dns.aws_acm_certificate_validation.argocd
}

moved {
  from = aws_route53_record.argocd_a
  to   = module.argocd_dns.aws_route53_record.argocd_a
}

moved {
  from = aws_route53_record.argocd_aaaa
  to   = module.argocd_dns.aws_route53_record.argocd_aaaa
}

module "rds" {
  source             = "./modules/rds"
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

output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "eks_cluster_name" {
  value = module.eks_fargate.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks_fargate.cluster_endpoint
}

output "eks_cluster_ca_data" {
  value     = module.eks_fargate.cluster_certificate_authority_data
  sensitive = true
}

output "eks_oidc_provider_arn" {
  value = module.eks_fargate.oidc_provider_arn
}

output "eks_admin_principal_arns" {
  value       = module.eks_access.principal_arns
  description = "IAM principal ARNs granted cluster-admin access via EKS Access Entries."
}

output "eks_admin_access_policy_arn" {
  value       = module.eks_access.cluster_admin_access_policy_arn
  description = "EKS access policy ARN associated to the cluster admins."
}

output "alb_controller_role_arn" {
  value = module.alb_controller_irsa.role_arn
}

output "alb_controller_policy_arn" {
  value = module.alb_controller_irsa.policy_arn
}

output "argocd_image_updater_role_arn" {
  value       = module.argocd_image_updater_irsa.role_arn
  description = "IRSA role ARN to annotate the argocd-image-updater ServiceAccount (eks.amazonaws.com/role-arn)."
}

output "argocd_image_updater_policy_arn" {
  value       = module.argocd_image_updater_irsa.policy_arn
  description = "IAM policy ARN attached to the argocd-image-updater IRSA role."
}

output "cluster_autoscaler_role_arn" {
  value       = module.cluster_autoscaler_irsa.role_arn
  description = "IRSA role ARN to annotate the cluster-autoscaler ServiceAccount (eks.amazonaws.com/role-arn)."
}

output "cluster_autoscaler_policy_arn" {
  value       = module.cluster_autoscaler_irsa.policy_arn
  description = "IAM policy ARN attached to the cluster-autoscaler IRSA role."
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "rds_port" {
  value = module.rds.port
}

# Argo CD DNS/TLS outputs (re-exported)
output "argocd_acm_certificate_arn" {
  value       = module.argocd_dns.argocd_acm_certificate_arn
  description = "ACM certificate ARN for the Argo CD hostname (use in the Ingress certificate annotation)."
}

output "argocd_acm_dns_validation_records" {
  value       = module.argocd_dns.argocd_acm_dns_validation_records
  description = "DNS validation records to create in your DNS provider (useful when argocd_dns_provider=external)."
}

output "argocd_external_dns_cname" {
  value       = module.argocd_dns.argocd_external_dns_cname
  description = "Suggested external DNS record to point the Argo CD hostname to the ALB (requires your DNS provider to support the record type/name)."
}

output "argocd_alb_dns_name" {
  value       = module.argocd_dns.argocd_alb_dns_name
  description = "DNS name of the ALB created for the Argo CD Ingress."
}

output "argocd_public_zone_id" {
  value       = module.argocd_dns.argocd_public_zone_id
  description = "Route53 hosted zone ID used for argocd public DNS."
}

output "argocd_public_zone_name_servers" {
  value       = module.argocd_dns.argocd_public_zone_name_servers
  description = "Name servers for the created hosted zone (set these at your domain registrar)."
}
