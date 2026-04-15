"""Tests for the VaultBackend secrets implementation."""

import json
from unittest.mock import MagicMock, call, patch

import pytest

from secrets import VaultBackend


def _mock_urlopen(body: dict):
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# Vault KV v1 data payload
_KV1_BODY = {"data": {"GITHUB_TOKEN": "ghp_vault_v1", "ANTHROPIC_API_KEY": "sk-vault"}}

# Vault KV v2 data payload
_KV2_BODY = {"data": {"data": {"GITHUB_TOKEN": "ghp_vault_v2"}, "metadata": {}}}

# Mount metadata response indicating KV v2
_MOUNT_V2 = {"options": {"version": "2"}, "type": "kv"}
_MOUNT_V1 = {"options": {"version": "1"}, "type": "kv"}


class TestVaultBackendKV1:
    def _backend(self, **kw):
        defaults = dict(addr="http://vault:8200", token="hvs.test", mount="secret", path="app")
        return VaultBackend(**{**defaults, **kw})

    def test_get_returns_value_kv1(self):
        backend = self._backend()
        responses = [_mock_urlopen(_MOUNT_V1), _mock_urlopen(_KV1_BODY)]
        with patch("urllib.request.urlopen", side_effect=responses):
            assert backend.get("GITHUB_TOKEN") == "ghp_vault_v1"

    def test_get_returns_none_for_missing_key_kv1(self):
        backend = self._backend()
        responses = [_mock_urlopen(_MOUNT_V1), _mock_urlopen(_KV1_BODY)]
        with patch("urllib.request.urlopen", side_effect=responses):
            assert backend.get("NONEXISTENT") is None

    def test_version_cached_after_first_call(self):
        backend = self._backend()
        responses = [_mock_urlopen(_MOUNT_V1), _mock_urlopen(_KV1_BODY), _mock_urlopen(_KV1_BODY)]
        with patch("urllib.request.urlopen", side_effect=responses) as mock_open:
            backend.get("GITHUB_TOKEN")
            backend.get("ANTHROPIC_API_KEY")
            # First call: mount probe + secret fetch (2 calls)
            # Second call: secret fetch only (no re-probe), but result is cached
            assert mock_open.call_count == 3  # mount probe + 2 secret fetches

    def test_get_caches_secret_on_second_call(self):
        backend = self._backend()
        responses = [_mock_urlopen(_MOUNT_V1), _mock_urlopen(_KV1_BODY)]
        with patch("urllib.request.urlopen", side_effect=responses) as mock_open:
            backend.get("GITHUB_TOKEN")
            backend.get("GITHUB_TOKEN")  # cached — no additional HTTP call
            assert mock_open.call_count == 2  # mount probe + one secret fetch


class TestVaultBackendKV2:
    def _backend(self, **kw):
        defaults = dict(addr="http://vault:8200", token="hvs.test", mount="secret", path="app")
        return VaultBackend(**{**defaults, **kw})

    def test_get_returns_value_kv2(self):
        backend = self._backend()
        responses = [_mock_urlopen(_MOUNT_V2), _mock_urlopen(_KV2_BODY)]
        with patch("urllib.request.urlopen", side_effect=responses):
            assert backend.get("GITHUB_TOKEN") == "ghp_vault_v2"

    def test_secret_url_uses_data_prefix_for_kv2(self):
        backend = self._backend()
        backend._kv_version = 2  # skip mount probe
        url_called = []
        original = __import__("urllib.request", fromlist=["urlopen"]).urlopen

        def capturing_urlopen(req, **kw):
            url_called.append(req.full_url)
            return _mock_urlopen(_KV2_BODY)

        with patch("urllib.request.urlopen", side_effect=capturing_urlopen):
            backend.get("GITHUB_TOKEN")

        assert any("/data/" in url for url in url_called)


class TestVaultBackendErrors:
    def _backend(self, **kw):
        defaults = dict(addr="http://vault:8200", token="hvs.test", mount="secret", path="app")
        return VaultBackend(**{**defaults, **kw})

    def test_get_raises_runtime_error_when_token_missing(self):
        backend = VaultBackend(addr="http://vault:8200", token="", mount="secret", path="app")
        with pytest.raises(RuntimeError, match="VAULT_TOKEN"):
            backend.get("KEY")

    def test_get_returns_none_on_404(self):
        import urllib.error
        backend = self._backend()
        backend._kv_version = 1
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url=None, code=404, msg="Not Found", hdrs=None, fp=None
        )):
            assert backend.get("MISSING") is None

    def test_get_raises_runtime_error_on_403(self):
        import urllib.error
        backend = self._backend()
        backend._kv_version = 1
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url=None, code=403, msg="Forbidden", hdrs=None, fp=None
        )):
            with pytest.raises(RuntimeError, match="403"):
                backend.get("KEY")

    def test_reads_config_from_env(self, monkeypatch):
        monkeypatch.setenv("VAULT_ADDR", "http://my-vault:8200")
        monkeypatch.setenv("VAULT_TOKEN", "hvs.env")
        monkeypatch.setenv("VAULT_MOUNT", "myapp")
        monkeypatch.setenv("VAULT_PATH", "production")
        backend = VaultBackend()
        assert backend._addr == "http://my-vault:8200"
        assert backend._token == "hvs.env"
        assert backend._mount == "myapp"
        assert backend._path == "production"

    def test_mount_probe_failure_falls_back_to_kv1(self):
        backend = self._backend()
        # Mount probe raises, so version should fall back to 1
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            version = backend._detect_kv_version()
        assert version == 1

    def test_url_error_raises_runtime_error(self):
        import urllib.error
        backend = self._backend()
        backend._kv_version = 1
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with pytest.raises(RuntimeError, match="vault"):
                backend.get("KEY")
