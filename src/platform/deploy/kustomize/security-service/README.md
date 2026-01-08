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
   - `kubectl apply -k src/platform/ArgoCD/applications`
3. Build + roll out:
   - Push a commit to `demo` touching `src/security-service`
   - CI pushes `.../security-service:<CI_COMMIT_SHORT_SHA>` and opens an MR to bump:
     - `src/platform/deploy/kustomize/security-service/overlays/dev/kustomization.yaml`
   - Merge the MR → Argo CD auto-syncs.

