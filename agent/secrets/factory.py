"""Backend registry and factory.

The registry maps a short name (``"env"``, ``"doppler"``, etc.) to a
callable that constructs the backend.  Third-party code can extend the
registry via :func:`register_backend` without modifying this module —
the plugin/provider pattern that keeps the abstraction layer open for
extension and closed for modification.
"""

from __future__ import annotations

import os
from typing import Callable

from .base import SecretsBackend
from .doppler import DopplerBackend
from .env import EnvBackend
from .kv import KVBackend
from .vault import VaultBackend

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Callable[..., SecretsBackend]] = {
    "env": lambda **_: EnvBackend(),
    "doppler": lambda **kw: DopplerBackend(**kw),
    "vault": lambda **kw: VaultBackend(**kw),
    "kv": lambda **kw: KVBackend(**kw),
}


def register_backend(name: str, factory: Callable[..., SecretsBackend]) -> None:
    """Register a custom backend factory under *name*.

    This is the extension point for adding new backends without modifying
    this module.  Call it once at application startup, before the first
    :func:`get_secrets_store` call.

    Example::

        from agent.secrets import register_backend

        class MyBackend(SecretsBackend):
            def get(self, key):
                ...

        register_backend("mybackend", lambda **kw: MyBackend(**kw))

    Then set ``SECRETS_BACKEND=mybackend`` in the environment to activate it.
    """
    _REGISTRY[name] = factory


def create_backend(name: str, **kwargs: object) -> SecretsBackend:
    """Instantiate a backend by *name*, passing *kwargs* to its factory.

    Raises :class:`ValueError` for unknown names, with a hint listing the
    registered options.
    """
    factory = _REGISTRY.get(name)
    if factory is None:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown secrets backend '{name}'. "
            f"Registered backends: {known}"
        )
    return factory(**kwargs)


# ---------------------------------------------------------------------------
# Process-wide default backend (lazy singleton)
# ---------------------------------------------------------------------------

_default_backend: SecretsBackend | None = None


def get_secrets_store() -> SecretsBackend:
    """Return (and lazily initialise) the process-wide default secrets backend.

    The backend is selected by the ``SECRETS_BACKEND`` environment variable
    (default: ``"env"``).  Override it before the first call to change the
    backend for the whole process::

        import os
        os.environ["SECRETS_BACKEND"] = "doppler"
        from agent.secrets import get_secrets_store
        store = get_secrets_store()  # DopplerBackend
    """
    global _default_backend
    if _default_backend is None:
        backend_name = os.environ.get("SECRETS_BACKEND", "env")
        _default_backend = create_backend(backend_name)
    return _default_backend


def reset_secrets_store(backend: SecretsBackend | None = None) -> None:
    """Replace or clear the process-wide default backend.

    Primarily intended for tests — call with no argument to force
    re-initialisation on the next :func:`get_secrets_store` call::

        from agent.secrets.factory import reset_secrets_store
        reset_secrets_store()  # forces re-init from SECRETS_BACKEND env var
        reset_secrets_store(KVBackend({"KEY": "val"}))  # inject a test backend
    """
    global _default_backend
    _default_backend = backend
