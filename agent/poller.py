"""
Phoenix v5 — CI Polling Fallback (Phase 4)

Background asyncio task that polls GitHub for CI status on PRs that are
in 'pr_open' or 'ci_checking' state. Used when the repo is not configured
to send webhooks (e.g. local dev, private repos without ngrok).

Enabled by LIFECYCLE_POLL_ENABLED=true (default).
Poll interval: LIFECYCLE_POLL_INTERVAL seconds (default 90, min 30).
"""

from __future__ import annotations

import asyncio
import logging

from github import Github

import db as _db
from config import GITHUB_TOKEN, LIFECYCLE_POLL_ENABLED, LIFECYCLE_POLL_INTERVAL
from lifecycle import LifecycleStateMachine
from reactions import dispatch_reaction

logger = logging.getLogger(__name__)

POLLABLE_STATES = {"pr_open", "ci_checking"}


class LifecyclePoller:
    """Polls pr_lifecycle rows and transitions state based on GitHub check runs."""

    def __init__(self) -> None:
        self._stopped = False
        self._gh = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None

    def stop(self) -> None:
        self._stopped = True

    async def run(self) -> None:
        if not LIFECYCLE_POLL_ENABLED:
            logger.info("Lifecycle poller disabled (LIFECYCLE_POLL_ENABLED=false)")
            return
        if not self._gh:
            logger.warning("Lifecycle poller: no GITHUB_TOKEN — polling disabled")
            return

        logger.info(
            "Lifecycle poller started (interval=%ds)", LIFECYCLE_POLL_INTERVAL
        )
        while not self._stopped:
            try:
                await self._poll_all()
            except Exception as exc:
                logger.warning("Lifecycle poller error: %s", exc)
            # Sleep in small increments so stop() is responsive
            for _ in range(LIFECYCLE_POLL_INTERVAL):
                if self._stopped:
                    break
                await asyncio.sleep(1)

    async def _poll_all(self) -> None:
        rows = await _db.list_pollable_lifecycles(POLLABLE_STATES)
        if not rows:
            return

        tasks = [self._poll_one(row) for row in rows]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for row, result in zip(rows, results):
            if isinstance(result, Exception):
                logger.debug(
                    "Poll error for run %s: %s", row["run_id"][:8], result
                )

    async def _poll_one(self, row: dict) -> None:
        repo_name = row["repo"]
        branch_name = row.get("branch_name")
        run_id = row["run_id"]

        if not branch_name:
            return

        try:
            github_repo = await asyncio.to_thread(self._gh.get_repo, repo_name)
            branch = await asyncio.to_thread(github_repo.get_branch, branch_name)
            sha = branch.commit.sha

            check_runs = await asyncio.to_thread(
                lambda: list(github_repo.get_commit(sha).get_check_runs())
            )
        except Exception:
            return

        if not check_runs:
            return

        # Categorise check runs
        completed = [cr for cr in check_runs if cr.status == "completed"]
        if len(completed) < len(check_runs):
            # Still running — transition to ci_checking if not already
            if row["state"] == "pr_open":
                await LifecycleStateMachine.transition(run_id, "ci_checking")
            return

        # All completed — determine overall conclusion
        failed = [
            cr for cr in completed
            if cr.conclusion in ("failure", "timed_out", "cancelled", "action_required")
        ]

        if failed:
            transitioned = await LifecycleStateMachine.transition(
                run_id, "ci_failed", ci_conclusion="failure"
            )
            if transitioned:
                asyncio.create_task(
                    dispatch_reaction("ci_failed", row, {})
                )
        else:
            transitioned = await LifecycleStateMachine.transition(
                run_id, "ci_passed", ci_conclusion="success"
            )
            if transitioned:
                asyncio.create_task(
                    dispatch_reaction("ci_passed", row, {})
                )
