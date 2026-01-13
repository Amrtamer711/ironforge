output "node_role_arn" {
  description = "IAM role ARN used by worker nodes."
  value       = var.enable ? aws_iam_role.nodes[0].arn : null
}

output "node_group_names" {
  description = "Created node group names."
  value = {
    general = (var.enable && var.general_enabled) ? aws_eks_node_group.general[0].node_group_name : null
    sales   = (var.enable && var.sales_enabled) ? aws_eks_node_group.sales[0].node_group_name : null
  }
}

