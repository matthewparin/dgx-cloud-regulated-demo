terraform {
  required_version = ">= 1.5.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.29"
    }
  }
}
provider "kubernetes" {
  # pathexpand avoids issues with "~" in some shells
  config_path    = pathexpand("~/.kube/config")
  config_context = "kind-dgx-demo"
}
resource "kubernetes_namespace" "restricted" {
  metadata {
    name = "restricted"
    labels = {
      "pod-security.kubernetes.io/enforce"         = "restricted"
      "pod-security.kubernetes.io/enforce-version" = "latest"
    }
  }
}
resource "kubernetes_deployment" "costapp" {
  metadata {
    name      = "cost-estimator"
    namespace = kubernetes_namespace.restricted.metadata[0].name
    labels    = { app = "cost-estimator" }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "cost-estimator" } }
    template {
      metadata { labels = { app = "cost-estimator" } }
      spec {
        container {
          name              = "cost-estimator"
          image             = "cost-estimator:latest"
          image_pull_policy = "IfNotPresent"
          port { container_port = 5000 }
          resources {
            limits   = { cpu = "200m", memory = "200Mi" }
            requests = { cpu = "100m", memory = "100Mi" }
          }
          security_context {
            run_as_non_root            = true
            allow_privilege_escalation = false
          }
        }
      }
    }
  }
}
resource "kubernetes_service" "costapp_service" {
  metadata {
    name      = "cost-estimator-service"
    namespace = kubernetes_namespace.restricted.metadata[0].name
  }
  spec {
    selector = { app = kubernetes_deployment.costapp.metadata[0].labels.app }
    port { port = 80, target_port = 5000, protocol = "TCP" }
    type = "ClusterIP"
  }
}
