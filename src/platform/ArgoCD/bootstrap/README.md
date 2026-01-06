# Argo CD bootstrap (cluster install)

This installs Argo CD itself into the cluster. After this is running, Argo CD can pull and reconcile the Applications in `src/platform/ArgoCD/applications`.

## Prereqs

- EKS cluster reachable via `kubectl`
- If your cluster is **Fargate-only**, ensure Terraform’s workload Fargate profile includes the `argocd` namespace (it does by default; see `src/infrastructure/aws/variables.tf`).
- Ensure CoreDNS is running (cluster DNS). If `coredns` pods are `Pending`, Argo CD components may crash-loop:
  - `kubectl -n kube-system get pods -l k8s-app=kube-dns`
  - `kubectl -n kube-system rollout restart deploy/coredns`

## Install

```bash
kubectl apply -k src/platform/ArgoCD/bootstrap
```

## Access

Recommended: expose via an internet-facing ALB Ingress (requires AWS Load Balancer Controller):

```bash
kubectl -n argocd get ingress argocd-server
```

If the Ingress `ADDRESS` is empty, install the AWS Load Balancer Controller and wait for it to reconcile.

Open it in your browser using HTTP (the bootstrap config sets `server.insecure=true`):

```bash
echo "http://$(kubectl -n argocd get ingress argocd-server -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
```

If you prefer local-only access, use port-forward instead:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:80
```

Get the initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
```
