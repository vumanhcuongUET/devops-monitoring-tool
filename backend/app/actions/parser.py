"""Command parser for kubectl, helm, and argocd commands."""

import re
import shlex

from app.models.actions import CommandParams, CommandType

# Phase 12 S5: the only binaries the executor may run. Parser and executor
# share this one source of truth (validator.py applies the command-policy
# layer on top; this is the hard argv[0] floor).
ALLOWED_BINARIES = {"kubectl", "helm", "argocd"}


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

    # helm global flags that consume a value — needed to skip a flag-first
    # invocation ("helm -n prod uninstall rel") without misreading the flag's
    # value as the action positional.
    HELM_GLOBAL_FLAGS_WITH_VALUES = {
        "n", "namespace", "kube-context", "kubeconfig", "kube-apiserver",
        "registry-config", "repository-cache", "repository-config",
        "f", "values", "output", "o", "version",
    }

    # argocd patterns
    ARGOCD_COMMAND_PATTERN = re.compile(r"(?:app|cluster|project)")

    # argocd global flags (see HELM_GLOBAL_FLAGS_WITH_VALUES).
    ARGOCD_GLOBAL_FLAGS_WITH_VALUES = {
        "server", "auth-token", "grpc-web-root-path", "config",
        "port-forward-namespace", "logformat", "loglevel", "headers",
    }
    ARGOCD_BOOLEAN_FLAGS = {"grpc-web", "insecure", "plaintext", "core", "port-forward"}

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

    @staticmethod
    def _split(command: str) -> list:
        """Split command while preserving quoted strings, fallback on malformed input."""
        try:
            return shlex.split(command)
        except ValueError:
            return command.split()

    def _parse_flags(self, parts: list, i: int, params: CommandParams,
                     boolean_flags: set | None = None) -> None:
        """Shared flag/argument loop: fills params.flags/args from parts[i:].

        Handles --flag=value, --flag value, boolean flags, and --namespace.
        """
        while i < len(parts):
            part = parts[i]
            if part.startswith("-"):
                flag_name = part.lstrip("-")
                flag_value = None

                if "=" in flag_name:
                    flag_name, flag_value = flag_name.split("=", 1)
                elif flag_name not in (boolean_flags or set()) and i + 1 < len(parts) \
                        and not parts[i + 1].startswith("-"):
                    flag_value = parts[i + 1]
                    i += 1

                params.flags[flag_name] = flag_value or "true"

                # Special handling for namespace
                if flag_name in ("n", "namespace") and flag_value:
                    params.namespace = flag_value
            else:
                params.args.append(part)
            i += 1

    def _parse_kubectl(self, command: str) -> CommandParams:
        """Parse kubectl command."""
        parts = self._split(command)
        params = CommandParams(command_type=CommandType.KUBECTL)

        # Skip 'kubectl'
        idx = 1 if parts and parts[0] == "kubectl" else 0

        self._parse_flags(parts, idx, params, self.KUBECTL_BOOLEAN_FLAGS)

        # Classify positional arguments (order preserved)
        for part in params.args:
            # Handle type/name format first (e.g., deployment/api, pod/name)
            if "/" in part and not params.resource_type:
                type_part, name_part = part.split("/", 1)
                # Check if the type part matches known resource types
                if type_part in self.KUBECTL_RESOURCE_TYPES:
                    params.resource_type = self._normalize_resource_type(type_part)
                    params.resource_name = name_part
                elif not params.resource_name:
                    # Not a recognized type/name format, treat as regular argument
                    params.resource_name = part
            # Try to identify resource type and action
            elif not params.action and self.KUBECTL_RESOURCE_PATTERN.match(part):
                params.action = part
            elif not params.resource_type and part in self.KUBECTL_RESOURCE_TYPES:
                params.resource_type = self._normalize_resource_type(part)
            elif not params.resource_name and part:
                # For commands like logs, exec, the resource name comes without a type
                if part not in self.KUBECTL_RESOURCE_TYPES:
                    params.resource_name = part

        # Normalize resource type (e.g., po -> pod)
        if params.resource_type:
            params.resource_type = self._normalize_resource_type(params.resource_type)

        return params

    def _skip_global_flags(self, parts: list, idx: int,
                           with_values: set, boolean_flags: set | None = None) -> int:
        """Return the index of the first non-flag token at or after idx.

        Value-taking flags skip their value ("helm -n prod uninstall" lands
        on "uninstall", not "prod"); unknown or boolean flags skip only
        themselves. A "--flag=value" form never consumes an extra token.
        """
        i = idx
        while i < len(parts) and parts[i].startswith("-"):
            name = parts[i].lstrip("-").split("=", 1)[0]
            if ("=" not in parts[i] and name in with_values
                    and i + 1 < len(parts) and not parts[i + 1].startswith("-")):
                i += 2
            elif boolean_flags and name in boolean_flags:
                i += 1
            else:
                # Unknown flag: conservatively skip only itself; its value
                # (if any) will surface and stop the scan — callers then
                # fail to match an action rather than misread one.
                i += 1
        return i

    def _parse_helm(self, command: str) -> CommandParams:
        """Parse helm command."""
        parts = self._split(command)
        params = CommandParams(command_type=CommandType.HELM)

        # Skip 'helm'
        flag_start = 1 if parts and parts[0] == "helm" else 0

        # Global flags may precede the action ("helm -n prod uninstall rel")
        idx = self._skip_global_flags(
            parts, flag_start, self.HELM_GLOBAL_FLAGS_WITH_VALUES
        )

        # Extract action (install, upgrade, uninstall, etc.)
        if idx < len(parts) and self.HELM_COMMAND_PATTERN.match(parts[idx]):
            params.action = parts[idx]
            idx += 1
        else:
            # Nothing parsed past the flags — keep the pre-flag position so
            # _parse_flags still sees the whole invocation.
            idx = flag_start

        # Extract release name (usually follows action)
        if idx < len(parts) and not parts[idx].startswith("-"):
            params.resource_name = parts[idx]
            idx += 1

        # Extract chart path (usually follows release name)
        if idx < len(parts) and not parts[idx].startswith("-"):
            params.args.append(parts[idx])  # Chart path
            idx += 1

        self._parse_flags(parts, flag_start, params)

        return params

    def _parse_argocd(self, command: str) -> CommandParams:
        """Parse argocd command."""
        parts = self._split(command)
        params = CommandParams(command_type=CommandType.ARGOCD)

        # Skip 'argocd'
        flag_start = 1 if parts and parts[0] == "argocd" else 0

        # Global flags may precede the resource type ("argocd --grpc-web app get")
        idx = self._skip_global_flags(
            parts, flag_start,
            self.ARGOCD_GLOBAL_FLAGS_WITH_VALUES, self.ARGOCD_BOOLEAN_FLAGS,
        )

        # Extract resource type (app, cluster, project)
        if idx < len(parts) and self.ARGOCD_COMMAND_PATTERN.match(parts[idx]):
            params.resource_type = parts[idx]
            idx += 1
        else:
            idx = flag_start

        # Extract action
        if idx < len(parts) and not parts[idx].startswith("-"):
            params.action = parts[idx]
            idx += 1
        else:
            idx = flag_start

        # Extract app name (usually follows action)
        if idx < len(parts) and not parts[idx].startswith("-"):
            params.resource_name = parts[idx]
            idx += 1

        self._parse_flags(parts, flag_start, params)

        return params

    def _parse_generic(self, command: str, command_type: CommandType) -> CommandParams:
        """Parse generic/unknown command."""
        params = CommandParams(command_type=command_type)
        self._parse_flags(self._split(command), 0, params)
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
_parser: CommandParser | None = None


def get_command_parser() -> CommandParser:
    """Get or create the singleton CommandParser instance."""
    global _parser
    if _parser is None:
        _parser = CommandParser()
    return _parser
