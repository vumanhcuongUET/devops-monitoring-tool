"""Phase 16 P1-4: git refs from API input must be validated before they
reach git as argv elements — option-like tokens after "origin" are argument
injection ("git pull origin --upload-pack=<cmd>")."""
import pytest

from app.configmgmt.gitops import validate_ref


class TestValidateRef:
    def test_plain_names_pass(self):
        assert validate_ref("main") == "main"
        assert validate_ref("develop") == "develop"
        assert validate_ref("feature/foo-bar") == "feature/foo-bar"
        assert validate_ref("config/meinvoice/20260902-120000") == "config/meinvoice/20260902-120000"
        assert validate_ref("v1.2.3") == "v1.2.3"

    @pytest.mark.parametrize("bad", [
        "--upload-pack=touch /tmp/pwned",
        "-oProxyCommand=evil",
        "--force",
        "-b",
        "main..secret",
        "feature/",
        "",
        "has space",
        "semi;colon",
        "back`tick",
        "dollar$var",
    ])
    def test_option_like_and_hostile_names_rejected(self, bad):
        with pytest.raises(ValueError):
            validate_ref(bad)

    def test_leading_dot_ok_but_leading_dash_not(self):
        assert validate_ref(".github-config") == ".github-config"
        with pytest.raises(ValueError):
            validate_ref("-leading-dash")
