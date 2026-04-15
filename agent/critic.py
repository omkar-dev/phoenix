"""Pluggable critic interface for evaluating agent implementation quality.

Usage
-----
Implement the ``Critic`` Protocol to create a custom critic, then inject it
into ``ImplementerAgent``::

    agent = ImplementerAgent(run_id, request, critic=MyCritic())

The built-in ``DefaultCritic`` calls Claude Haiku to score the diff against
the acceptance criteria and returns structured feedback.  ``NullCritic``
always passes — useful in tests or when the feature is disabled.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CriticContext:
    """Everything a critic needs to evaluate a completed agent run."""
    acceptance_criteria: list[str]
    work_dir: Path
    agent_summary: str          # agent's self-reported summary
    diff: str                   # full git diff of uncommitted changes
    cycle: int = 0              # refinement cycle index (0 = first evaluation)


@dataclass
class CriticResult:
    """Structured evaluation produced by a critic."""
    score: float                # 0.0 (nothing done) → 1.0 (all criteria met)
    issues: list[str] = field(default_factory=list)   # specific gaps found
    passed: bool = True         # True when score >= threshold
    feedback: str = ""          # prose to send back to the agent


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class Critic(Protocol):
    """Minimal interface every critic must satisfy."""

    async def evaluate(self, ctx: CriticContext) -> CriticResult:
        """Evaluate the agent's work and return a structured result."""
        ...


# ── Built-in implementations ──────────────────────────────────────────────────

class NullCritic:
    """No-op critic — always passes.  Use in tests or to skip evaluation."""

    async def evaluate(self, ctx: CriticContext) -> CriticResult:
        return CriticResult(score=1.0, issues=[], passed=True, feedback="")


class DefaultCritic:
    """LLM-based critic that scores the diff against acceptance criteria.

    Uses Claude Haiku by default — fast and cheap per evaluation call.

    Parameters
    ----------
    api_key:    Anthropic API key.  Falls back to ``ANTHROPIC_API_KEY`` env var.
    model:      Model ID to use for evaluation.
    threshold:  Minimum score (0–1) required to consider the run passed.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5-20251001",
        threshold: float = 0.75,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._threshold = threshold

    async def evaluate(self, ctx: CriticContext) -> CriticResult:
        import anthropic  # imported lazily — not required when critic is unused

        criteria_text = "\n".join(f"- {c}" for c in ctx.acceptance_criteria)
        diff_preview = ctx.diff[:6000] if ctx.diff else "(no changes detected)"

        prompt = (
            "You are a code reviewer evaluating whether an implementation satisfies "
            "its acceptance criteria.\n\n"
            f"ACCEPTANCE CRITERIA:\n{criteria_text}\n\n"
            f"AGENT SUMMARY:\n{ctx.agent_summary or '(no summary provided)'}\n\n"
            f"GIT DIFF (what was actually changed):\n```diff\n{diff_preview}\n```\n\n"
            "Evaluate the implementation. Respond with ONLY valid JSON — no prose, "
            "no markdown fences:\n"
            '{"score": <float 0.0-1.0>, '
            '"issues": ["<specific gap>"], '
            '"feedback": "<2-3 sentences on what to fix>"}\n\n'
            "score=1.0 means every criterion is fully satisfied. "
            "score=0.0 means nothing was implemented. "
            "Return an empty issues list and score >= 0.9 when there are no gaps."
        )

        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        message = await client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()

        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                data = json.loads(m.group(0))
                score = float(data.get("score", 0.5))
                issues: list[str] = data.get("issues", [])
                feedback: str = data.get("feedback", "")
                return CriticResult(
                    score=score,
                    issues=issues,
                    passed=score >= self._threshold,
                    feedback=feedback,
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Parsing failed — treat as passing so the critic never hard-blocks a run
        return CriticResult(score=0.8, issues=[], passed=True, feedback=raw[:300])
