# AWS EKS clusters (staging + production)

This folder contains two Terraform root modules:

- `staging/` → EKS cluster `mmg-staging-cluster-1-t588`
- `production/` → EKS cluster `mmg-production-cluster-1-t588`

Both stacks use the shared `cluster_stack` module at `src/infrastructure/aws/modules/cluster_stack` so they stay in sync.

## Usage

Remote state is stored in the existing S3 backend:

- `clusters/staging/terraform.tfstate`
- `clusters/production/terraform.tfstate`

Terraform requires the RDS password to be provided (same as the demo stack):

```bash
export TF_VAR_db_password='...'
make infra-staging-apply AWS_PROFILE=your-profile
make infra-production-apply AWS_PROFILE=your-profile
```

## Notes

- These stacks intentionally do **not** create shared/global resources like ECR repositories or globally-named S3 buckets. The existing `src/infrastructure/aws` stack still owns those.
- Argo CD DNS/TLS is not created here (no domains needed for v1). Each cluster can run Argo CD via the default ALB Ingress hostname or `kubectl port-forward`.

