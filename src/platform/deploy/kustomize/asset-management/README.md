# Asset Management (Kustomize manifests)

This directory contains the Kubernetes manifests for deploying `asset-management` into the cluster using Kustomize.

Argo CD Application:
- `src/platform/ArgoCD/applications/assetmgmt-dev.yaml`

## In-cluster address

- `http://asset-management.backends.svc.cluster.local:8001`
- Health: `GET /health`

## Image updates (pure GitOps)

The deployed image tag is controlled in Git:

- `src/platform/deploy/kustomize/asset-management/overlays/dev/kustomization.yaml` → `images[].newTag`

Push a change to `src/asset-management/**` on the `demo` branch to build/push a new image. CI will open a GitOps MR to bump `newTag` (requires `GITLAB_BOT_TOKEN`), then merge it to deploy.

Note: the ECR repository name used for this service is `asset_library` (legacy naming).

## Runtime env (Kubernetes)

This Deployment can load runtime environment variables from a Secret named `asset-management-env` in the `backends` namespace (optional; pod will still start without it).
