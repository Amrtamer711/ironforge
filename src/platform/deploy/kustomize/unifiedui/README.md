# Unified UI (Kustomize manifests)

This directory contains the Kubernetes manifests for deploying `unified-ui` into the cluster using Kustomize.

In the demo setup, these manifests are applied by Argo CD via the `Application` at:

- `src/platform/ArgoCD/applications/unifiedui-dev.yaml`
- `src/platform/ArgoCD/applications/unifiedui-prod.yaml` (SemVer release flow)

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

## Releases (SemVer)

CI publishes immutable SemVer image tags (e.g. `1.2.3`) when you create a git tag (e.g. `v1.2.3`).

Production uses `overlays/prod` and expects `images[].newTag` to be set to the desired SemVer tag.
