variable "bucket_names" {
  type        = list(string)
  description = "Bucket names to create."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to buckets."
  default     = {}
}
