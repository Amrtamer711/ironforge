data "aws_partition" "current" {}

locals {
  node_role_name = coalesce(var.node_role_name, "${var.cluster_name}-node-role")

  # EKS node group names max out at 63 chars.
  # Prefix with cluster_name for easy identification, but hash if needed.
  general_node_group_name = (
    length("${var.cluster_name}-${var.general_name}") <= 63
    ? "${var.cluster_name}-${var.general_name}"
    : "${substr(var.cluster_name, 0, 40)}-${substr(md5(var.general_name), 0, 10)}"
  )

  sales_node_group_name = (
    length("${var.cluster_name}-${var.sales_name}") <= 63
    ? "${var.cluster_name}-${var.sales_name}"
    : "${substr(var.cluster_name, 0, 40)}-${substr(md5(var.sales_name), 0, 10)}"
  )
}

resource "aws_iam_role" "nodes" {
  count = var.enable ? 1 : 0

  name = local.node_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "eks_worker_node" {
  count = var.enable ? 1 : 0

  role       = aws_iam_role.nodes[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_cni" {
  count = var.enable ? 1 : 0

  role       = aws_iam_role.nodes[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  count = var.enable ? 1 : 0

  role       = aws_iam_role.nodes[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "ssm" {
  count = var.enable && var.enable_ssm ? 1 : 0

  role       = aws_iam_role.nodes[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_eks_node_group" "general" {
  count = var.enable && var.general_enabled ? 1 : 0

  cluster_name    = var.cluster_name
  node_group_name = local.general_node_group_name
  node_role_arn   = aws_iam_role.nodes[0].arn
  subnet_ids      = var.subnet_ids

  capacity_type  = var.capacity_type
  disk_size      = var.disk_size
  instance_types = var.general_instance_types

  scaling_config {
    min_size     = var.general_min_size
    desired_size = var.general_desired_size
    max_size     = var.general_max_size
  }

  update_config {
    max_unavailable = 1
  }

  labels = var.general_labels

  dynamic "taint" {
    for_each = var.general_taints
    content {
      key    = taint.value.key
      value  = taint.value.value
      effect = taint.value.effect
    }
  }

  tags = var.tags

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node,
    aws_iam_role_policy_attachment.eks_cni,
    aws_iam_role_policy_attachment.ecr_readonly,
    aws_iam_role_policy_attachment.ssm,
  ]
}

resource "aws_eks_node_group" "sales" {
  count = var.enable && var.sales_enabled ? 1 : 0

  cluster_name    = var.cluster_name
  node_group_name = local.sales_node_group_name
  node_role_arn   = aws_iam_role.nodes[0].arn
  subnet_ids      = var.subnet_ids

  capacity_type  = var.capacity_type
  disk_size      = var.disk_size
  instance_types = var.sales_instance_types

  scaling_config {
    min_size     = var.sales_min_size
    desired_size = var.sales_desired_size
    max_size     = var.sales_max_size
  }

  update_config {
    max_unavailable = 1
  }

  labels = var.sales_labels

  dynamic "taint" {
    for_each = var.sales_taints
    content {
      key    = taint.value.key
      value  = taint.value.value
      effect = taint.value.effect
    }
  }

  tags = var.tags

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node,
    aws_iam_role_policy_attachment.eks_cni,
    aws_iam_role_policy_attachment.ecr_readonly,
    aws_iam_role_policy_attachment.ssm,
  ]
}

