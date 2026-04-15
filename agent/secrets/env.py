"""Environment-variable secrets backend."""

from __future__ import annotations

import os

from .base import SecretsBackend


class EnvBackend(SecretsBackend):
    """Read secrets from the process environment (``os.environ``).

    This is the default backend and requires no external dependencies or
    configuration beyond the environment variables themselves.

    Example::

        backend = EnvBackend()
        token = backend.get("GITHUB_TOKEN")  # reads os.environ["GITHUB_TOKEN"]
    """

    def get(self, key: str) -> str | None:
        value = os.environ.get(key, "")
        return value if value else None
