#!/usr/bin/env bash
# Sync policies/opa/*.rego into k8s/opa/policies-configmap.yaml.
#
# Phase 16 P1-9: the ConfigMap shipped an `allow := true` placeholder while
# the real policies lived only in the repo, so the OPA deployment evaluated
# nothing. The ConfigMap is generated; edit the Rego sources, then re-run:
#
#   ./scripts/sync-opa-policies.sh
#
# and commit both the policy and the regenerated manifest.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY_DIR="$ROOT/policies/opa"
TARGET="$ROOT/k8s/opa/policies-configmap.yaml"
POLICIES=(actions.rego resources.rego time_windows.rego compliance.rego)

python3 - "$POLICY_DIR" "$TARGET" "${POLICIES[@]}" <<'PYEOF'
import sys
from pathlib import Path

policy_dir, target = Path(sys.argv[1]), Path(sys.argv[2])
policy_files = sys.argv[3:]

entries = []
for name in policy_files:
    content = (policy_dir / name).read_text().rstrip("\n")
    indented = "\n".join("    " + line if line else "" for line in content.split("\n"))
    entries.append(f"  {name}: |\n{indented}")
configmap = "\n".join(entries)

target.write_text(f"""---
# OPA policy bundle — the REAL policies from policies/opa/*.rego, synced by
# scripts/sync-opa-policies.sh. Phase 16 P1-9: this ConfigMap held only an
# `allow := true` placeholder, so the deployment evaluated nothing.
# GENERATED FILE — edit policies/opa/*.rego and re-run the script.
apiVersion: v1
kind: ConfigMap
metadata:
  name: opa-policies
  namespace: opa
  labels:
    app: opa
data:
{configmap}
""")
print(f"synced {len(policy_files)} policies into {target}")
PYEOF
