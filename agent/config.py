"""
Phoenix v5 — centralised configuration

All settings are read from environment variables (and optionally a .env file
in the agent/ directory). Missing required variables raise a clear error at
startup rather than failing silently later.

Secrets backend
---------------
By default secrets (GITHUB_TOKEN, ANTHROPIC_API_KEY) are read from the
process environment via the built-in ``env`` backend.  Set ``SECRETS_BACKEND``
to ``doppler``, ``vault``, or ``kv`` to switch to an alternative backend
without changing any other code.  See ``agent/secrets/`` for details.
"""

import asyncio
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# NOTE: `secrets` here refers to the local agent/secrets/ package, not the
# Python stdlib `secrets` module.  agent/ is always on sys.path when this
# module is loaded (it is the package root), so the local package takes
# precedence over the stdlib one.
from secrets import get_secrets_store  # local agent/secrets/ package


class _Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently ignore unknown env vars
    )

    github_token: str = Field("", description="GitHub PAT with repo scope (optional — can be set in the UI Settings → GitHub)")
    anthropic_api_key: str = Field("", description="Anthropic API key (optional if set per-agent in the UI)")
    llm_model: str = Field(
        "anthropic/claude-sonnet-4-6",
        description="Default LiteLLM model string",
    )
    cors_origins: str = Field(
        "",
        description="Comma-separated allowed CORS origins. Empty = all localhost ports in dev.",
    )
    pnx_repos_dir: Path = Field(
        default_factory=lambda: Path.home() / ".pnx" / "repos",
        description="Directory where base git clones are stored",
    )
    secrets_backend: str = Field(
        "env",
        description="Secrets backend to use: env | doppler | vault | kv",
    )
    github_webhook_secret: str = Field(
        "",
        description="HMAC-SHA256 secret for validating GitHub webhook payloads. Empty = accept all (dev mode).",
    )
    slack_webhook_url: str = Field(
        "",
        description="Slack incoming webhook URL for notifications. Empty = notifications disabled.",
    )
    stuck_threshold_minutes: int = Field(
        30,
        description="Minutes of agent inactivity before it is considered stuck.",
    )
    lifecycle_poll_enabled: bool = Field(
        True,
        description="Enable the CI polling fallback (polls GitHub every LIFECYCLE_POLL_INTERVAL seconds). Disable if you rely solely on webhooks.",
    )
    lifecycle_poll_interval: int = Field(
        90,
        description="Seconds between CI status polls for the polling fallback. Min 30.",
    )


# Validate and load at import time — bad config fails loudly at startup.
_settings = _Settings()

# Initialise the secrets store using the configured backend.
# When SECRETS_BACKEND=env (the default) this simply reads os.environ and
# the behaviour is identical to the previous implementation.
_secrets = get_secrets_store()

# Re-export as module-level names so existing imports don't change.
# Pydantic / .env values take precedence; the secrets backend fills in any
# gaps (e.g. when running with SECRETS_BACKEND=doppler and no local .env).
GITHUB_TOKEN: str = _settings.github_token or _secrets.get("GITHUB_TOKEN") or ""
ANTHROPIC_API_KEY: str = _settings.anthropic_api_key or _secrets.get("ANTHROPIC_API_KEY") or ""
LLM_MODEL: str = _settings.llm_model
CORS_ORIGINS: str = _settings.cors_origins
BASE_REPOS_DIR: Path = _settings.pnx_repos_dir
GITHUB_WEBHOOK_SECRET: str = _settings.github_webhook_secret or _secrets.get("GITHUB_WEBHOOK_SECRET") or ""
SLACK_WEBHOOK_URL: str = _settings.slack_webhook_url or _secrets.get("SLACK_WEBHOOK_URL") or ""
STUCK_THRESHOLD_MINUTES: int = _settings.stuck_threshold_minutes
LIFECYCLE_POLL_ENABLED: bool = _settings.lifecycle_poll_enabled
LIFECYCLE_POLL_INTERVAL: int = max(30, _settings.lifecycle_poll_interval)

# Per-repo lock: serialises fetch + worktree-add so concurrent runs for the
# same repo don't race on the shared base clone.
_repo_locks: dict[str, asyncio.Lock] = {}
