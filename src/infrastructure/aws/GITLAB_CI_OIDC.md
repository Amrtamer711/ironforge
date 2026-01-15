# GitLab CI → AWS (OIDC) for ECR pushes

The Docker build jobs in `.gitlab-ci.yml` push images to ECR by assuming an IAM role (`AWS_ROLE_ARN`) using a GitLab OIDC ID token (`AWS_ID_TOKEN` / `id_tokens`).

## Common failure on `staging`

If `demo` pipelines work but `staging` fails with:

`An error occurred (AccessDenied) when calling the AssumeRoleWithWebIdentity operation: Not authorized to perform sts:AssumeRoleWithWebIdentity`

then the IAM role trust policy usually allows only the `demo` branch `sub` claim. Add `staging` (and `main`) to the allowed `gitlab.com:sub` values.

`.gitlab-ci.yml` prints **sanitized** `aud`/`sub` claims so you can copy the exact values into the AWS trust policy.

## Required AWS configuration

1. **IAM OIDC provider** for GitLab:
   - Provider URL (issuer): `https://gitlab.com`
   - Audience / client ID list contains: `https://gitlab.com` (must match `.gitlab-ci.yml` `id_tokens: ... aud:`)

2. **IAM role** (the role referenced by `AWS_ROLE_ARN`) with:
   - `Action`: `sts:AssumeRoleWithWebIdentity`
   - `Principal.Federated`: `arn:aws:iam::<ACCOUNT_ID>:oidc-provider/gitlab.com`
   - Conditions for `aud` and `sub`

## Example trust policy (allow `demo`, `staging`, `main`)

Replace:
- `<ACCOUNT_ID>` with your AWS account ID (e.g. `018881300778`)
- `<PROJECT_PATH>` with your GitLab `CI_PROJECT_PATH` (e.g. `mmg-global/ironforge`)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/gitlab.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "gitlab.com:aud": "https://gitlab.com"
        },
        "StringLike": {
          "gitlab.com:sub": [
            "project_path:<PROJECT_PATH>:ref_type:branch:ref:demo",
            "project_path:<PROJECT_PATH>:ref_type:branch:ref:staging",
            "project_path:<PROJECT_PATH>:ref_type:branch:ref:main"
          ]
        }
      }
    }
  ]
}
```

