variable "environment" {
  type        = string
  description = "Target deployment environment (staging or production)"
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "The environment must be either 'staging' or 'production'."
  }
}

variable "kubeconfig_path" {
  type        = string
  description = "Path to the kubeconfig file for local/cluster authentication"
  default     = "~/.kube/config"
}

variable "kubeconfig_context" {
  type        = string
  description = "Optional Kubernetes context name from kubeconfig"
  default     = null
}

variable "namespace" {
  type        = string
  description = "Kubernetes namespace to deploy into (defaults to gtfs-validator-<environment>)"
  default     = null
}

variable "chart_path" {
  type        = string
  description = "Filesystem path to the GTFS validator Helm chart"
  default     = "../helm/gtfs-validator"
}

variable "image_tag" {
  type        = string
  description = "Optional image tag override for deployment"
  default     = null
}

variable "replica_count" {
  type        = number
  description = "Optional replica count override for deployment"
  default     = null
}

