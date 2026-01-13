output "name_prefix" {
  value       = local.name_prefix
  description = "Naming prefix used for this environment (project-environment)."
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

output "eks_cluster_security_group_id" {
  value = module.eks_fargate.cluster_security_group_id
}

output "eks_oidc_provider_arn" {
  value = module.eks_fargate.oidc_provider_arn
}

output "eks_oidc_provider_url" {
  value = module.eks_fargate.oidc_provider_url
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

