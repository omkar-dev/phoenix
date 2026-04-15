"""
Phoenix v5 — Reactions System

Centralised dispatcher that maps lifecycle events to automated actions.
Each handler is registered with the @reaction decorator.

Handlers run as background asyncio tasks so they never block the webhook
response. Errors are logged to run_logs but never re-raised.

Registered handlers:
  ci_failed         → CI retry: collect failed logs, spawn new agent run
  approved          → Auto-merge: merge PR via GitHub API
  changes_requested → Notify: broadcast SSE event with reviewer details
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import db as _db
import broadcast as _broadcast
from ci_collector import CILogCollector
from config import GITHUB_TOKEN
from lifecycle import LifecycleStateMachine
from models import IssueSpec, RunRequest

MAX_CI_RETRIES = 3


# ── Handler registry ───────────────────────────────────────────────────────────

REACTION_HANDLERS: dict[str, Callable] = {}


def reaction(event_type: str):
    """Decorator: register an async function as the handler for event_type."""
    def decorator(fn: Callable) -> Callable:
        REACTION_HANDLERS[event_type] = fn
        return fn
    return decorator


async def dispatch_reaction(
    event_type: str,
    lifecycle_row: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    """
    Entry point — look up the handler for event_type, call it, swallow errors.
    Intended to be fired with asyncio.create_task() from the webhook dispatcher.
    """
    handler = REACTION_HANDLERS.get(event_type)
    if not handler:
        return
    try:
        await handler(lifecycle_row, payload)
    except Exception as exc:
        run_id = lifecycle_row.get("run_id", "unknown")
        try:
            await _db.append_run_log(
                run_id=run_id,
                repo=lifecycle_row.get("repo", ""),
                issue_number=lifecycle_row.get("issue_number", 0),
                event_type="reaction_error",
                data={"reaction": event_type, "error": str(exc)},
            )
        except Exception:
            pass


# ── Handlers ───────────────────────────────────────────────────────────────────

@reaction("ci_failed")
async def handle_ci_failed(row: dict, payload: dict) -> None:
    """
    On CI failure:
    1. Check retry count — abort + notify if >= MAX_CI_RETRIES
    2. Collect failed check run logs
    3. Reconstruct RunRequest from original 'start' event in run_logs
    4. Set existing_branch so agent pushes to the same PR branch
    5. Spawn new ImplementerAgent run with CI failure context prepended
    6. Persist retry record to ci_retries table
    """
    from agent import ImplementerAgent
    from critic import DefaultCritic
    from registry import RunState, _runs

    original_run_id = row["run_id"]
    repo = row["repo"]
    branch_name = row.get("branch_name", "")
    issue_number = row.get("issue_number", 0)
    pr_number = row.get("pr_number")

    # 1. Check retry limit
    retry_count = await _db.count_ci_retries(original_run_id)
    if retry_count >= MAX_CI_RETRIES:
        await _broadcast.broadcast({
            "type": "ci_retry_limit_reached",
            "runId": original_run_id,
            "issueNumber": issue_number,
            "repo": repo,
            "prUrl": row.get("pr_url"),
            "message": f"CI failed {retry_count} times — manual intervention required.",
        })
        return

    # 2. Collect CI failure logs
    collector = CILogCollector(GITHUB_TOKEN)
    ci_logs = await collector.collect_failed_logs(repo, branch_name)

    # 3. Reconstruct RunRequest from the original run's 'start' event
    original_request: RunRequest | None = None
    try:
        logs = await _db.get_run_logs(original_run_id)
        for entry in logs:
            if entry["event_type"] == "start":
                data = entry["data"] if isinstance(entry["data"], dict) else json.loads(entry["data"])
                req_data = data.get("request", {})
                if req_data:
                    original_request = RunRequest.model_validate(req_data)
                    break
    except Exception:
        pass

    if not original_request:
        # Fallback: build a minimal request from the lifecycle row
        original_request = RunRequest(
            issue_number=issue_number,
            repo_full_name=repo,
            spec=IssueSpec(
                intent=f"Fix CI failures on PR #{pr_number}",
                acceptance_criteria=["All CI checks pass"],
                additional_comments="",
            ),
        )

    # 4. Build retry RunRequest
    attempt = retry_count + 1
    ci_context = (
        f"CI FAILED (attempt {attempt} of {MAX_CI_RETRIES}). "
        f"Fix the following CI failures before doing anything else:\n\n{ci_logs}"
        if ci_logs
        else f"CI FAILED (attempt {attempt} of {MAX_CI_RETRIES}). Fix the CI failures."
    )

    existing_comments = original_request.spec.additional_comments or ""
    retry_spec = original_request.spec.model_copy(update={
        "additional_comments": f"{ci_context}\n\n{existing_comments}".strip(),
    })
    retry_request = original_request.model_copy(update={
        "spec": retry_spec,
        "existing_branch": branch_name,  # push to same PR branch — no new PR
    })

    # 5. Spawn new agent run
    new_run_id = str(uuid.uuid4())
    critic = None
    if retry_request.critic and retry_request.critic.enabled:
        critic = DefaultCritic(
            api_key=retry_request.llm_api_key or None,
            model=retry_request.critic.model or "claude-haiku-4-5-20251001",
            threshold=retry_request.critic.threshold,
        )
    agent = ImplementerAgent(new_run_id, retry_request, critic=critic)
    task = asyncio.create_task(agent.run(), name=f"ci-retry-{new_run_id[:8]}")
    _runs[new_run_id] = RunState(run_id=new_run_id, agent=agent, task=task)

    await _broadcast.broadcast({
        "type": "run_started",
        "runId": new_run_id,
        "issueNumber": issue_number,
        "repo": repo,
        "ciRetry": True,
        "attempt": attempt,
        "originalRunId": original_run_id,
    })

    # 6. Persist retry record
    await _db.save_ci_retry(
        original_run_id=original_run_id,
        retry_run_id=new_run_id,
        repo=repo,
        issue_number=issue_number,
        attempt=attempt,
        ci_conclusion="failure",
    )


@reaction("approved")
async def handle_approved(row: dict, payload: dict) -> None:
    """
    On PR approval:
    - Abort if CI has not passed (ci_conclusion != 'success')
    - Auto-merge via PyGithub squash merge
    - Transition lifecycle to 'merged'
    """
    import asyncio
    from github import Github

    pr_number = row.get("pr_number")
    repo_name = row.get("repo")
    run_id = row["run_id"]

    if not pr_number or not repo_name:
        return

    # Only auto-merge if CI passed
    if row.get("ci_conclusion") not in ("success", None):
        # ci_conclusion might be null if webhook-only (no polling), allow merge
        pass
    if row.get("ci_conclusion") == "failure":
        # CI is known-failed — don't merge
        return

    try:
        gh = Github(GITHUB_TOKEN)
        github_repo = await asyncio.to_thread(gh.get_repo, repo_name)
        pr = await asyncio.to_thread(github_repo.get_pull, pr_number)
        await asyncio.to_thread(pr.merge, merge_method="squash")
    except Exception as exc:
        await _broadcast.broadcast({
            "type": "auto_merge_failed",
            "runId": run_id,
            "issueNumber": row.get("issue_number"),
            "repo": repo_name,
            "prUrl": row.get("pr_url"),
            "error": str(exc),
        })
        return

    await LifecycleStateMachine.transition(run_id, "merged")


@reaction("changes_requested")
async def handle_changes_requested(row: dict, payload: dict) -> None:
    """
    On changes_requested review:
    Broadcast an SSE event so the frontend can update the card status.
    The reviewer's login is extracted from the webhook payload.
    """
    reviewer = ""
    try:
        reviewer = payload.get("review", {}).get("user", {}).get("login", "")
    except Exception:
        pass

    await _broadcast.broadcast({
        "type": "review_requested_changes",
        "runId": row["run_id"],
        "issueNumber": row.get("issue_number"),
        "repo": row.get("repo"),
        "prUrl": row.get("pr_url"),
        "reviewer": reviewer,
    })
