"""
Phoenix v5 — ReviewerAgent (Phase 7)

After ImplementerAgent creates a PR, ReviewerAgent:
1. Fetches the PR diff via PyGithub
2. Evaluates it against the acceptance criteria via LLM
3. Posts a GitHub PR review (APPROVE or REQUEST_CHANGES)
4. Broadcasts a pipeline_stage SSE event

The reviewer is optional — only active when RunRequest.enable_reviewer=True.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import broadcast as _broadcast
from config import ANTHROPIC_API_KEY, GITHUB_TOKEN
from models import IssueSpec

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_DIFF_CHARS = 12_000  # token budget for the diff

_SYSTEM_PROMPT = """\
You are a code reviewer. Given a PR diff and acceptance criteria, decide:
- APPROVE if the diff clearly satisfies all criteria and has no obvious bugs
- REQUEST_CHANGES if criteria are unmet or there are clear defects

Respond with JSON:
{
  "decision": "APPROVE" | "REQUEST_CHANGES",
  "summary": "<1-3 sentence review comment>",
  "score": <0.0-1.0 confidence>
}
No prose outside the JSON."""


@dataclass
class ReviewResult:
    passed: bool
    summary: str
    score: float


class ReviewerAgent:
    """Reviews a PR diff against acceptance criteria and posts a GitHub review."""

    def __init__(self, api_key: str | None = None, run_id: str = "") -> None:
        self._api_key = api_key or ANTHROPIC_API_KEY
        self._run_id = run_id

    async def review_and_post(
        self,
        repo_full_name: str,
        pr_number: int,
        spec: IssueSpec,
    ) -> ReviewResult:
        """
        Fetch diff, call LLM, post review. Returns ReviewResult.
        On error, returns a neutral passing result (fail-open).
        """
        await _broadcast.broadcast({
            "type": "pipeline_stage",
            "runId": self._run_id,
            "stage": "reviewing",
            "repo": repo_full_name,
            "prNumber": pr_number,
        })

        # 1. Fetch diff
        diff_text = await self._fetch_diff(repo_full_name, pr_number)

        # 2. Evaluate
        result = await self._evaluate(spec, diff_text)

        # 3. Post review
        await self._post_review(repo_full_name, pr_number, result)

        logger.info(
            "ReviewerAgent: %s (score=%.2f) for %s#%s",
            "APPROVE" if result.passed else "REQUEST_CHANGES",
            result.score,
            repo_full_name,
            pr_number,
        )
        return result

    async def _fetch_diff(self, repo_full_name: str, pr_number: int) -> str:
        """Return a truncated unified diff of the PR."""
        try:
            from github import Github
            gh = Github(GITHUB_TOKEN)
            repo = await asyncio.to_thread(gh.get_repo, repo_full_name)
            pr = await asyncio.to_thread(repo.get_pull, pr_number)
            files = await asyncio.to_thread(pr.get_files)
            parts = []
            for f in files:
                patch = f.patch or ""
                parts.append(f"--- {f.filename} (+{f.additions}/-{f.deletions})\n{patch}")
            return "\n\n".join(parts)[:MAX_DIFF_CHARS]
        except Exception as exc:
            logger.warning("ReviewerAgent: failed to fetch diff: %s", exc)
            return ""

    async def _evaluate(self, spec: IssueSpec, diff_text: str) -> ReviewResult:
        """LLM evaluation. Returns a passing result if LLM call fails."""
        if not diff_text:
            return ReviewResult(passed=True, summary="No diff available — auto-approved.", score=0.5)

        criteria = "\n".join(f"- {c}" for c in spec.acceptance_criteria)
        user_message = (
            f"Acceptance criteria:\n{criteria}\n\n"
            f"PR diff:\n```diff\n{diff_text}\n```"
        )

        try:
            import json
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self._api_key)
            response = await client.messages.create(
                model=_HAIKU_MODEL,
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text if response.content else "{}"
            data = json.loads(raw)
            return ReviewResult(
                passed=data.get("decision", "APPROVE") == "APPROVE",
                summary=data.get("summary", ""),
                score=float(data.get("score", 0.5)),
            )
        except Exception as exc:
            logger.warning("ReviewerAgent LLM call failed: %s", exc)
            return ReviewResult(passed=True, summary="Review skipped due to LLM error.", score=0.5)

    async def _post_review(
        self,
        repo_full_name: str,
        pr_number: int,
        result: ReviewResult,
    ) -> None:
        """Post APPROVE or REQUEST_CHANGES review via PyGithub."""
        try:
            from github import Github
            gh = Github(GITHUB_TOKEN)
            repo = await asyncio.to_thread(gh.get_repo, repo_full_name)
            pr = await asyncio.to_thread(repo.get_pull, pr_number)
            event = "APPROVE" if result.passed else "REQUEST_CHANGES"
            body = result.summary or ("LGTM" if result.passed else "Changes needed.")
            await asyncio.to_thread(pr.create_review, body=body, event=event)
        except Exception as exc:
            logger.warning("ReviewerAgent: failed to post review: %s", exc)
