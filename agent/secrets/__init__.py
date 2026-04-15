"""Secrets storage abstraction layer for Phoenix v5.

This package provides a unified interface for reading (and optionally writing)
sensitive values such as API keys, tokens, and passwords.  Application code
calls :func:`get_secret` or :func:`require_secret` without knowing which
backend is in use; the backend is selected at startup via the
``SECRETS_BACKEND`` environment variable.

Supported backends
------------------
``env`` (default)
    Reads from ``os.environ``.  Requires no additional configuration.

``doppler``
    Fetches secrets from the `Doppler <https://www.doppler.com/>`_ service.
    Needs ``DOPPLER_TOKEN``, ``DOPPLER_PROJECT``, and ``DOPPLER_CONFIG``.

``vault``
    Reads from a `HashiCorp Vault <https://www.vaultproject.io/>`_ KV store.
    Needs ``VAULT_ADDR`` and ``VAULT_TOKEN`` (plus optional ``VAULT_MOUNT``
    and ``VAULT_PATH``).

``kv``
    In-memory key-value store.  Useful for tests and local overrides.
    Optionally loads from a JSON file specified by ``SECRETS_KV_FILE``.

Adding a new backend
--------------------
Register a factory callable with :func:`register_backend` before the first
call to :func:`get_secrets_store`::

    from agent.secrets import register_backend, SecretsBackend

    class MyBackend(SecretsBackend):
        def get(self, key: str) -> str | None:
            ...

    register_backend("mybackend", lambda **kw: MyBackend(**kw))

Then set ``SECRETS_BACKEND=mybackend`` in the environment.

Quick-start examples
--------------------
::

    from agent.secrets import get_secret, require_secret

    # Returns None if the secret is absent:
    token = get_secret("GITHUB_TOKEN")

    # Raises KeyError if the secret is absent:
    api_key = require_secret("ANTHROPIC_API_KEY")

    # Use a specific backend directly (e.g. in tests):
    from agent.secrets import KVBackend
    store = KVBackend({"GITHUB_TOKEN": "ghp_test"})
    store.get("GITHUB_TOKEN")  # "ghp_test"
"""

from .base import SecretsBackend
from .doppler import DopplerBackend
from .env import EnvBackend
from .factory import (
    create_backend,
    get_secrets_store,
    register_backend,
    reset_secrets_store,
)
from .kv import KVBackend
from .vault import VaultBackend

__all__ = [
    # Core interface
    "SecretsBackend",
    # Concrete backends
    "EnvBackend",
    "DopplerBackend",
    "VaultBackend",
    "KVBackend",
    # Factory / registry
    "create_backend",
    "register_backend",
    "get_secrets_store",
    "reset_secrets_store",
    # Convenience helpers
    "get_secret",
    "require_secret",
]


def get_secret(key: str) -> str | None:
    """Return *key* from the default secrets backend, or ``None`` if absent."""
    return get_secrets_store().get(key)


def require_secret(key: str) -> str:
    """Return *key* from the default secrets backend.

    Raises :class:`KeyError` if the secret is absent or empty.
    """
    return get_secrets_store().require(key)
