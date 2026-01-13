# security-service — Kubernetes Deployment

Deploys the `security-service` FastAPI app into the cluster (namespace `backends`).

## Purpose (why you need this)

Other services (including `unified-ui` via `/api/security/*`) call this service for:
- RBAC lookups
- Audit logging
- API key validation
- Rate limiting

## In-cluster address

- `http://security-service.backends.svc.cluster.local:8002`
- Health: `GET /health`

## Deploy (Argo CD)

1. Ensure the ECR repo exists (Terraform): `security-service` was added to `ecr_repository_names` in `src/infrastructure/aws/main.tf`.
2. Apply the Argo CD Applications:
   - Demo: `kubectl apply -k src/platform/ArgoCD/applications`
   - Staging: `kubectl apply -k src/platform/ArgoCD/applications-staging`
   - Production: `kubectl apply -k src/platform/ArgoCD/applications-production`
3. Build + roll out:
   - Demo: push to `demo` → MR bumps `src/platform/deploy/kustomize/security-service/overlays/dev/kustomization.yaml`
   - Staging: push to `staging` → MR bumps `src/platform/deploy/kustomize/security-service/overlays/staging/kustomization.yaml`
   - Production: push to `main` → MR bumps `src/platform/deploy/kustomize/security-service/overlays/production/kustomization.yaml`
   - Merge the MR → Argo CD auto-syncs.
