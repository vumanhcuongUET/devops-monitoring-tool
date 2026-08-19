"""Unit tests for Command Parser."""

import pytest

from app.actions.parser import CommandParser, get_command_parser
from app.models.actions import CommandType, CommandParams


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
        assert "-f" in result.flags or "follow" in result.flags
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
        assert command in result.args or command in result.flags

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
        assert "all-namespaces" in result.args or "all_namespaces" in result.flags

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
        from app.actions.parser import _command_parser
        _command_parser = None

        parser = get_command_parser()

        assert parser is not None
        assert isinstance(parser, CommandParser)
