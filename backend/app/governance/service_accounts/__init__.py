"""Kubernetes Service Account configurations for AI agents.

This module defines service accounts that should be created in Kubernetes
to give AI agents the appropriate level of access.

Service Accounts:
- ai-dev-admin: Full admin access in development
- ai-staging-operator: Operator access in staging
- ai-prod-viewer: Read-only access in production
- ai-prod-operator: Limited operator access in production (scale only)
"""

SERVICE_ACCOUNTS = {
    "ai-dev-admin": {
        "description": "Full admin access for development environment",
        "namespace": "devops-ai",
        "environment": "development",
        "rules": [
            {"apiGroups": ["*"], "resources": ["*"], "verbs": ["*"]},
        ],
    },
    "ai-staging-operator": {
        "description": "Operator access for staging environment",
        "namespace": "devops-ai",
        "environment": "staging",
        "rules": [
            {"apiGroups": [""], "resources": ["pods", "services", "configmaps"], "verbs": ["get", "list", "watch"]},
            {"apiGroups": [""], "resources": ["pods"], "verbs": ["create", "delete", "deletecollection"]},
            {"apiGroups": ["apps"], "resources": ["deployments", "replicasets"], "verbs": ["get", "list", "watch", "update", "scale"]},
            {"apiGroups": ["apps"], "resources": ["deployments"], "verbs": ["rollback"]},
            {"apiGroups": ["batch"], "resources": ["jobs", "cronjobs"], "verbs": ["get", "list", "watch", "create"]},
        ],
    },
    "ai-prod-viewer": {
        "description": "Read-only access for production environment",
        "namespace": "devops-ai",
        "environment": "production",
        "rules": [
            {"apiGroups": [""], "resources": ["pods", "services", "configmaps", "secrets"], "verbs": ["get", "list", "watch"]},
            {"apiGroups": ["apps"], "resources": ["deployments", "replicasets", "statefulsets"], "verbs": ["get", "list", "watch"]},
            {"apiGroups": ["batch"], "resources": ["jobs", "cronjobs"], "verbs": ["get", "list", "watch"]},
        ],
    },
    "ai-prod-operator": {
        "description": "Limited operator access for production (scale only)",
        "namespace": "devops-ai",
        "environment": "production",
        "rules": [
            {"apiGroups": [""], "resources": ["pods", "services"], "verbs": ["get", "list", "watch"]},
            {"apiGroups": ["apps"], "resources": ["deployments", "replicasets"], "verbs": ["get", "list", "watch", "scale"]},
        ],
    },
}


def generate_service_account_manifest(sa_name: str, namespace: str = "devops-ai") -> str:
    """Generate Kubernetes manifest for a service account.

    Args:
        sa_name: Name of the service account
        namespace: Namespace for the service account

    Returns:
        YAML manifest
    """
    if sa_name not in SERVICE_ACCOUNTS:
        raise ValueError(f"Unknown service account: {sa_name}")

    sa_config = SERVICE_ACCOUNTS[sa_name]
    rules = sa_config["rules"]

    # Generate ClusterRole
    cluster_role_name = f"{sa_name}-clusterrole"

    manifest = f"""---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {sa_name}
  namespace: {namespace}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {cluster_role_name}
rules:
"""

    for rule in rules:
        api_groups = ", ".join([f'"{ag}"' for ag in rule["apiGroups"]])
        resources = ", ".join([f'"{r}"' for r in rule["resources"]])
        verbs = ", ".join([f'"{v}"' for v in rule["verbs"]])

        manifest += f"""- apiGroups: [{api_groups}]
  resources: [{resources}]
  verbs: [{verbs}]
"""

    # Generate ClusterRoleBinding
    manifest += f"""---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {sa_name}-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {cluster_role_name}
subjects:
- kind: ServiceAccount
  name: {sa_name}
  namespace: {namespace}
"""

    return manifest


def generate_all_manifests(namespace: str = "devops-ai") -> str:
    """Generate manifests for all service accounts.

    Args:
        namespace: Namespace for service accounts

    Returns:
        Combined YAML manifest
    """
    manifests = []
    for sa_name in SERVICE_ACCOUNTS:
        manifests.append(f"# {sa_name}\n")
        manifests.append(generate_service_account_manifest(sa_name, namespace))

    return "\n".join(manifests)


def get_service_account_for_environment(environment: str) -> str:
    """Get the appropriate service account for an environment.

    Args:
        environment: Environment name

    Returns:
        Service account name
    """
    env_map = {
        "development": "ai-dev-admin",
        "dev": "ai-dev-admin",
        "staging": "ai-staging-operator",
        "production": "ai-prod-viewer",  # Default to read-only
        "prod": "ai-prod-viewer",
    }

    return env_map.get(environment.lower(), "ai-prod-viewer")


def get_operator_service_account(environment: str) -> str:
    """Get the operator service account for an environment.

    For production, returns the limited operator account instead of viewer.

    Args:
        environment: Environment name

    Returns:
        Service account name
    """
    env_map = {
        "development": "ai-dev-admin",
        "dev": "ai-dev-admin",
        "staging": "ai-staging-operator",
        "production": "ai-prod-operator",
        "prod": "ai-prod-operator",
    }

    return env_map.get(environment.lower(), "ai-prod-viewer")
