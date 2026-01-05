# Kubernetes Platform (ArgoCD + Kustomize)

Terraform provisions infrastructure (VPC/EKS/Fargate/IAM). Kubernetes app configuration is deployed by ArgoCD from this directory.

## Unified UI

Kustomize manifests live at:
- `src/platform/deploy/kustomize/unifiedui/base`
- `src/platform/deploy/kustomize/unifiedui/overlays/dev`

ArgoCD Application example:
- `src/platform/ArgoCD/applications/unifiedui-dev.yaml`
- `src/platform/ArgoCD/applications/aws-load-balancer-controller.yaml`

Bootstrap ArgoCD itself:
- `src/platform/ArgoCD/bootstrap/README.md`

## Public access and future APIs

The Unified UI is exposed via an AWS ALB Ingress (AWS Load Balancer Controller). This works well for:
- browser access to the UI
- routing additional API services later (host/path based routing) so the UI can call same-origin endpoints like `/api/...`
