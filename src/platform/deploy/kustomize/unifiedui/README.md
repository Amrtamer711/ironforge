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

This follows the same flow as Argo CD (request ACM, validate via DNS, then patch the Ingress with TLS annotations).

Choose one of these DNS setups:

- **Dedicated platform apex fully in Route53 (recommended)**:
  - Use a new apex domain (e.g. `mmgplatform.com`) that you point to Route53 nameservers at the registrar.
  - Run:

    ```bash
    make platform-apex-step1 AWS_PROFILE=your-profile PLATFORM_APEX=mmg-nova.com
    make platform-apex-step2 AWS_PROFILE=your-profile PLATFORM_APEX=mmg-nova.com
    ```

- **Route53 hosted zone for the subdomain** (common when only the subdomain is in Route53):
  - Use `SERVICEPLATFORM_ZONE_NAME=serviceplatform.mmg.global` (and set `SERVICEPLATFORM_CREATE_ZONE=false` if the zone already exists).
  - Ensure the parent DNS zone delegates the subdomain via NS records.
- **External DNS provider** (no Route53 DNS management):
  - Use `SERVICEPLATFORM_DNS_PROVIDER=external` and create the validation + CNAME records from Terraform outputs in your DNS provider.

```bash
make platform-unifiedui-tls-step1 AWS_PROFILE=your-profile SERVICEPLATFORM_ZONE_NAME=serviceplatform.mmg.global SERVICEPLATFORM_HOSTNAME=serviceplatform.mmg.global
make platform-unifiedui-tls-step2 AWS_PROFILE=your-profile SERVICEPLATFORM_ZONE_NAME=serviceplatform.mmg.global SERVICEPLATFORM_HOSTNAME=serviceplatform.mmg.global
make platform-unifiedui-url SERVICEPLATFORM_HOSTNAME=serviceplatform.mmg.global
```
