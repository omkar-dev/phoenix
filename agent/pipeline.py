"""
Phoenix v5 — AgentPipeline (Phase 7)

Optional planner → implementer → reviewer chain.
Activated when RunRequest.enable_planner or enable_reviewer is True.

RunState.agent always points to the inner ImplementerAgent so existing
SSE streaming (/runs/{id}/stream) requires no changes.
"""

from __future__ import annotations

import logging

from registry import AgentResult

logger = logging.getLogger(__name__)


class AgentPipeline:
    """Orchestrates PlannerAgent → ImplementerAgent → ReviewerAgent."""

    def __init__(self, run_id: str, request, critic=None) -> None:
        from agent import ImplementerAgent
        self._run_id = run_id
        self._request = request
        self._critic = critic
        # Always create the implementer — it's the SSE source
        self.implementer = ImplementerAgent(run_id, request, critic=critic)

    async def run(self) -> AgentResult:
        request = self._request

        # 1. Planning stage (optional)
        if request.enable_planner:
            try:
                from planner import PlannerAgent
                planner = PlannerAgent(
                    api_key=request.llm_api_key,
                    run_id=self._run_id,
                )
                request = await planner.plan(request)
                # Rebuild implementer with enriched request
                from agent import ImplementerAgent
                self.implementer = ImplementerAgent(
                    self._run_id, request, critic=self._critic
                )
            except Exception as exc:
                logger.warning("Pipeline: planner failed, continuing without plan: %s", exc)

        # 2. Implementation stage
        result: AgentResult = await self.implementer.run()

        # 3. Review stage (optional — only when PR was created successfully)
        if request.enable_reviewer and result.success and result.pr_url:
            pr_number = self._extract_pr_number(result.pr_url)
            if pr_number:
                try:
                    from reviewer import ReviewerAgent
                    rev = ReviewerAgent(
                        api_key=request.llm_api_key,
                        run_id=self._run_id,
                    )
                    await rev.review_and_post(
                        repo_full_name=request.repo_full_name,
                        pr_number=pr_number,
                        spec=request.spec,
                    )
                except Exception as exc:
                    logger.warning("Pipeline: reviewer failed: %s", exc)

        return result

    # expose events() so RunState.agent.events() works on the pipeline too
    def events(self):
        return self.implementer.events()

    async def _cleanup_worktree(self):
        return await self.implementer._cleanup_worktree()

    @property
    def request(self):
        return self.implementer.request

    @staticmethod
    def _extract_pr_number(pr_url: str) -> int | None:
        """Parse PR number from a GitHub PR URL."""
        try:
            return int(pr_url.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            return None
