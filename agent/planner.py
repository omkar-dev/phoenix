"""
Phoenix v5 — PlannerAgent (Phase 7)

Enriches an IssueSpec with a detailed implementation plan before handing
it to ImplementerAgent. Uses Claude Haiku for speed and cost efficiency.

The planner is optional — only active when RunRequest.enable_planner=True.
"""

from __future__ import annotations

import asyncio
import logging

import broadcast as _broadcast
from config import ANTHROPIC_API_KEY, LLM_MODEL
from models import IssueSpec, RunRequest

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are a senior software engineer. Given an issue description with intent and
acceptance criteria, produce a concise implementation plan.

Output a short markdown section (3–8 bullet points) covering:
- Which files/modules to modify or create
- Key algorithms or data-structure decisions
- Any edge cases to watch for
- How to verify the acceptance criteria

Be specific and actionable. No preamble."""


class PlannerAgent:
    """Enriches an IssueSpec with a technical implementation plan."""

    def __init__(self, api_key: str | None = None, run_id: str = "") -> None:
        self._api_key = api_key or ANTHROPIC_API_KEY
        self._run_id = run_id

    async def plan(self, request: RunRequest) -> RunRequest:
        """
        Call LLM to enrich request.spec.technical_notes with a plan.
        Returns an updated RunRequest. On error, returns original unchanged.
        """
        await _broadcast.broadcast({
            "type": "pipeline_stage",
            "runId": self._run_id,
            "stage": "planning",
            "issueNumber": request.issue_number,
            "repo": request.repo_full_name,
        })

        spec = request.spec
        user_message = (
            f"Issue intent: {spec.intent}\n\n"
            f"Acceptance criteria:\n"
            + "\n".join(f"- {c}" for c in spec.acceptance_criteria)
            + (f"\n\nAdditional context:\n{spec.additional_comments}" if spec.additional_comments else "")
            + (f"\n\nExisting technical notes:\n{spec.technical_notes}" if spec.technical_notes else "")
        )

        plan_text = await self._call_llm(user_message)
        if not plan_text:
            return request

        existing = spec.technical_notes or ""
        enriched_notes = (
            f"{existing}\n\n**Implementation Plan (auto-generated):**\n{plan_text}".strip()
        )
        enriched_spec = spec.model_copy(update={"technical_notes": enriched_notes})
        enriched_request = request.model_copy(update={"spec": enriched_spec})

        logger.info("PlannerAgent enriched spec for run %s", self._run_id[:8] if self._run_id else "?")
        return enriched_request

    async def _call_llm(self, user_message: str) -> str:
        """Direct Anthropic API call — returns empty string on error."""
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self._api_key)
            response = await client.messages.create(
                model=_HAIKU_MODEL,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text if response.content else ""
        except Exception as exc:
            logger.warning("PlannerAgent LLM call failed: %s", exc)
            return ""
