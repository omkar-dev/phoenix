"""
Phoenix v5 — PR Lifecycle State Machine

Tracks the lifecycle of PRs opened by ImplementerAgent runs through states:
  working → pr_open → ci_checking → ci_passed → approved → merged
                                  ↘ ci_failed → ci_checking (retry loop)
                                    changes_requested → approved

State transitions are validated against VALID_TRANSITIONS before being
persisted and broadcast to connected SSE clients.
"""

from __future__ import annotations

import db as _db
import broadcast as _broadcast

VALID_TRANSITIONS: dict[str, set[str]] = {
    "working":           {"pr_open"},
    "pr_open":           {"ci_checking", "merged"},
    "ci_checking":       {"ci_failed", "ci_passed"},
    "ci_failed":         {"ci_checking"},
    "ci_passed":         {"changes_requested", "approved", "merged"},
    "changes_requested": {"ci_checking", "approved"},
    "approved":          {"merged"},
}

# Terminal states — no further transitions possible
TERMINAL_STATES = {"merged"}


class LifecycleStateMachine:
    """Manages state transitions for pr_lifecycle rows."""

    @staticmethod
    async def transition(
        run_id: str,
        new_state: str,
        **extra_fields,
    ) -> bool:
        """
        Attempt a state transition for the given run.

        Returns True if the transition was applied, False if:
        - No lifecycle row exists for run_id
        - The transition is not valid from the current state
        - The current state is already a terminal state
        """
        row = await _db.get_lifecycle_by_run(run_id)
        if not row:
            return False

        current = row["state"]
        if current in TERMINAL_STATES:
            return False

        allowed = VALID_TRANSITIONS.get(current, set())
        if new_state not in allowed:
            return False

        await _db.upsert_lifecycle(
            run_id=run_id,
            repo=row["repo"],
            issue_number=row["issue_number"],
            state=new_state,
            **extra_fields,
        )

        await _broadcast.broadcast({
            "type": "lifecycle_updated",
            "runId": run_id,
            "issueNumber": row["issue_number"],
            "repo": row["repo"],
            "prUrl": row.get("pr_url"),
            "prNumber": row.get("pr_number"),
            "branch": row.get("branch_name"),
            "state": new_state,
        })

        return True

    @staticmethod
    async def init_working(
        run_id: str,
        repo: str,
        issue_number: int,
    ) -> None:
        """Create the initial 'working' lifecycle row when a run starts."""
        await _db.upsert_lifecycle(
            run_id=run_id,
            repo=repo,
            issue_number=issue_number,
            state="working",
        )
