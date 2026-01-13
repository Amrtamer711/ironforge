# Asset Management (Kustomize manifests)

This directory contains the Kubernetes manifests for deploying `asset-management` into the cluster using Kustomize.

Argo CD Application:
- Demo: `src/platform/ArgoCD/applications/assetmgmt-dev.yaml`
- Staging: `src/platform/ArgoCD/applications-staging/assetmgmt-staging.yaml`
- Production: `src/platform/ArgoCD/applications-production/assetmgmt-production.yaml`

## In-cluster address

- `http://asset-management.backends.svc.cluster.local:8001`
- Health: `GET /health`

## Image updates (pure GitOps)

The deployed image tag is controlled in Git:

- Demo: `src/platform/deploy/kustomize/asset-management/overlays/dev/kustomization.yaml` → `images[].newTag`
- Staging: `src/platform/deploy/kustomize/asset-management/overlays/staging/kustomization.yaml` → `images[].newTag`
- Production: `src/platform/deploy/kustomize/asset-management/overlays/production/kustomization.yaml` → `images[].newTag`

Push a change to `src/asset-management/**` on `demo`, `staging`, or `main` to build/push a new image. CI will open a GitOps MR to bump `newTag` (requires `GITLAB_BOT_TOKEN`), then merge it to deploy to that environment.

Note: the ECR repository name used for this service is `asset_library` (legacy naming).

## Runtime env (Kubernetes)

This Deployment can load runtime environment variables from a Secret named `asset-management-env` in the `backends` namespace (optional; pod will still start without it).

Recommended flow (keeps secrets out of Git):

1) Put your runtime settings into `src/asset-management/.env` (this repo already ignores `.env` files).
2) Apply/update the Secret and restart the pods:

```bash
make platform-assetmgmt-env
```
