output "role_arn" {
  value = aws_iam_role.this.arn
}

output "policy_arn" {
  value = aws_iam_policy.this.arn
}

output "service_account_annotation_role_arn" {
  value       = aws_iam_role.this.arn
  description = "Annotate the aws-load-balancer-controller ServiceAccount with eks.amazonaws.com/role-arn = this value."
}
