"""Abstract base class for secrets backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SecretsBackend(ABC):
    """Common interface for all secrets storage backends.

    Callers interact exclusively with this interface, which means the
    underlying backend can be swapped without touching application code.
    """

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Return the secret for *key*, or ``None`` if it does not exist.

        Implementations must never log or surface the secret value in
        exception messages or debug output.
        """

    def require(self, key: str) -> str:
        """Return the secret for *key*, raising ``KeyError`` if absent or empty."""
        value = self.get(key)
        if not value:
            raise KeyError(
                f"Required secret '{key}' was not found in {self.__class__.__name__}"
            )
        return value

    def set(self, key: str, value: str) -> None:  # noqa: A003
        """Store *value* under *key*.

        Not all backends support writes.  Raises ``NotImplementedError`` by
        default; override in backends that support mutation.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support writing secrets"
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"{self.__class__.__name__}()"
