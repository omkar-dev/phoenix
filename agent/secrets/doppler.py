"""Doppler secrets management backend."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import SecretsBackend

_DOPPLER_API_BASE = "https://api.doppler.com/v3/configs/config/secret"


class DopplerBackend(SecretsBackend):
    """Fetch secrets from the `Doppler <https://www.doppler.com/>`_ service.

    Doppler is a cloud-native secrets manager.  This backend calls the
    Doppler REST API using only Python stdlib (``urllib``), so no additional
    packages are required.

    Secrets are cached in-process for the lifetime of the backend instance to
    minimise network round-trips.

    Configuration env vars:
        DOPPLER_TOKEN    – Doppler service token (required).
        DOPPLER_PROJECT  – Project name (required unless passed directly).
        DOPPLER_CONFIG   – Config / environment name, e.g. ``prd`` or ``dev``
                           (required unless passed directly).

    Example::

        backend = DopplerBackend()          # reads env vars
        backend = DopplerBackend(
            token="dp.st.xxx",
            project="ponenix",
            config="prd",
        )
        token = backend.get("GITHUB_TOKEN")
    """

    def __init__(
        self,
        token: str | None = None,
        project: str | None = None,
        config: str | None = None,
    ) -> None:
        self._token = token or os.environ.get("DOPPLER_TOKEN", "")
        self._project = project or os.environ.get("DOPPLER_PROJECT", "")
        self._config = config or os.environ.get("DOPPLER_CONFIG", "")
        self._cache: dict[str, str | None] = {}

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

    def _build_url(self, key: str) -> str:
        params: list[str] = [f"name={key}"]
        if self._project:
            params.append(f"project={self._project}")
        if self._config:
            params.append(f"config={self._config}")
        return f"{_DOPPLER_API_BASE}?{'&'.join(params)}"

    def _fetch(self, key: str) -> str | None:
        if not self._token:
            raise RuntimeError(
                "DopplerBackend requires DOPPLER_TOKEN to be configured"
            )

        req = urllib.request.Request(
            self._build_url(key),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body: dict[str, Any] = json.loads(resp.read())
                # Doppler response shape:
                # {"secret": {"name": "KEY", "value": {"raw": "...", "computed": "..."}}}
                raw: str = body.get("secret", {}).get("value", {}).get("raw", "")
                return raw if raw else None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            # Do not include the key value in the message — secrets must not
            # appear in error output even as key names in some organisations.
            raise RuntimeError(
                f"Doppler API returned HTTP {exc.code} "
                f"(project='{self._project}', config='{self._config}')"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not reach Doppler API: {exc.reason}"
            ) from exc
