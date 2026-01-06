output "cluster_admin_access_policy_arn" {
  value       = local.cluster_admin_access_policy_arn
  description = "The EKS cluster access policy ARN used for cluster-admin."
}

output "principal_arns" {
  value       = var.principal_arns
  description = "The IAM principal ARNs granted cluster-admin access via EKS Access Entries."
}

output "access_entry_ids" {
  value       = { for k, v in aws_eks_access_entry.admin_t588 : k => v.id }
  description = "Access entry IDs keyed by principal ARN."
}