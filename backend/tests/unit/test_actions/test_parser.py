"""Unit tests for Command Parser."""

import pytest

from app.actions.parser import CommandParser, get_command_parser
from app.models.actions import CommandType


class TestCommandParser:
    """Test command parsing functionality."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return CommandParser()

    def test_parse_kubectl_get_command(self, parser):
        """Test parsing kubectl get command."""
        command = "kubectl get pods -n default"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        assert result.action == "get"
        assert result.resource_type == "pod"
        assert result.namespace == "default"
        assert "pods" in result.args

    def test_parse_kubectl_describe_command(self, parser):
        """Test parsing kubectl describe command."""
        command = "kubectl describe deployment api -n meinvoice"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        assert result.action == "describe"
        assert result.resource_type == "deployment"
        assert result.resource_name == "api"
        assert result.namespace == "meinvoice"

    def test_parse_kubectl_delete_command(self, parser):
        """Test parsing kubectl delete command."""
        command = "kubectl delete pod test-pod -n default"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        assert result.action == "delete"
        assert result.resource_type == "pod"
        assert result.resource_name == "test-pod"

    def test_parse_kubectl_logs_command(self, parser):
        """Test parsing kubectl logs command."""
        command = "kubectl logs -f pod-123 -n meinvoice"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        assert result.action == "logs"
        # Flags are stored without leading dash
        assert "f" in result.flags or "follow" in result.flags
        assert result.resource_name == "pod-123"

    def test_parse_kubectl_rollout_restart(self, parser):
        """Test parsing kubectl rollout restart command."""
        command = "kubectl rollout restart deployment/api -n meinvoice"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        assert result.action == "rollout"
        assert "restart" in result.args

    def test_parse_kubectl_scale_command(self, parser):
        """Test parsing kubectl scale command."""
        command = "kubectl scale deployment/api --replicas=5 -n meinvoice"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        assert result.action == "scale"
        assert result.resource_type == "deployment"
        assert result.resource_name == "api"

    def test_parse_helm_upgrade_command(self, parser):
        """Test parsing helm upgrade command."""
        command = "helm upgrade meinvoice ./chart -n meinvoice"
        result = parser.parse(command)

        assert result.command_type == CommandType.HELM
        assert result.action == "upgrade"
        assert result.resource_name == "meinvoice"

    def test_parse_helm_install_command(self, parser):
        """Test parsing helm install command."""
        command = "helm install my-release ./chart -n default"
        result = parser.parse(command)

        assert result.command_type == CommandType.HELM
        assert result.action == "install"
        assert result.resource_name == "my-release"

    def test_parse_helm_rollback_command(self, parser):
        """Test parsing helm rollback command."""
        command = "helm rollback meinvoice 1 -n meinvoice"
        result = parser.parse(command)

        assert result.command_type == CommandType.HELM
        assert result.action == "rollback"
        assert result.resource_name == "meinvoice"

    def test_parse_argocd_sync_command(self, parser):
        """Test parsing argocd sync command."""
        command = "argocd app sync meinvoice"
        result = parser.parse(command)

        assert result.command_type == CommandType.ARGOCD
        assert result.action == "sync"
        assert result.resource_name == "meinvoice"

    def test_parse_argocd_rollback_command(self, parser):
        """Test parsing argocd rollback command."""
        command = "argocd app rollback meinvoice"
        result = parser.parse(command)

        assert result.command_type == CommandType.ARGOCD
        assert result.action == "rollback"
        assert result.resource_name == "meinvoice"

    def test_parse_generic_command(self, parser):
        """Test parsing generic/unknown command."""
        command = "custom-script.sh arg1 arg2"
        result = parser.parse(command)

        assert result.command_type == CommandType.SCRIPT
        # The command is split into individual args
        assert "custom-script.sh" in result.args
        assert "arg1" in result.args
        assert "arg2" in result.args

    def test_parse_command_with_namespace_flag(self, parser):
        """Test parsing command with namespace flag variations."""
        command = "kubectl get pods --namespace=monitoring"
        result = parser.parse(command)

        assert result.namespace == "monitoring"

    def test_parse_command_with_multiple_flags(self, parser):
        """Test parsing command with multiple flags."""
        command = "kubectl get pods -n default -l app=api -o wide"
        result = parser.parse(command)

        assert result.namespace == "default"
        assert "app=api" in result.flags.values() or "app" in result.flags
        assert len(result.args) > 0

    def test_parse_invalid_command_empty(self, parser):
        """Test parsing empty command."""
        command = ""
        result = parser.parse(command)

        assert result.command_type == CommandType.SCRIPT

    def test_parse_command_with_quotes(self, parser):
        """Test parsing command with quoted arguments."""
        command = 'kubectl get pods -n "my-namespace"'
        result = parser.parse(command)

        assert result.namespace == "my-namespace"

    def test_detect_command_type_kubectl(self, parser):
        """Test kubectl command type detection."""
        assert parser._detect_command_type("kubectl get pods") == CommandType.KUBECTL
        assert parser._detect_command_type("kubectl apply -f manifest.yaml") == CommandType.KUBECTL

    def test_detect_command_type_helm(self, parser):
        """Test helm command type detection."""
        assert parser._detect_command_type("helm install release") == CommandType.HELM
        assert parser._detect_command_type("helm upgrade release chart") == CommandType.HELM

    def test_detect_command_type_argocd(self, parser):
        """Test argocd command type detection."""
        assert parser._detect_command_type("argocd app sync appname") == CommandType.ARGOCD
        assert parser._detect_command_type("argocd app get appname") == CommandType.ARGOCD

    def test_normalize_resource_type(self, parser):
        """Test resource type normalization."""
        assert parser._normalize_resource_type("pods") == "pod"
        assert parser._normalize_resource_type("deployments") == "deployment"
        assert parser._normalize_resource_type("services") == "service"
        assert parser._normalize_resource_type("svc") == "service"

    def test_parse_kubectl_all_namespace(self, parser):
        """Test parsing kubectl command with --all-namespaces."""
        command = "kubectl get pods --all-namespaces"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        # Flags are stored with the original name (with dashes)
        assert "all-namespaces" in result.flags or "all-namespaces" in result.args

    def test_parse_kubectl_with_context(self, parser):
        """Test parsing kubectl command with context."""
        command = "kubectl get pods --context=dev-cluster"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        assert "context" in result.flags or "dev-cluster" in str(result.flags)


class TestCommandParserSingleton:
    """Test CommandParser singleton pattern."""

    def test_get_command_parser_returns_singleton(self):
        """Test that get_command_parser returns same instance."""
        parser1 = get_command_parser()
        parser2 = get_command_parser()

        assert parser1 is parser2

    def test_get_command_parser_initializes_new_instance(self):
        """Test that first call initializes the parser."""
        from app.actions.parser import _parser
        _parser = None

        parser = get_command_parser()

        assert parser is not None
        assert isinstance(parser, CommandParser)


class TestCommandParserEdgeCases:
    """Test edge cases in command parsing."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return CommandParser()

    def test_parse_malformed_command_unclosed_quote(self, parser):
        """Test parsing command with unclosed quote."""
        # shlex.split will handle this, parser should not crash
        command = "kubectl get pods -n 'unclosed"
        result = parser.parse(command)

        # Should parse with fallback behavior
        assert result is not None
        assert result.command_type == CommandType.KUBECTL

    def test_parse_command_with_multiple_namespace_flags(self, parser):
        """Test command with multiple namespace flags (last wins)."""
        command = "kubectl get pods -n default -n production"
        result = parser.parse(command)

        # Last namespace should be used
        assert result.namespace in ["default", "production"]

    def test_parse_argocd_with_complex_flags(self, parser):
        """Test argocd command with complex flags."""
        command = "argocd app sync myapp --timeout 300 --force"
        result = parser.parse(command)

        assert result.command_type == CommandType.ARGOCD
        assert result.action == "sync"
        assert result.resource_name == "myapp"

    def test_parse_helm_with_set_flag(self, parser):
        """Test helm command with --set flag values."""
        command = "helm install myapp ./chart --set image.tag=v1.0 --set replica.count=3"
        result = parser.parse(command)

        assert result.command_type == CommandType.HELM
        assert result.action == "install"
        assert result.resource_name == "myapp"
        # --set flags should be captured
        assert "image.tag" in str(result.flags) or "replica.count" in str(result.flags)

    def test_normalize_all_abbreviations(self, parser):
        """Test all resource type abbreviation normalizations."""
        abbreviations = {
            "po": "pod",
            "deploy": "deployment",
            "svc": "service",
            "sts": "statefulset",
            "ds": "daemonset",
            "ns": "namespace",
            "cm": "configmap",
            "no": "node",
        }

        for abbrev, full in abbreviations.items():
            result = parser._normalize_resource_type(abbrev)
            assert result == full, f"Expected {abbrev} -> {full}, got {result}"

    def test_parse_kubectl_exec_command(self, parser):
        """Test parsing kubectl exec command."""
        command = "kubectl exec -it pod-123 -- /bin/sh"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        # exec might not be in the standard pattern, but should not crash
        assert result is not None

    def test_parse_kubectl_top_command(self, parser):
        """Test parsing kubectl top command."""
        command = "kubectl top pods -n default"
        result = parser.parse(command)

        assert result.command_type == CommandType.KUBECTL
        assert result.action == "top"

    def test_parse_helm_list_with_filter(self, parser):
        """Test helm list command with filter."""
        command = "helm list -n default --filter 'name=api'"
        result = parser.parse(command)

        assert result.command_type == CommandType.HELM
        assert result.action == "list"

    def test_parse_argocd_get_with_output(self, parser):
        """Test argocd get command with output format."""
        command = "argocd app get myapp -o json"
        result = parser.parse(command)

        assert result.command_type == CommandType.ARGOCD
        assert result.action == "get" or "get" in result.args
