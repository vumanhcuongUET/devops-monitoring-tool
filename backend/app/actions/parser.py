"""Command parser for kubectl, helm, and argocd commands."""

import re
import shlex
from typing import Optional

from app.models.actions import CommandParams, CommandType


class CommandParser:
    """Parse shell commands into structured parameters."""

    # kubectl patterns
    KUBECTL_RESOURCE_PATTERN = re.compile(
        r"(?:get|describe|logs|delete|exec|rollout|scale|top|apply)"
    )

    # kubectl resource types (exact matches)
    KUBECTL_RESOURCE_TYPES = {
        "pod", "pods", "po",
        "deployment", "deployments", "deploy",
        "service", "services", "svc",
        "statefulset", "statefulsets", "sts",
        "daemonset", "daemonsets", "ds",
        "namespace", "namespaces", "ns",
        "configmap", "configmaps", "cm",
        "secret", "secrets",
        "node", "nodes", "no",
        "endpoints", "ep",
        "ingress", "ingresses", "ing",
        "persistentvolume", "persistentvolumes", "pv",
        "persistentvolumeclaim", "persistentvolumeclaims", "pvc",
        "storageclass", "storageclasses", "sc",
    }

    # kubectl boolean flags (no value expected)
    KUBECTL_BOOLEAN_FLAGS = {
        "f", "follow", "w", "watch", "h", "help", "v", "verbose",
        "all-namespaces", "A", "show-labels", "show-all",
        "dry-run", "server-side", "force", "cascade", "grace-period",
        "field-manager", "insecure-skip-tls-verify",
    }

    # helm patterns
    HELM_COMMAND_PATTERN = re.compile(r"(?:install|upgrade|uninstall|rollback|list|status)")

    # argocd patterns
    ARGOCD_COMMAND_PATTERN = re.compile(r"(?:app|cluster|project)")

    def __init__(self):
        self._patterns = {
            "kubectl": self._parse_kubectl,
            "helm": self._parse_helm,
            "argocd": self._parse_argocd,
        }

    def parse(self, command: str) -> CommandParams:
        """Parse a command string into structured parameters."""
        command = command.strip()

        # Detect command type
        command_type = self._detect_command_type(command)

        # Use appropriate parser
        if command_type in self._patterns:
            return self._patterns[command_type](command)

        # Default parsing for unknown commands
        return self._parse_generic(command, command_type)

    def _detect_command_type(self, command: str) -> CommandType:
        """Detect the type of command from the command string."""
        parts = command.split()

        if not parts:
            return CommandType.SCRIPT

        first_command = parts[0]

        if first_command == "kubectl":
            return CommandType.KUBECTL
        elif first_command == "helm":
            return CommandType.HELM
        elif first_command == "argocd":
            return CommandType.ARGOCD
        elif first_command.startswith("kubectl"):
            # Handle kubectl with prefixes like kubectl.exe
            return CommandType.KUBECTL

        return CommandType.SCRIPT

    def _parse_kubectl(self, command: str) -> CommandParams:
        """Parse kubectl command."""
        try:
            # Split command while preserving quoted strings
            parts = shlex.split(command)
        except ValueError:
            # Fallback for malformed commands
            parts = command.split()

        params = CommandParams(command_type=CommandType.KUBECTL)

        # Skip 'kubectl'
        idx = 1 if parts and parts[0] == "kubectl" else 0

        # Extract flags and arguments
        i = idx
        while i < len(parts):
            part = parts[i]

            # Handle flags
            if part.startswith("-"):
                flag_name = part.lstrip("-")
                flag_value = None

                # Handle --flag=value format
                if "=" in flag_name:
                    flag_name, flag_value = flag_name.split("=", 1)
                    params.flags[flag_name] = flag_value
                # Handle --flag value format for non-boolean flags
                elif flag_name not in self.KUBECTL_BOOLEAN_FLAGS and i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                    flag_value = parts[i + 1]
                    i += 1
                    params.flags[flag_name] = flag_value
                else:
                    # Boolean flag or flag without value
                    params.flags[flag_name] = "true"

                # Special handling for namespace
                if flag_name in ["n", "namespace"] and flag_value:
                    params.namespace = flag_value
            else:
                # Non-flag arguments
                params.args.append(part)

                # Handle type/name format first (e.g., deployment/api, pod/name)
                if "/" in part and not params.resource_type:
                    type_part, name_part = part.split("/", 1)
                    # Check if the type part matches known resource types
                    if type_part in self.KUBECTL_RESOURCE_TYPES:
                        params.resource_type = self._normalize_resource_type(type_part)
                        params.resource_name = name_part
                    else:
                        # Not a recognized type/name format, treat as regular argument
                        if not params.resource_name:
                            params.resource_name = part
                # Try to identify resource type and action
                elif not params.action and self.KUBECTL_RESOURCE_PATTERN.match(part):
                    params.action = part
                elif not params.resource_type and part in self.KUBECTL_RESOURCE_TYPES:
                    params.resource_type = self._normalize_resource_type(part)
                elif not params.resource_name and part:
                    # For commands like logs, exec, the resource name comes without a type
                    # Also handle cases where resource_name comes after resource_type
                    if not params.resource_type or part != params.resource_type:
                        # Don't set resource_name if it's a known resource type
                        if part not in self.KUBECTL_RESOURCE_TYPES:
                            params.resource_name = part

            i += 1

        # Normalize resource type (e.g., po -> pod)
        if params.resource_type:
            params.resource_type = self._normalize_resource_type(params.resource_type)

        return params

    def _parse_helm(self, command: str) -> CommandParams:
        """Parse helm command."""
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command.split()

        params = CommandParams(command_type=CommandType.HELM)

        # Skip 'helm'
        idx = 1 if parts and parts[0] == "helm" else 0

        # Extract action (install, upgrade, uninstall, etc.)
        if idx < len(parts) and self.HELM_COMMAND_PATTERN.match(parts[idx]):
            params.action = parts[idx]
            idx += 1

        # Extract release name (usually follows action)
        if idx < len(parts) and not parts[idx].startswith("-"):
            params.resource_name = parts[idx]
            idx += 1

        # Extract chart path (usually follows release name)
        if idx < len(parts) and not parts[idx].startswith("-"):
            params.args.append(parts[idx])  # Chart path
            idx += 1

        # Extract flags
        i = idx
        while i < len(parts):
            part = parts[i]
            if part.startswith("-"):
                flag_name = part.lstrip("-")
                flag_value = None

                if "=" in flag_name:
                    flag_name, flag_value = flag_name.split("=", 1)
                elif i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                    flag_value = parts[i + 1]
                    i += 1

                params.flags[flag_name] = flag_value or "true"

                # Special handling for namespace
                if flag_name in ["n", "namespace"]:
                    params.namespace = flag_value
            else:
                params.args.append(part)
            i += 1

        return params

    def _parse_argocd(self, command: str) -> CommandParams:
        """Parse argocd command."""
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command.split()

        params = CommandParams(command_type=CommandType.ARGOCD)

        # Skip 'argocd'
        idx = 1 if parts and parts[0] == "argocd" else 0

        # Extract resource type (app, cluster, project)
        if idx < len(parts) and self.ARGOCD_COMMAND_PATTERN.match(parts[idx]):
            params.resource_type = parts[idx]
            idx += 1

        # Extract action
        if idx < len(parts):
            params.action = parts[idx]
            idx += 1

        # Extract app name (usually follows action)
        if idx < len(parts) and not parts[idx].startswith("-"):
            params.resource_name = parts[idx]
            idx += 1

        # Extract flags
        i = idx
        while i < len(parts):
            part = parts[i]
            if part.startswith("-"):
                flag_name = part.lstrip("-")
                flag_value = None

                if "=" in flag_name:
                    flag_name, flag_value = flag_name.split("=", 1)
                elif i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                    flag_value = parts[i + 1]
                    i += 1

                params.flags[flag_name] = flag_value or "true"
            else:
                params.args.append(part)
            i += 1

        return params

    def _parse_generic(self, command: str, command_type: CommandType) -> CommandParams:
        """Parse generic/unknown command."""
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command.split()

        params = CommandParams(command_type=command_type)

        # Try to identify any flags
        for i, part in enumerate(parts):
            if part.startswith("-"):
                flag_name = part.lstrip("-")
                flag_value = None

                if "=" in flag_name:
                    flag_name, flag_value = flag_name.split("=", 1)
                elif i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                    flag_value = parts[i + 1]

                params.flags[flag_name] = flag_value or "true"
            else:
                params.args.append(part)

        return params

    def _normalize_resource_type(self, resource_type: str) -> str:
        """Normalize kubectl resource type abbreviations and plural forms."""
        # Plural to singular mappings
        plural_to_singular = {
            "pods": "pod",
            "deployments": "deployment",
            "services": "service",
            "statefulsets": "statefulset",
            "daemonsets": "daemonset",
            "namespaces": "namespace",
            "configmaps": "configmap",
            "nodes": "node",
            "endpoints": "endpoint",
            "ingresses": "ingress",
            "persistentvolumes": "persistentvolume",
            "persistentvolumeclaims": "persistentvolumeclaim",
            "storageclasses": "storageclass",
        }
        # Abbreviations to full form mappings
        abbreviations = {
            "po": "pod",
            "deploy": "deployment",
            "svc": "service",
            "sts": "statefulset",
            "ds": "daemonset",
            "ns": "namespace",
            "cm": "configmap",
            "no": "node",
            "ep": "endpoint",
            "ing": "ingress",
            "pv": "persistentvolume",
            "pvc": "persistentvolumeclaim",
            "sc": "storageclass",
        }
        # First check plural forms
        if resource_type in plural_to_singular:
            return plural_to_singular[resource_type]
        # Then check abbreviations
        return abbreviations.get(resource_type, resource_type)


# Singleton instance
_parser: Optional[CommandParser] = None


def get_command_parser() -> CommandParser:
    """Get or create the singleton CommandParser instance."""
    global _parser
    if _parser is None:
        _parser = CommandParser()
    return _parser
