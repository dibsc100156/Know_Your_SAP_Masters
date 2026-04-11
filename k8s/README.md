# Kubernetes Deployment Guide — Know Your SAP Masters

## Prerequisites

```bash
# 1. kubectl configured
kubectl config current-context  # verify cluster access

# 2. Create namespace
kubectl apply -f k8s/base/namespace.yaml

# 3. Create secrets (edit credentials first!)
#    NEVER commit real credentials
cat <<EOF > k8s/overlays/prod/hana_password.txt
YourRealHANAPassword
EOF
kubectl create secret generic sap-masters-secrets \
  -n sap-masters \
  --from-literal=HANA_DB_USER=YOUR_USER \
  --from-file=HANA_DB_PASSWORD=k8s/overlays/prod/hana_password.txt \
  --from-literal=RABBITMQ_PASSWORD=ProdSecurePassword \
  --from-literal=MINIO_ACCESS_KEY=sapmasters \
  --from-file=MINIO_SECRET_KEY=k8s/overlays/prod/minio_password.txt

# 4. Install KEDA (required for RabbitMQ queue-based autoscaling)
kubectl apply -f https://kedacore.io/keda-2.14.2.yaml

# 5. Install NGINX Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml

# 6. Install metrics-server (required for HPA CPU/memory scaling)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

## Deploy

### Dev (mock data, no HANA required)
```bash
kubectl apply -k k8s/overlays/dev
```

### Staging (pool mode, staging HANA)
```bash
kubectl apply -k k8s/overlays/staging
```

### Production (real HANA, full HA)
```bash
# 1. Create secrets with real credentials
kubectl apply -k k8s/overlays/prod

# 2. Verify all pods running
kubectl get pods -n sap-masters -w

# 3. Check HPA status
kubectl get hpa -n sap-masters
kubectl get hpa -n sap-masters --watch

# 4. Check KEDA scalers
kubectl get scaledobject -n sap-masters
kubectl get scaledobject -n sap-masters --watch
```

## Verify

```bash
# Pods
kubectl get pods -n sap-masters

# Services
kubectl get svc -n sap-masters

# HPA (CPU/memory autoscaling)
kubectl get hpa -n sap-masters

# KEDA ScaledObjects (queue-based autoscaling)
kubectl get scaledobject -n sap-masters

# Logs
kubectl logs -n sap-masters deployment/backend --tail=100 -f
kubectl logs -n sap-masters deployment/celery-primary --tail=50 -f

# Pod resource usage
kubectl top pods -n sap-masters
```

## Access Services

```bash
# Port-forward for local access (dev)
kubectl port-forward -n sap-masters svc/backend 8000:8000 &
kubectl port-forward -n sap-masters svc/flower 5555:5555 &
kubectl port-forward -n sap-masters svc/rabbitmq 15672:15672 &

# API
curl http://localhost:8000/health

# Flower (Celery monitoring)
open http://localhost:5555

# RabbitMQ Management
open http://localhost:15672

# Memgraph Lab (graph visualization)
kubectl port-forward -n sap-masters svc/memgraph-lab 3000:3000 &
open http://localhost:3000
```

## Scaling

```bash
# Manual scale (dev/staging)
kubectl scale deployment backend -n sap-masters --replicas=4
kubectl scale deployment celery-primary -n sap-masters --replicas=4

# Check scaling events
kubectl describe hpa backend-hpa -n sap-masters
kubectl describe scaledobject celery-primary-scaler -n sap-masters

# Watch KEDA scaling decisions
kubectl logs -n keda deployment/keda-operator -f
```

## Update (Rolling Update)

```bash
# Push new image
docker build -t sapmasters/backend:v0.3.1 ./backend
docker push sapmasters/backend:v0.3.1

# Rolling update
kubectl set image deployment/backend backend=sapmasters/backend:v0.3.1 -n sap-masters
kubectl rollout status deployment/backend -n sap-masters

# Celery workers (no downtime — rolling update)
kubectl set image deployment/celery-primary celery-worker=sapmasters/backend:v0.3.1 -n sap-masters
kubectl rollout status deployment/celery-primary -n sap-masters
```

## Troubleshooting

```bash
# Pod stuck in Pending (PVC issues)
kubectl describe pvc -n sap-masters
kubectl get events -n sap-masters --sort-by=.lastTimestamp

# HPA not scaling (metrics-server issue)
kubectl top pods -n sap-masters  # must show CPU/memory
kubectl get apiservices | grep metrics

# KEDA not scaling (RabbitMQ connectivity)
kubectl logs -n keda deployment/keda-operator --tail=100
kubectl get scaledobject celery-primary-scaler -n sap-masters -o yaml

# Circuit breaker open (HANA pool)
kubectl exec -n sap-masters deployment/backend -- python -c \
  "from app.tools.hana_pool import get_pool; print(get_pool().stats())"

# Network policy blocking (Denial)
kubectl describe networkpolicy default-deny-all -n sap-masters
```

## Architecture

```
                    ┌─────────────────────────────────────────────────────┐
External ──────────►│ NGINX Ingress (rate-limit, TLS)                   │
                    └─────┬────────────────────────────────────────────┘
                          │ :8000
          ┌──────────────▼──────────────┐
          │   Backend API (HPA 2-10)   │
          │   FastAPI + Session Middleware │
          └──────┬──────────────────┬───┘
                 │ Celery tasks        │ Direct queries
     ┌──────────▼──────┐    ┌────────▼────────┐
     │ celery-primary   │    │  Memgraph      │
     │ (KEDA: queue)   │    │  (Graph RAG)   │
     │ HPA: 2-20       │    └────────────────┘
     └────────┬─────────┘
               │
  ┌───────────┼──────────────────────┐
  │          │                      │
▼▼          ▼▼                     ▼
Qdrant    Redis          Memgraph (Graph RAG)
(Schema   (Sessions,    Qdrant    SAP HANA
 RAG)     Celery Results (Patterns)
```
