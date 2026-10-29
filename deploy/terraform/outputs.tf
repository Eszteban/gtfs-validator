output "environment" {
  description = "Deployed environment name"
  value       = var.environment
}

output "namespace" {
  description = "Kubernetes namespace where the application is deployed"
  value       = kubernetes_namespace.gtfs_namespace.metadata[0].name
}

output "release_name" {
  description = "Helm release name deployed by Terraform"
  value       = helm_release.gtfs_validator.name
}

output "release_status" {
  description = "Status of the deployed Helm release"
  value       = helm_release.gtfs_validator.status
}

output "service_internal_dns" {
  description = "Internal Kubernetes ClusterIP service DNS address"
  value       = "${helm_release.gtfs_validator.name}.${kubernetes_namespace.gtfs_namespace.metadata[0].name}.svc.cluster.local:8000"
}

