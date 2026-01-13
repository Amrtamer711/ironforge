# Argo CD repo credentials (GitLab)

Argo CD must be able to read this Git repository in order to sync Applications like `unifiedui-dev`.

This directory provides a Kustomize-managed `Secret` of type `repository`.

## Setup

1) Create `gitlab-repo.env` (this file is gitignored):

```bash
cp src/platform/ArgoCD/repo-credentials/gitlab-repo.env.example src/platform/ArgoCD/repo-credentials/gitlab-repo.env
```

2) Edit `src/platform/ArgoCD/repo-credentials/gitlab-repo.env`:

- `url`: `https://gitlab.com/mmg-global/ironforge.git`
- `username`: your GitLab **Deploy Token** username (recommended) or `oauth2` for a PAT
- `password`: the deploy token value (or PAT)

3) Apply:

```bash
kubectl apply -k src/platform/ArgoCD/repo-credentials
```

## Notes

- Recommended: GitLab Project → Settings → Access Tokens → **Deploy Token** with `read_repository`.
- After applying, Argo CD should be able to sync `Application` resources pointing at this repo.

