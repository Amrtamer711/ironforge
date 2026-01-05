# Argo CD bootstrap (cluster install)

This installs Argo CD itself into the cluster. After this is running, Argo CD can pull and reconcile the Applications in `src/platform/ArgoCD/applications`.

## Prereqs

- EKS cluster reachable via `kubectl`
- If your cluster is **Fargate-only**, ensure Terraform’s workload Fargate profile includes the `argocd` namespace (it does by default; see `src/infrastructure/aws/variables.tf`).

## Install

```bash
kubectl apply -k src/platform/ArgoCD/bootstrap
```

## Access (quick)

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Get the initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
```
