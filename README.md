# DGX Cloud Regulated Environment Demo
*A compact, production-minded slice of a secure AI platform for regulated environments (gov/health/finance).*

**What you get**
- **App**: Python/Flask service with endpoints for a **GPU training cost/time/energy** estimator
  - `/` (health), `/catalog` (GPU catalog), `/estimate` (simple),
    `/estimate/training` (single scenario), `/estimate/training-grid` (batch)
- **Security**: Docker image runs **non-root**; K8s namespace enforces **Pod Security Standards (restricted)**; deployment hardened (no priv-esc, drop **ALL** caps, read-only FS, seccomp RuntimeDefault)
- **Infra**: **Terraform** defines namespace + labels, LimitRange/ResourceQuota, Deployment, Service
- **Orchestration**: **Kind** (Kubernetes-in-Docker) for portable local clusters
- **Data**: Curated **GPU catalog** + optional **Azure Retail Prices** fetcher to populate live per-GPU $/h
- **Polish**: **Liveness/Readiness** probes, **Makefile**, and CI (Terraform fmt/validate + Docker build)

---

## 0) Fork → Clone

1) On GitHub, click **Fork** → your account.
2) Clone your fork and open it:
```bash
git clone https://github.com/matthewparin/dgx-cloud-regulated-demo.git
cd dgx-cloud-regulated-demo
code .
```

## Quick Start

## Terminal A - Bring everything up
### Build
```bash
docker build -t cost-estimator:latest -f app/Dockerfile app
```

### Kind up
```bash
kind delete cluster --name dgx-demo || true
kind create cluster --name dgx-demo --image kindest/node:v1.28.9
kubectl config use-context kind-dgx-demo
kubectl wait --for=condition=Ready node --all --timeout=180s
```

### Load image into node (may need to do only once)
```bash
kind load docker-image cost-estimator:latest --name dgx-demo
```

### Terraform
```bash
cd infra
terraform init
terraform apply -auto-approve
cd ..
```

### Expose the service locally (keeps running in this terminal)
```bash
kubectl -n restricted port-forward svc/cost-estimator-service 8080:80
```

## Terminal B - run & test
```bash
curl -s -X POST http://localhost:8080/estimate/training \
  -H 'Content-Type: application/json' \
  -d '{"gpu_model":"H100-80GB","num_gpus":8,"model_params_b":7,"tokens_b":1,"price_tier":"on_demand"}' | jq .
```

## Teardown
### Stop any local port-forward on 8080
```bash
lsof -ti tcp:8080 | xargs -r kill
```

### Destroy Terraform resources (if cluster exists)
```bash
cd infra && terraform destroy -auto-approve || true; cd ..
```

### Delete Kind cluster and local image
```bash
kind delete cluster --name dgx-demo || true
docker image rm -f cost-estimator:latest || true
```

### Troubleshooting (fast)

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
kind delete cluster --name dgx-demo && make kind-up
```
