locals {
  target_namespace = var.namespace != null ? var.namespace : "gtfs-validator-${var.environment}"
  release_name     = "gtfs-validator-${var.environment}"
  chart_directory  = "${path.module}/${var.chart_path}"

  base_values_file = "${local.chart_directory}/values.yaml"
  env_values_file  = "${local.chart_directory}/values-${var.environment}.yaml"

  values_files = fileexists(local.env_values_file) ? [
    file(local.base_values_file),
    file(local.env_values_file)
    ] : [
    file(local.base_values_file)
  ]
}

provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kubeconfig_context
}

provider "helm" {
  kubernetes {
    config_path    = var.kubeconfig_path
    config_context = var.kubeconfig_context
  }
}

# 1. Deklaratív Kubernetes Namespace létrehozása az adott környezethez
resource "kubernetes_namespace" "gtfs_namespace" {
  metadata {
    name = local.target_namespace

    labels = {
      "app.kubernetes.io/name"       = "gtfs-validator"
      "app.kubernetes.io/managed-by" = "terraform"
      "environment"                  = var.environment
    }
  }
}

# 2. GTFS Validator Helm Release telepítése a környezeti értékekkel
resource "helm_release" "gtfs_validator" {
  name      = local.release_name
  chart     = local.chart_directory
  namespace = kubernetes_namespace.gtfs_namespace.metadata[0].name
  timeout   = 300
  wait      = false

  values = local.values_files

  dynamic "set" {
    for_each = var.image_tag != null ? [var.image_tag] : []
    content {
      name  = "image.tag"
      value = set.value
    }
  }

  dynamic "set" {
    for_each = var.replica_count != null ? [var.replica_count] : []
    content {
      name  = "replicaCount"
      value = set.value
    }
  }
}
