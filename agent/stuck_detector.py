"""
Phoenix v5 — Stuck Detection + Slack Notifier (Phase 6)

Polls in-flight agent runs for inactivity. When an agent is idle longer
than STUCK_THRESHOLD_MINUTES, sends a Slack notification (if configured)
and marks the run as notified so the alert fires only once per run.

Also detects CI-checking rows that have been stuck in that state too long.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import db as _db
from config import SLACK_WEBHOOK_URL, STUCK_THRESHOLD_MINUTES
from registry import _runs

logger = logging.getLogger(__name__)

STUCK_POLL_INTERVAL = 120  # seconds between scans


# ── Slack notifier ─────────────────────────────────────────────────────────────

class SlackNotifier:
    """Posts plain-text messages to a Slack incoming webhook URL."""

    async def send(self, text: str) -> None:
        """No-op when SLACK_WEBHOOK_URL is empty."""
        if not SLACK_WEBHOOK_URL:
            return
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    SLACK_WEBHOOK_URL,
                    json={"text": text},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as exc:
            logger.warning("Slack notification failed: %s", exc)


# ── Stuck detector ─────────────────────────────────────────────────────────────

class StuckDetector:
    """Background task that scans for stuck agent runs and CI states."""

    def __init__(self) -> None:
        self._stopped = False
        self._notifier = SlackNotifier()

    def stop(self) -> None:
        self._stopped = True

    async def run(self) -> None:
        logger.info("Stuck detector started (threshold=%dmin)", STUCK_THRESHOLD_MINUTES)
        while not self._stopped:
            try:
                await self._scan()
            except Exception as exc:
                logger.warning("Stuck detector scan error: %s", exc)
            for _ in range(STUCK_POLL_INTERVAL):
                if self._stopped:
                    break
                await asyncio.sleep(1)

    async def _scan(self) -> None:
        now = datetime.now(UTC)

        # 1. Check in-flight agent runs for idleness
        for run_id, state in list(_runs.items()):
            if state.task.done():
                continue  # run finished — not stuck

            if await _db.has_been_notified(run_id):
                continue  # already alerted

            # Find the last logged event for this run
            try:
                logs = await _db.get_run_logs(run_id)
            except Exception:
                continue

            if not logs:
                continue

            last_event_str = logs[-1].get("logged_at", "")
            if not last_event_str:
                continue

            try:
                last_event = datetime.fromisoformat(last_event_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            idle_minutes = (now - last_event).total_seconds() / 60
            if idle_minutes < STUCK_THRESHOLD_MINUTES:
                continue

            # Agent is stuck — notify
            repo = state.agent.request.repo_full_name
            issue = state.agent.request.issue_number
            msg = (
                f":warning: *Phoenix agent stuck* — "
                f"run `{run_id[:8]}` on `{repo}#{issue}` "
                f"has been idle for {int(idle_minutes)} min with no output."
            )
            await self._notifier.send(msg)
            await _db.mark_notified(run_id, "idle")
            logger.info("Stuck alert sent for run %s (idle %.0fmin)", run_id[:8], idle_minutes)

        # 2. Check for CI rows stuck in ci_checking
        try:
            ci_rows = await _db.list_pollable_lifecycles({"ci_checking"})
        except Exception:
            return

        for row in ci_rows:
            run_id = row["run_id"]
            if await _db.has_been_notified(f"ci:{run_id}"):
                continue

            updated_str = row.get("updated_at", "")
            if not updated_str:
                continue

            try:
                updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            idle_minutes = (now - updated).total_seconds() / 60
            if idle_minutes < STUCK_THRESHOLD_MINUTES * 2:
                continue  # give CI more grace time (2×)

            repo = row["repo"]
            issue = row["issue_number"]
            pr_url = row.get("pr_url", "")
            msg = (
                f":hourglass: *Phoenix CI stuck* — "
                f"`{repo}#{issue}` has been in `ci_checking` "
                f"for {int(idle_minutes)} min. PR: {pr_url or 'unknown'}"
            )
            await self._notifier.send(msg)
            await _db.mark_notified(f"ci:{run_id}", "ci_stuck")
