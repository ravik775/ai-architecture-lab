# Kubernetes Runbook

## Prerequisites
- Docker Desktop with Kubernetes enabled, or Minikube/Kind.
- kubectl installed.

## Build Local Images
From project root:
```bash
docker build -t service-registry:local -f services/service-registry/Dockerfile .
docker build -t api-gateway:local -f services/api-gateway/Dockerfile .
docker build -t loan-service:local -f services/loan-service/Dockerfile .
docker build -t credit-score-service:local -f services/credit-score-service/Dockerfile .
docker build -t document-verification-service:local -f services/document-verification-service/Dockerfile .
docker build -t notification-service:local -f services/notification-service/Dockerfile .
docker build -t loan-decision-service:local -f services/loan-decision-service/Dockerfile .
```

For Minikube, run first:
```bash
eval $(minikube docker-env)
```

## Deploy
```bash
kubectl apply -f k8s/
```

## Check Pods
```bash
kubectl get pods
kubectl get svc
```

## Access API Gateway
```bash
kubectl port-forward svc/api-gateway 8080:8080
```

Then test:
```bash
curl -X POST http://localhost:8080/loans -H "Content-Type: application/json" -d '{"customerId":"CUST-1001","customerName":"Ravi","amount":500000}'
```

## Cleanup
```bash
kubectl delete -f k8s/
```
