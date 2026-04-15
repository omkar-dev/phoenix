"""Tests for the secrets factory, registry, and convenience helpers."""

import pytest

from secrets import (
    DopplerBackend,
    EnvBackend,
    KVBackend,
    SecretsBackend,
    VaultBackend,
    create_backend,
    get_secret,
    get_secrets_store,
    register_backend,
    require_secret,
    reset_secrets_store,
)


@pytest.fixture(autouse=True)
def reset_store():
    """Ensure the process-wide singleton is reset between tests."""
    reset_secrets_store()
    yield
    reset_secrets_store()


class TestCreateBackend:
    def test_creates_env_backend(self):
        assert isinstance(create_backend("env"), EnvBackend)

    def test_creates_kv_backend(self):
        assert isinstance(create_backend("kv"), KVBackend)

    def test_creates_doppler_backend(self):
        assert isinstance(create_backend("doppler"), DopplerBackend)

    def test_creates_vault_backend(self):
        assert isinstance(create_backend("vault"), VaultBackend)

    def test_raises_value_error_for_unknown_backend(self):
        with pytest.raises(ValueError, match="unknown_backend"):
            create_backend("unknown_backend")

    def test_error_lists_registered_backends(self):
        with pytest.raises(ValueError, match="env"):
            create_backend("not_a_backend")


class TestRegisterBackend:
    def test_register_and_create_custom_backend(self):
        class _CustomBackend(SecretsBackend):
            def get(self, key: str) -> str | None:
                return f"custom:{key}"

        register_backend("custom_test", lambda **_: _CustomBackend())
        backend = create_backend("custom_test")
        assert isinstance(backend, _CustomBackend)
        assert backend.get("ANY") == "custom:ANY"

    def test_registered_backend_usable_as_default_store(self, monkeypatch):
        class _InjectBackend(SecretsBackend):
            def get(self, key: str) -> str | None:
                return "injected"

        register_backend("inject_test", lambda **_: _InjectBackend())
        monkeypatch.setenv("SECRETS_BACKEND", "inject_test")
        store = get_secrets_store()
        assert store.get("ANYTHING") == "injected"


class TestGetSecretsStore:
    def test_returns_env_backend_by_default(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        store = get_secrets_store()
        assert isinstance(store, EnvBackend)

    def test_returns_kv_backend_when_configured(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "kv")
        store = get_secrets_store()
        assert isinstance(store, KVBackend)

    def test_returns_same_instance_on_repeated_calls(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        assert get_secrets_store() is get_secrets_store()

    def test_reset_forces_reinitialisation(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        first = get_secrets_store()
        reset_secrets_store()
        second = get_secrets_store()
        assert first is not second

    def test_reset_with_explicit_backend_replaces_store(self):
        injected = KVBackend({"K": "v"})
        reset_secrets_store(injected)
        assert get_secrets_store() is injected


class TestConvenienceHelpers:
    def test_get_secret_returns_value(self, monkeypatch):
        store = KVBackend({"GITHUB_TOKEN": "ghp_test"})
        reset_secrets_store(store)
        assert get_secret("GITHUB_TOKEN") == "ghp_test"

    def test_get_secret_returns_none_when_missing(self):
        reset_secrets_store(KVBackend())
        assert get_secret("NONEXISTENT") is None

    def test_require_secret_returns_value(self):
        reset_secrets_store(KVBackend({"API_KEY": "secret"}))
        assert require_secret("API_KEY") == "secret"

    def test_require_secret_raises_key_error_when_missing(self):
        reset_secrets_store(KVBackend())
        with pytest.raises(KeyError):
            require_secret("MISSING_KEY")

    def test_github_and_claude_keys_retrievable_without_knowing_backend(self):
        """Acceptance criterion: callers must not need to know which backend is in use."""
        store = KVBackend({
            "GITHUB_TOKEN": "ghp_integration_test",
            "ANTHROPIC_API_KEY": "sk-ant-integration",
        })
        reset_secrets_store(store)

        # Callers just call get_secret — they don't import or instantiate backends
        assert get_secret("GITHUB_TOKEN") == "ghp_integration_test"
        assert get_secret("ANTHROPIC_API_KEY") == "sk-ant-integration"
