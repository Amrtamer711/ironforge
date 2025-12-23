variable "repository_names" {
  type        = list(string)
  description = "ECR repository names."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to repositories."
  default     = {}
}
