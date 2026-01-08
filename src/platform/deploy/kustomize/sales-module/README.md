# Sales Module (proposal-bot) — Kubernetes Deployment

This deploys the `sales-module` FastAPI service (named `proposal-bot`) into the cluster and makes it reachable from `unified-ui` via in-cluster DNS.

## What gets deployed

- Namespace: `backends`
- Service DNS (from inside the cluster): `http://proposal-bot.backends.svc.cluster.local:8000`
- Health endpoint: `GET /health`

## Deploy (Argo CD)

1. Ensure the ECR repo exists (Terraform):
   - Add `proposal-bot` to `ecr_repository_names` (already done in `src/infrastructure/aws/main.tf`)
   - Run your normal Terraform apply for `src/infrastructure/aws`

2. Apply the Argo CD Application:
   - `kubectl apply -k src/platform/ArgoCD/applications`

3. Build/push + roll out a real image tag:
   - Push a commit to `demo` touching `src/sales-module`
   - CI builds/pushes `018881300778.dkr.ecr.eu-north-1.amazonaws.com/proposal-bot:<CI_COMMIT_SHORT_SHA>`
   - CI opens an MR to bump `src/platform/deploy/kustomize/sales-module/overlays/dev/kustomization.yaml` `newTag`
   - Merge the MR and Argo CD auto-syncs

