# Argo CD bootstrap (cluster install)

This installs Argo CD itself into the cluster. After this is running, Argo CD can pull and reconcile the Applications in `src/platform/ArgoCD/applications`.

## Prereqs

- AWS credentials available locally (recommended: use `AWS_PROFILE`)
- EKS cluster reachable via `kubectl`
- If your cluster is **Fargate-only**, ensure Terraform’s workload Fargate profile includes the `argocd` namespace (it does by default; see `src/infrastructure/aws/variables.tf`).
- Ensure CoreDNS is running (cluster DNS). If `coredns` pods are `Pending`, Argo CD components may crash-loop:
  - `kubectl -n kube-system get pods -l k8s-app=kube-dns`
  - `kubectl -n kube-system rollout restart deploy/coredns`

## Infrastructure (Terraform)

Use the root `Makefile` to deploy AWS infrastructure.

1) (Optional) Create a remote state backend (S3 + DynamoDB lock):

```bash
make infra-bootstrap AWS_PROFILE=your-profile
```

Note: to use the remote backend, uncomment the backend block in `src/infrastructure/aws/backend.tf` and run:

```bash
make infra-init AWS_PROFILE=your-profile
```

2) Deploy the AWS infrastructure (EKS, networking, etc):

```bash
make infra-apply AWS_PROFILE=your-profile
```

3) Configure kubeconfig (region is `eu-north-1` by default in Terraform):

```bash
aws eks update-kubeconfig \
  --region eu-north-1 \
  --name "$(terraform -chdir=src/infrastructure/aws output -raw eks_cluster_name)"
```

## Install

```bash
make platform-argocd-bootstrap
```

## Access

Recommended: expose via an internet-facing ALB Ingress (requires AWS Load Balancer Controller):

```bash
kubectl -n argocd get ingress argocd-server
```

If the Ingress `ADDRESS` is empty, install the AWS Load Balancer Controller and wait for it to reconcile.

Open it in your browser using HTTP (the bootstrap config sets `server.insecure=true`):

```bash
make platform-argocd-url
```

## TLS (secure browser)

To avoid “Connection not secure”, terminate TLS at the ALB using an ACM certificate and a real hostname.

This repo supports two common setups:

- GoDaddy registrar + Route53 DNS delegation (works for apex hostname, e.g. `argocdmmg.global`):
  1) Create the hosted zone + request ACM cert (prints the nameservers you must set in GoDaddy):

     ```bash
     make platform-argocd-tls-step1 AWS_PROFILE=your-profile ARGOCD_ZONE_NAME=argocdmmg.global ARGOCD_HOSTNAME=argocdmmg.global
     ```

  2) In GoDaddy, update the domain’s nameservers to the Route53 values from the command output.
  3) Finish ACM validation + apply the TLS overlay:

     ```bash
     make platform-argocd-tls-step2 AWS_PROFILE=your-profile ARGOCD_ZONE_NAME=argocdmmg.global ARGOCD_HOSTNAME=argocdmmg.global
     ```

- External DNS provider without delegation (requires a subdomain hostname, e.g. `argocd.example.com`):
  - See `src/platform/ArgoCD/bootstrap-tls/README.md`.

If you prefer local-only access, use port-forward instead:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:80
```

Get the initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
```
