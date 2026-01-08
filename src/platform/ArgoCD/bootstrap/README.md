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

## Install platform applications

Argo CD needs `Application` resources to know what to deploy (Unified UI, sales module, security service, asset management, etc).

```bash
make platform-argocd-apps
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

- Recommended (lowest friction): dedicate an apex domain for the platform and manage it fully in Route53:
  1) Create the hosted zone (or use an existing one via `PLATFORM_APEX_HOSTED_ZONE_ID=...`) and request a single ACM cert:

     ```bash
     make platform-apex-step1 AWS_PROFILE=your-profile PLATFORM_APEX=mmg-nova.com
     ```

  2) In your registrar, update the domain’s nameservers to the Route53 values from the command output (skip if Route53 is your registrar).
  3) Finish ACM validation + create Route53 alias records + apply TLS to both Argo CD and Unified UI:

     ```bash
     make platform-apex-step2 AWS_PROFILE=your-profile PLATFORM_APEX=mmg-nova.com
     ```

  Troubleshooting (duplicate hosted zones): if Route53 shows multiple hosted zones named `mmg-nova.com`, prefer operating by zone id to avoid ambiguity:
  - Keep the zone that your registrar is using (compare `dig NS mmg-nova.com +short` with each zone’s `NameServers`).
  - If you want to switch to a manually-created/registration-created hosted zone, pass its id and disable zone creation:
    - `PLATFORM_APEX_CREATE_ZONE=false PLATFORM_APEX_HOSTED_ZONE_ID=Z...`
  - If Terraform previously created a zone, `make platform-apex-step1/step2` will automatically drop it from Terraform state when `PLATFORM_APEX_HOSTED_ZONE_ID` is set (so Terraform won’t try to destroy it). You can then delete the unused hosted zone in Route53.

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

## Unified UI (same pattern)

Unified UI is deployed by Argo CD from `src/platform/deploy/kustomize/unifiedui`.

To expose it with a custom hostname + TLS, use the same dedicated platform apex flow:

```bash
make platform-apex-step1 AWS_PROFILE=your-profile PLATFORM_APEX=mmg-nova.com
make platform-apex-step2 AWS_PROFILE=your-profile PLATFORM_APEX=mmg-nova.com
make platform-unifiedui-url PLATFORM_APEX=mmg-nova.com
```

## Unified UI image updates (pure GitOps)

CI pushes images with a unique tag (commit SHA). The deployed tag lives in Git:

- `src/platform/deploy/kustomize/unifiedui/overlays/dev/kustomization.yaml` → `images[].newTag`

To roll out a new image:

1) Build/push a new image tag (usually by pushing a commit to the `demo` branch).
2) Prefer: let CI open a GitOps merge request (MR) that bumps `newTag` automatically (recommended).
   - Create a GitLab CI variable `GITLAB_BOT_TOKEN` (bot PAT/project access token) with permission to push branches and create merge requests.
   - The pipeline will create an MR titled `Deploy unifiedui-dev: <sha>` targeting the `demo` branch.
   - Merge the MR to deploy.
   - Fallback: update `newTag` manually, commit, and push.
3) Argo CD syncs and Kubernetes rolls the Deployment.
