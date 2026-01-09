# Video Critique — Kubernetes Deployment

Deploys the `video-critique` FastAPI service into the cluster (namespace `backends`).

## In-cluster address

- `http://video-critique.backends.svc.cluster.local:8003`
- Health: `GET /health`

## Deploy (Argo CD)

1. Ensure the ECR repo exists (Terraform): add `video-critique` to `ecr_repository_names` in `src/infrastructure/aws/main.tf` and apply.
2. Apply the Argo CD Applications:
   - `kubectl apply -k src/platform/ArgoCD/applications`
3. Build + roll out:
   - Push a commit to `demo` touching `src/video-critique`
   - CI pushes `.../video-critique:<CI_COMMIT_SHORT_SHA>` and opens an MR to bump:
     - `src/platform/deploy/kustomize/video-critique/overlays/dev/kustomization.yaml`
   - Merge the MR → Argo CD auto-syncs.

## Runtime env (Kubernetes)

This Deployment can load runtime environment variables from a Secret named `video-critique-env` in the `backends` namespace (optional).

Recommended flow (keeps secrets out of Git):

1) Put your runtime settings into `src/video-critique/.env` (this repo already ignores `.env` files).
2) Apply/update the Secret and restart the pods:

```bash
make platform-videocritique-env
```

