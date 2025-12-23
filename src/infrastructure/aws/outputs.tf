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
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "eks_cluster_ca_data" {
  value     = module.eks.cluster_certificate_authority_data
  sensitive = true
}

output "eks_oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
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

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "rds_port" {
  value = module.rds.port
}
