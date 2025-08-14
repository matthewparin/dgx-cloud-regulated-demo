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
  config_path    = pathexpand("~/.kube/config")
  config_context = "kind-dgx-demo"
}

# Namespace with Pod Security Standards: restricted
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
        automount_service_account_token = false

        container {
          name              = "cost-estimator"
          image             = "cost-estimator:latest"
          image_pull_policy = "IfNotPresent"

          port {
            container_port = 5000
          }

          # Health probes (must be multi-line with nested blocks)
          liveness_probe {
            http_get {
              path = "/"
              port = 5000
            }
            initial_delay_seconds = 5
            period_seconds        = 10
            timeout_seconds       = 2
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 5000
            }
            initial_delay_seconds = 3
            period_seconds        = 5
            timeout_seconds       = 2
            failure_threshold     = 3
          }

          # Resource governance
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

          # Security hardening — PSS: restricted
          security_context {
            run_as_non_root            = true
            allow_privilege_escalation = false
            read_only_root_filesystem  = true
            capabilities { drop = ["ALL"] }
            seccomp_profile { type = "RuntimeDefault" }
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
    selector = {
      app = "cost-estimator"
    }

    port {
      port        = 80
      target_port = 5000
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}
