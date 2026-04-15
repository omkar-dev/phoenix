"""
Phoenix v5 — CI Log Collector

Fetches failed check run logs from GitHub for a branch tip commit.
Used by the CI feedback loop to provide context to the retrying agent.
"""

from __future__ import annotations

import asyncio

from github import Github


MAX_LOG_CHARS = 8_000   # token budget for CI context injected into spec
MAX_FAILED_CHECKS = 5   # cap to avoid overwhelming the prompt


class CILogCollector:
    def __init__(self, github_token: str):
        self._gh = Github(github_token)

    async def collect_failed_logs(self, repo_full_name: str, branch_name: str) -> str:
        """
        Return a markdown-formatted string of failed check run outputs for the
        tip commit of branch_name. Returns empty string if nothing fails or
        the GitHub API is unreachable.
        """
        try:
            repo = await asyncio.to_thread(self._gh.get_repo, repo_full_name)
            branch = await asyncio.to_thread(repo.get_branch, branch_name)
            sha = branch.commit.sha

            check_runs = await asyncio.to_thread(
                lambda: list(repo.get_commit(sha).get_check_runs())
            )
        except Exception:
            return ""

        failed = [
            cr for cr in check_runs
            if cr.conclusion in ("failure", "timed_out", "cancelled", "action_required")
        ][:MAX_FAILED_CHECKS]

        if not failed:
            return ""

        budget_per_check = MAX_LOG_CHARS // max(len(failed), 1)
        parts: list[str] = []

        for cr in failed:
            parts.append(f"### Failed check: {cr.name}")
            text = ""
            try:
                if cr.output and cr.output.text:
                    text = cr.output.text[:budget_per_check]
                elif cr.output and cr.output.summary:
                    text = cr.output.summary[:budget_per_check]
            except Exception:
                pass

            if text:
                parts.append(f"```\n{text}\n```")
            else:
                parts.append("_(no log output available)_")

        return "\n\n".join(parts)
