"""
Phoenix v5 — Movement recording and AI-based team assignment endpoints.
"""

import asyncio
import json
import re

from fastapi import APIRouter, Query

import broadcast as _broadcast
import db as _db
from config import ANTHROPIC_API_KEY
from models import MovementBody, TeamAssignmentRequest, TeamAssignmentResult

router = APIRouter()

_CONFIDENCE_THRESHOLD = 0.6

_TEAM_ASSIGN_SYSTEM = (
    "You are a project routing assistant. Given an issue and a list of teams, "
    "select the most appropriate team to handle it based on the issue content and "
    "destination column. "
    "Return ONLY a JSON object with keys: team_id (string), confidence (float 0-1), "
    "reasoning (one sentence string). No markdown, no extra text."
)


@router.post("/movements", status_code=204)
async def record_movement(body: MovementBody) -> None:
    await _db.log_movement(body.repo, body.issue_number, body.from_column, body.to_column, body.actor)
    asyncio.create_task(_broadcast.broadcast({
        "type": "card_moved",
        "repo": body.repo,
        "issueNumber": body.issue_number,
        "fromColumn": body.from_column,
        "toColumn": body.to_column,
        "actor": body.actor,
    }))


@router.get("/movements")
async def get_movements(
    repo: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    return await _db.list_movements(repo, limit)


@router.post("/team-assignment")
async def assign_team(body: TeamAssignmentRequest) -> TeamAssignmentResult:
    """Use AI to assign the most appropriate team when an issue is moved to a new column."""
    if not body.teams:
        return TeamAssignmentResult(
            team_id=None, team_name=None, confidence=0.0,
            needs_manual=True, reasoning="No teams configured for assignment.",
        )

    api_key = body.llm_api_key or ANTHROPIC_API_KEY
    if not api_key:
        return TeamAssignmentResult(
            team_id=None, team_name=None, confidence=0.0,
            needs_manual=True, reasoning="No LLM API key configured.",
        )

    teams_text = "\n".join(
        f"- id={t.id}: {t.name}" + (f" — {t.description}" if t.description else "")
        for t in body.teams
    )
    user_msg = (
        f"Issue #{body.issue_number}: {body.issue_title}\n"
        f"Description: {(body.issue_body or '(none)')[:800]}\n"
        f"Destination column: {body.to_column}\n\n"
        f"Available teams:\n{teams_text}\n\n"
        'Return JSON: {"team_id": "<id>", "confidence": <0.0-1.0>, "reasoning": "<sentence>"}'
    )

    try:
        import anthropic as _anthropic

        model = body.llm_model or "claude-haiku-4-5"
        client = _anthropic.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model=model,
            max_tokens=256,
            system=_TEAM_ASSIGN_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.0,
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        data = json.loads(raw)

        selected_id = str(data.get("team_id", "")).strip()
        confidence = float(data.get("confidence", 0.0))
        reasoning = str(data.get("reasoning", "")).strip()

        matched = next((t for t in body.teams if t.id == selected_id), None)
        if not matched or confidence < _CONFIDENCE_THRESHOLD:
            return TeamAssignmentResult(
                team_id=None, team_name=None, confidence=confidence,
                needs_manual=True,
                reasoning=reasoning or f"Confidence too low ({confidence:.0%}) to auto-assign.",
            )

        return TeamAssignmentResult(
            team_id=matched.id, team_name=matched.name,
            confidence=confidence, needs_manual=False,
            reasoning=reasoning,
        )

    except Exception as exc:
        return TeamAssignmentResult(
            team_id=None, team_name=None, confidence=0.0,
            needs_manual=True, reasoning=f"AI assignment unavailable: {exc}",
        )
