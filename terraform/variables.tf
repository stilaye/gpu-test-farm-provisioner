variable "node_count" {
  description = "Number of GPU test node containers to provision"
  type        = number
  default     = 2
}

variable "node_image_tag" {
  description = "Tag for the GPU node container image"
  type        = string
  default     = "latest"
}

variable "cuda_test_image_tag" {
  description = "Tag for the CUDA test workload container image"
  type        = string
  default     = "latest"
}
