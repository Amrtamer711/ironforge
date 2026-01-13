output "name_prefix" {
  value = module.cluster.name_prefix
}

output "vpc_id" {
  value = module.cluster.vpc_id
}

output "eks_cluster_name" {
  value = module.cluster.eks_cluster_name
}

output "alb_controller_role_arn" {
  value = module.cluster.alb_controller_role_arn
}

output "cluster_autoscaler_role_arn" {
  value = module.cluster.cluster_autoscaler_role_arn
}

output "rds_endpoint" {
  value = module.cluster.rds_endpoint
}

