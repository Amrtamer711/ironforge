data "aws_partition" "current" {}

locals {
  # Grants full administrator access across the whole cluster.
  cluster_admin_access_policy_arn = "arn:${data.aws_partition.current.partition}:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  principals                     = toset(var.principal_arns)
}

resource "aws_eks_access_entry" "admin" {
  for_each = local.principals

  cluster_name  = var.cluster_name
  principal_arn = each.value

  # STANDARD entries can have one or more access policies associated.
  type = "STANDARD"

  tags = var.tags
}

resource "aws_eks_access_policy_association" "cluster_admin" {
  for_each = local.principals

  cluster_name  = var.cluster_name
  principal_arn = each.value
  policy_arn    = local.cluster_admin_access_policy_arn

  access_scope {
    type = "cluster"
  }

  depends_on = [aws_eks_access_entry.admin]
}
