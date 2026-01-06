# Argo CD TLS overlay (`bootstrap-tls`)

This overlay enables HTTPS on the Argo CD ALB Ingress by setting:
- `alb.ingress.kubernetes.io/certificate-arn`
- ALB HTTPS listener + HTTP→HTTPS redirect
- Ingress host

## Configure

Create a local env file (ignored by git):

```bash
cp src/platform/ArgoCD/bootstrap-tls/argocd-tls.env.example src/platform/ArgoCD/bootstrap-tls/argocd-tls.env
```

Edit `src/platform/ArgoCD/bootstrap-tls/argocd-tls.env`:
- `ARGOCD_HOSTNAME`: the hostname you will use (e.g. `argocd.example.com`)
- `ARGOCD_ACM_CERT_ARN`: ACM cert ARN in the same region as the cluster

## Apply

```bash
kubectl apply -k src/platform/ArgoCD/bootstrap-tls
```

## GoDaddy + apex hostname (delegate to Route53)

If you want to use the apex hostname (e.g. `argocdmmg.global`) with an ALB, delegate DNS to Route53 (GoDaddy remains the registrar).

Recommended: use the root `Makefile` targets.

```bash
make platform-argocd-tls-step1 AWS_PROFILE=your-profile ARGOCD_ZONE_NAME=argocdmmg.global ARGOCD_HOSTNAME=argocdmmg.global
```

Then set the GoDaddy domain nameservers to the Route53 values printed by the command.

```bash
make platform-argocd-tls-step2 AWS_PROFILE=your-profile ARGOCD_ZONE_NAME=argocdmmg.global ARGOCD_HOSTNAME=argocdmmg.global
```

`platform-argocd-tls-step2` writes `src/platform/ArgoCD/bootstrap-tls/argocd-tls.env` and applies the overlay.

## External DNS providers (no delegation)

If your DNS is not in Route53, Terraform can still request the ACM cert and output the DNS validation records:

```bash
terraform -chdir=src/infrastructure/aws apply \
  -var enable_argocd_public_dns=true \
  -var argocd_dns_provider=external \
  -var argocd_hostname=argocd.example.com \
  -var argocd_wait_for_acm_validation=false
```

Then:
- Add the `CNAME` validation record(s) from `terraform -chdir=src/infrastructure/aws output -json argocd_acm_dns_validation_records`
- Point your hostname to the Argo CD ALB hostname (from `kubectl -n argocd get ingress argocd-server -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{"\n"}'`)

Note: many DNS providers do not support a `CNAME` at the zone apex (e.g. `example.com`). If you run into that, use a subdomain like `argocd.example.com`, or move DNS for the domain/subdomain to a provider that supports ALIAS/CNAME-flattening.
