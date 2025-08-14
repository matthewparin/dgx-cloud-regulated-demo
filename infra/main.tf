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
  config_path    = "~/.kube/config"
  config_context = "kind-dgx-demo"
}

# Namespace with Pod Security Standards enforced at 'restricted'
resource "kubernetes_namespace" "restricted" {
  metadata {
    name = "restricted"
    labels = {
      "pod-security.kubernetes.io/enforce"         = "restricted"
      "pod-security.kubernetes.io/enforce-version" = "latest"
    }
  }
}

# Application Deployment
resource "kubernetes_deployment" "costapp" {
  metadata {
    name      = "cost-estimator"
    namespace = kubernetes_namespace.restricted.metadata[0].name
    labels = {
      app = "cost-estimator"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "cost-estimator"
      }
    }

    template {
      metadata {
        labels = {
          app = "cost-estimator"
        }
      }

      spec {
        container {
          name               = "cost-estimator"
          image              = "cost-estimator:latest"
          image_pull_policy  = "IfNotPresent"

          port {
            container_port = 5000
          }

          # Resource governance (cost discipline)
          resources {
            limits = {
              cpu    = "200m"
              memory = "200Mi"
            }
            requests = {
              cpu    = "100m"
              memory = "100Mi"
            }
          }

          # Security hardening — required by 'restricted' profile
          security_context {
            run_as_non_root            = true
            allow_privilege_escalation = false
          }
        }
      }
    }
  }
}

# ClusterIP Service
resource "kubernetes_service" "costapp_service" {
  metadata {
    name      = "cost-estimator-service"
    namespace = kubernetes_namespace.restricted.metadata[0].name
  }

  spec {
    selector = {
      app = kubernetes_deployment.costapp.metadata[0].labels.app
    }

    port {
      port        = 80
      target_port = 5000
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}
