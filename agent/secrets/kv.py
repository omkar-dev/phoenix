"""In-memory key-value secrets backend with optional JSON-file persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .base import SecretsBackend


class KVBackend(SecretsBackend):
    """Simple in-memory key-value store for secrets.

    Useful for:
    - Unit tests (inject secrets without touching the environment)
    - Local development overrides
    - Composing with other backends in custom pipelines

    An optional JSON file can be loaded at construction time so that secrets
    survive process restarts without being baked into environment variables.

    Configuration env vars:
        SECRETS_KV_FILE  – path to a JSON file containing a flat
                           ``{"KEY": "value", ...}`` mapping.  If the file
                           does not exist the backend starts empty (no error).

    Example::

        # From a dict
        store = KVBackend({"GITHUB_TOKEN": "ghp_xxx", "ANTHROPIC_API_KEY": "sk-xxx"})

        # From a JSON file
        store = KVBackend(file="/run/secrets/app.json")

        # Runtime writes (useful for testing)
        store.set("NEW_KEY", "new-value")
        store.delete("OLD_KEY")
    """

    def __init__(
        self,
        initial: dict[str, str] | None = None,
        *,
        file: str | Path | None = None,
    ) -> None:
        self._store: dict[str, str] = dict(initial or {})
        kv_file = file or os.environ.get("SECRETS_KV_FILE")
        if kv_file:
            self._load_file(Path(kv_file))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_file(self, path: Path) -> None:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError(
                    f"SECRETS_KV_FILE '{path}' must contain a JSON object, "
                    f"got {type(data).__name__}"
                )
            self._store.update({str(k): str(v) for k, v in data.items()})
        except FileNotFoundError:
            pass  # missing file is not fatal at startup

    # ------------------------------------------------------------------
    # SecretsBackend interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        value = self._store.get(key, "")
        return value if value else None

    def set(self, key: str, value: str) -> None:  # noqa: A003
        self._store[key] = value

    def delete(self, key: str) -> None:
        """Remove *key* from the store.  No-op if *key* does not exist."""
        self._store.pop(key, None)
