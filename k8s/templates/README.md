# k8s/templates/

Reference manifests that must NEVER be applied as-is and must never live
inside an ArgoCD-synced directory (`k8s/backend`, `k8s/staging`,
`k8s/postgresql`, ... — those sync with `selfHeal`, which would overwrite
real out-of-band Secret values with these empty placeholders on every sync).

Create real Secrets out-of-band, per the header of each template:
- `staging-secrets-template.yaml` — via `~/.staging-secrets` sourced by
  `scripts/deploy-staging.sh`
- `postgres-credentials-template.yaml` — via `kubectl create secret generic postgres-credentials ...`
