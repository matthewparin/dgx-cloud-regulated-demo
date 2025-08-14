# DGX Cloud Regulated Demo
A compact, **production-minded** example of running a secure AI microservice on Kubernetes with **Pod Security Standards (restricted)** and **infrastructure-as-code**.

The app exposes:
- `/` – health
- `/estimate` – simple legacy estimator (`nodes * hours * 10`)
- `/catalog` – GPU catalog (editable CSV)
- `/estimate/training` – realistic **time / cost / energy** training estimate
- `/estimate/training-grid` – run a grid across GPU counts/models

This repo intentionally keeps the surface area tiny: **Flask only**, a minimal Docker image, and **Terraform** that deploys **just** a namespace, hardened Deployment (with probes), and a Service.

---


Security posture:
- **PSS: restricted** on the namespace (prevents non-compliant pods)
- Container **non-root**, `allowPrivilegeEscalation: false`, **drop ALL** caps, **read-only** root FS, `seccompProfile: RuntimeDefault`
- Liveness/Readiness probes
- Resource requests/limits (sane defaults)

---

## Prereqs (macOS)
- **Docker Desktop** (running)
- **Homebrew** + CLIs:
  ```bash
  brew install kubernetes-cli kind
  brew tap hashicorp/tap && brew install hashicorp/tap/terraform
```


## 0) Fork → Clone

1) On GitHub, click **Fork** → your account.
2) Clone your fork and open it:
```bash
git clone https://github.com/matthewparin/dgx-cloud-regulated-demo.git
cd dgx-cloud-regulated-demo
code .
```

## Quick Start

## Terminal A - Build, Create Cluster, Deploy
### 0) Make sure Docker Desktop is running
```bash
open -a Docker || true
```

### 1) Build the app image
```bash
docker build -t cost-estimator:latest -f app/Dockerfile app
```

### 2) Create (or recreate) the Kind cluster
```bash
kind delete cluster --name dgx-demo || true
kind create cluster --name dgx-demo --image kindest/node:v1.28.9
kubectl config use-context kind-dgx-demo
kubectl wait --for=condition=Ready node --all --timeout=180s
```

### 3) Load the local image into the Kind node (air-gap-friendly)
```bash
kind load docker-image cost-estimator:latest --name dgx-demo
```

### 4) Apply the infrastructure
```bash
cd infra
terraform init
terraform apply -auto-approve
cd ..
```

## Terminal B - Run the service locally
```bash
kubectl -n restricted port-forward svc/cost-estimator-service 8080:80
```

## Teardown
```bash
# Stop port-forward
lsof -ti tcp:8080 | xargs -r kill

# Destroy Terraform resources (if cluster up)
cd infra && terraform destroy -auto-approve || true; cd ..

# Delete Kind cluster and local image
kind delete cluster --name dgx-demo || true
docker image rm -f cost-estimator:latest || true
```

## Troubleshooting

ImagePullBackOff → reload image and restart:
```bash
kind load docker-image cost-estimator:latest --name dgx-demo
kubectl -n restricted rollout restart deploy/cost-estimator
```

Empty Service ENDPOINTS → readiness failing or selector mismatch:
```bash
kubectl -n restricted get endpoints cost-estimator-service -o wide
kubectl -n restricted describe pods -l app=cost-estimator
```

Port 8080 busy → use a different local port:
```bash
kubectl -n restricted port-forward svc/cost-estimator-service 9090:80
```

Terraform “connection refused” → cluster not ready; recreate it:
```bash
kind delete cluster --name dgx-demo || true
kind create cluster --name dgx-demo --image kindest/node:v1.28.9
kubectl get nodes
```
