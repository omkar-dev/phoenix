"""HashiCorp Vault secrets backend."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import SecretsBackend


class VaultBackend(SecretsBackend):
    """Fetch secrets from a `HashiCorp Vault <https://www.vaultproject.io/>`_ KV store.

    Supports both **KV v1** and **KV v2** engines.  The engine version is
    auto-detected from the Vault mount metadata on the first request and
    cached for the lifetime of the backend.

    All values are read from a single Vault path (``{mount}/{path}``); *key*
    refers to a field inside that path's data map, not a separate path.  This
    mirrors the common practice of grouping application secrets under a single
    path per environment.

    Secrets are cached in-process for the lifetime of the backend instance.

    Configuration env vars:
        VAULT_ADDR    – Vault server URL (default: ``http://127.0.0.1:8200``).
        VAULT_TOKEN   – Vault token with read access (required).
        VAULT_MOUNT   – KV mount path (default: ``secret``).
        VAULT_PATH    – Secret path inside the mount (default: ``ponenix``).

    Example::

        backend = VaultBackend()          # reads env vars
        backend = VaultBackend(
            addr="https://vault.internal:8200",
            token="hvs.xxx",
            mount="secret",
            path="ponenix/prd",
        )
        token = backend.get("GITHUB_TOKEN")
    """

    def __init__(
        self,
        addr: str | None = None,
        token: str | None = None,
        mount: str | None = None,
        path: str | None = None,
    ) -> None:
        self._addr = (
            addr or os.environ.get("VAULT_ADDR") or "http://127.0.0.1:8200"
        ).rstrip("/")
        self._token = token or os.environ.get("VAULT_TOKEN", "")
        self._mount = mount or os.environ.get("VAULT_MOUNT") or "secret"
        self._path = path or os.environ.get("VAULT_PATH") or "ponenix"
        self._cache: dict[str, str | None] = {}
        self._kv_version: int | None = None

    # ------------------------------------------------------------------
    # SecretsBackend interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        value = self._fetch(key)
        self._cache[key] = value
        return value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_kv_version(self) -> int:
        """Return the KV engine version (1 or 2) for the configured mount."""
        if self._kv_version is not None:
            return self._kv_version

        url = f"{self._addr}/v1/sys/mounts/{self._mount}"
        req = urllib.request.Request(
            url,
            headers={
                "X-Vault-Token": self._token,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body: dict[str, Any] = json.loads(resp.read())
                version_str: str = body.get("options", {}).get("version", "1")
                self._kv_version = int(version_str)
        except Exception:
            # Any error falls back to v1 so the backend degrades gracefully.
            self._kv_version = 1

        return self._kv_version

    def _secret_url(self) -> str:
        version = self._detect_kv_version()
        if version == 2:
            return f"{self._addr}/v1/{self._mount}/data/{self._path}"
        return f"{self._addr}/v1/{self._mount}/{self._path}"

    def _fetch(self, key: str) -> str | None:
        if not self._token:
            raise RuntimeError(
                "VaultBackend requires VAULT_TOKEN to be configured"
            )

        req = urllib.request.Request(
            self._secret_url(),
            headers={
                "X-Vault-Token": self._token,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body: dict[str, Any] = json.loads(resp.read())
                if self._kv_version == 2:
                    data: dict[str, str] = body.get("data", {}).get("data", {})
                else:
                    data = body.get("data", {})
                value: str = data.get(key, "")
                return value if value else None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise RuntimeError(
                f"Vault returned HTTP {exc.code} for "
                f"mount='{self._mount}' path='{self._path}'"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not reach Vault at '{self._addr}': {exc.reason}"
            ) from exc
