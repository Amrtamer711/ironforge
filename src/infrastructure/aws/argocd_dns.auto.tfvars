# Terraform auto-loaded variables for Argo CD public DNS/TLS.
#
# This repo expects Argo CD to be reachable at `https://argocdmmg.global` in the demo environment.
# Override any of these at runtime via `-var ...` if you need different values.

enable_argocd_public_dns       = true
argocd_dns_provider            = "route53"
create_argocd_public_zone      = true
argocd_public_zone_name        = "argocdmmg.global"
argocd_hostname                = "argocdmmg.global"
argocd_wait_for_acm_validation = true

