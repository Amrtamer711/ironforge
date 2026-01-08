# Unified UI (Kustomize manifests)

This directory contains the Kubernetes manifests for deploying `unified-ui` into the cluster using Kustomize.

In the demo setup, these manifests are applied by Argo CD via the `Application` at:

- `src/platform/ArgoCD/applications/unifiedui-dev.yaml`

## In-cluster API traffic model

`unified-ui` is expected to call backend services using in-cluster DNS, e.g.:

- `http://proposal-bot.sales.svc.cluster.local:8000`

These endpoints should be passed to the UI as environment variables (see the `overlays/dev` patch in `kustomization.yaml`).

## Access

Get the ALB hostname:

```bash
kubectl -n unifiedui get ingress unified-ui -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{"\n"}'
```

## Custom hostname + TLS (Route53 + ACM)

Unified UI uses the dedicated platform apex flow (single hosted zone + single ACM cert) managed by the standalone stack in `src/infrastructure/aws/modules/stacks/platform_apex`.

```bash
make platform-apex-step1 AWS_PROFILE=your-profile PLATFORM_APEX=mmg-nova.com
make platform-apex-step2 AWS_PROFILE=your-profile PLATFORM_APEX=mmg-nova.com
make platform-unifiedui-url PLATFORM_APEX=mmg-nova.com
```

## Image updates (pure GitOps)

The deployed image tag is controlled in Git:

- `src/platform/deploy/kustomize/unifiedui/overlays/dev/kustomization.yaml` → `images[].newTag`

Recommended: let CI open a GitOps merge request that bumps `newTag` automatically, then merge it to deploy.

- Create a GitLab CI variable `GITLAB_BOT_TOKEN` with permission to push branches and create merge requests.
- Push a change to `src/unified-ui/**` on the `demo` branch.
- Merge the generated MR titled `Deploy unifiedui-dev: <sha>`.

## Supabase / runtime env (Kubernetes)

Unified UI expects Supabase environment variables at runtime (see `src/unified-ui/.env.example` for the canonical list).

For Kubernetes, runtime env vars are loaded from a Secret named `unified-ui-env` (see `envFrom` in `src/platform/deploy/kustomize/unifiedui/overlays/dev/kustomization.yaml`).

1) Create `src/unified-ui/supabase.env` from the example and fill values from Render (this file is gitignored):

```bash
cp src/unified-ui/supabase.env.example src/unified-ui/supabase.env
```

2) Apply/update the secret:

```bash
make platform-unifiedui-env
```
