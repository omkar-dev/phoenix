"""
Phoenix v5 — GitHub Webhook Receiver

Receives GitHub webhook events at POST /webhooks/github and dispatches them
to the lifecycle state machine. Validates HMAC-SHA256 signatures when
GITHUB_WEBHOOK_SECRET is configured.

Handled events:
  pull_request        — opened/reopened → pr_open; closed+merged → merged
  pull_request_review — approved → approved; changes_requested → changes_requested
  check_suite         — requested → ci_checking; completed → ci_passed/ci_failed
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

import db as _db
from config import GITHUB_WEBHOOK_SECRET
from lifecycle import LifecycleStateMachine

router = APIRouter()


# ── HMAC Validation ────────────────────────────────────────────────────────────

async def _validate_hmac(request: Request) -> bytes:
    """
    Validate GitHub HMAC-SHA256 webhook signature.
    Returns raw body bytes (must be read before JSON parsing).
    Raises 403 if signature is invalid.
    If GITHUB_WEBHOOK_SECRET is empty, skips validation (dev mode).
    """
    body = await request.body()
    if not GITHUB_WEBHOOK_SECRET:
        return body  # dev mode — accept all

    sig_header = request.headers.get("X-Hub-Signature-256", "")
    if not sig_header.startswith("sha256="):
        raise HTTPException(status_code=403, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, sig_header):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    return body


# ── Webhook Endpoint ───────────────────────────────────────────────────────────

@router.post("/webhooks/github", status_code=204)
async def github_webhook(request: Request) -> Response:
    """Receive and dispatch a GitHub webhook event."""
    body = await _validate_hmac(request)
    event_type = request.headers.get("X-GitHub-Event", "")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Dispatch asynchronously so we return 204 immediately
    asyncio.create_task(_dispatch_webhook(event_type, payload))
    return Response(status_code=204)


# ── Dispatcher ─────────────────────────────────────────────────────────────────

async def _dispatch_webhook(event_type: str, payload: dict) -> None:
    """Route a GitHub webhook event to the appropriate lifecycle handler."""
    try:
        if event_type == "pull_request":
            await _handle_pull_request(payload)
        elif event_type == "pull_request_review":
            await _handle_pull_request_review(payload)
        elif event_type == "check_suite":
            await _handle_check_suite(payload)
        # Other events (push, issue_comment, etc.) ignored for now
    except Exception:
        pass  # Webhook handlers must never propagate exceptions


async def _lookup_row_by_pr(payload: dict) -> dict | None:
    """Extract repo + branch from a payload and look up the lifecycle row."""
    repo = payload.get("repository", {}).get("full_name", "")
    pr = payload.get("pull_request", {})
    branch = pr.get("head", {}).get("ref", "")
    if not repo or not branch:
        return None
    return await _db.get_lifecycle_by_branch(repo, branch)


# ── pull_request ───────────────────────────────────────────────────────────────

async def _handle_pull_request(payload: dict) -> None:
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {}).get("full_name", "")
    branch = pr.get("head", {}).get("ref", "")
    pr_number = pr.get("number")

    if not repo or not branch:
        return

    row = await _db.get_lifecycle_by_branch(repo, branch)
    if not row:
        return

    if action in ("opened", "reopened"):
        await LifecycleStateMachine.transition(
            row["run_id"], "pr_open",
            pr_number=pr_number,
            pr_url=pr.get("html_url"),
        )
    elif action == "closed" and pr.get("merged"):
        await LifecycleStateMachine.transition(row["run_id"], "merged")


# ── pull_request_review ────────────────────────────────────────────────────────

async def _handle_pull_request_review(payload: dict) -> None:
    action = payload.get("action", "")
    if action != "submitted":
        return

    review = payload.get("review", {})
    review_state = review.get("state", "").lower()

    state_map = {
        "approved": "approved",
        "changes_requested": "changes_requested",
    }
    new_state = state_map.get(review_state)
    if not new_state:
        return

    row = await _lookup_row_by_pr(payload)
    if not row:
        return

    transitioned = await LifecycleStateMachine.transition(
        row["run_id"], new_state,
        review_decision=review_state,
    )

    if transitioned and new_state == "approved":
        # Fire approved reaction (imported lazily to avoid circular imports)
        try:
            from reactions import dispatch_reaction
            asyncio.create_task(dispatch_reaction("approved", row, payload))
        except ImportError:
            pass
    elif transitioned and new_state == "changes_requested":
        try:
            from reactions import dispatch_reaction
            asyncio.create_task(dispatch_reaction("changes_requested", row, payload))
        except ImportError:
            pass


# ── check_suite ────────────────────────────────────────────────────────────────

async def _handle_check_suite(payload: dict) -> None:
    action = payload.get("action", "")
    suite = payload.get("check_suite", {})
    repo = payload.get("repository", {}).get("full_name", "")
    head_branch = suite.get("head_branch", "")

    if not repo or not head_branch:
        return

    row = await _db.get_lifecycle_by_branch(repo, head_branch)
    if not row:
        return

    if action == "requested":
        await LifecycleStateMachine.transition(row["run_id"], "ci_checking")

    elif action == "completed":
        conclusion = suite.get("conclusion", "")

        if conclusion == "success":
            await LifecycleStateMachine.transition(
                row["run_id"], "ci_passed",
                ci_conclusion="success",
            )

        elif conclusion in ("failure", "timed_out", "cancelled", "action_required"):
            transitioned = await LifecycleStateMachine.transition(
                row["run_id"], "ci_failed",
                ci_conclusion=conclusion,
            )
            if transitioned:
                try:
                    from reactions import dispatch_reaction
                    asyncio.create_task(dispatch_reaction("ci_failed", row, payload))
                except ImportError:
                    pass
