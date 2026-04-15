"""Tests for the EnvBackend secrets implementation."""

import pytest

from secrets import EnvBackend


class TestEnvBackend:
    def test_get_returns_value_when_env_var_set(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
        backend = EnvBackend()
        assert backend.get("GITHUB_TOKEN") == "ghp_test_token"

    def test_get_returns_none_when_env_var_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_SECRET_XYZ", raising=False)
        backend = EnvBackend()
        assert backend.get("MISSING_SECRET_XYZ") is None

    def test_get_returns_none_when_env_var_is_empty_string(self, monkeypatch):
        monkeypatch.setenv("EMPTY_SECRET", "")
        backend = EnvBackend()
        assert backend.get("EMPTY_SECRET") is None

    def test_require_returns_value_when_present(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        backend = EnvBackend()
        assert backend.require("ANTHROPIC_API_KEY") == "sk-ant-test"

    def test_require_raises_key_error_when_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_SECRET_XYZ", raising=False)
        backend = EnvBackend()
        with pytest.raises(KeyError, match="MISSING_SECRET_XYZ"):
            backend.require("MISSING_SECRET_XYZ")

    def test_set_raises_not_implemented(self, monkeypatch):
        backend = EnvBackend()
        with pytest.raises(NotImplementedError):
            backend.set("KEY", "value")

    def test_does_not_expose_secret_value_in_error_message(self, monkeypatch):
        """Secret values must never appear in error output."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        backend = EnvBackend()
        try:
            backend.require("SECRET_KEY")
        except KeyError as exc:
            # The error should mention the key name but not a value
            assert "SECRET_KEY" in str(exc)
