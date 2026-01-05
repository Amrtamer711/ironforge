variable "repository_names" {
  type        = list(string)
  description = "ECR repository names."
}

variable "force_delete" {
  type        = bool
  description = "Whether to force delete ECR repositories on destroy (deletes all images)."
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to repositories."
  default     = {}
}
