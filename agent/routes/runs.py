import asyncio
import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from github import Github

import broadcast as _broadcast
import db as _db
from agent import ImplementerAgent
from config import GITHUB_TOKEN
from critic import DefaultCritic
from models import PushDirectRequest, RunEvent, RunRequest
from registry import RunState, _runs

router = APIRouter()


def _on_task_done(run_id: str, task: asyncio.Task) -> None:
    state = _runs.get(run_id)
    if state and not task.cancelled() and task.exception() is None:
        state.result = task.result()


@router.post("/runs", status_code=202)
async def create_run(request: RunRequest) -> dict:
    run_id = str(uuid.uuid4())
    critic = None
    if request.critic and request.critic.enabled:
        critic = DefaultCritic(
            api_key=request.llm_api_key or None,
            model=request.critic.model or "claude-haiku-4-5-20251001",
            threshold=request.critic.threshold,
        )
    agent = ImplementerAgent(run_id, request, critic=critic)
    task = asyncio.create_task(agent.run(), name=f"run-{run_id[:8]}")
    _runs[run_id] = RunState(run_id=run_id, agent=agent, task=task)
    task.add_done_callback(lambda t: _on_task_done(run_id, t))
    asyncio.create_task(_broadcast.broadcast({
        "type": "run_started",
        "runId": run_id,
        "issueNumber": request.issue_number,
        "repo": request.repo_full_name,
    }))
    return {"run_id": run_id, "stream_url": f"/runs/{run_id}/stream"}


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    async def generate() -> AsyncIterator[str]:
        async for event in state.agent.events():
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/status")
async def run_status(run_id: str) -> dict:
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    if not state.task.done():
        return {"status": "running"}
    result = state.result
    if result is None or not result.success:
        if result and result.interrupted:
            return {
                "status": "interrupted",
                "error": result.error,
                "worktree_path": result.worktree_path,
                "branch": result.branch,
            }
        return {"status": "failed", "error": result.error if result else "unknown"}
    return {
        "status": "complete",
        "pr_url": result.pr_url,
        "branch": result.branch_name,
        "files": result.files_changed,
    }


@router.post("/runs/{run_id}/push")
async def push_run(run_id: str) -> dict:
    """Push the committed branch and open a draft PR."""
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        pr_url = await state.agent.push_and_pr()
        return {"ok": True, "pr_url": pr_url}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str) -> dict:
    state = _runs.pop(run_id, None)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    _cancelled_issue = state.agent.request.issue_number
    _cancelled_repo = state.agent.request.repo_full_name
    state.task.cancel()
    asyncio.create_task(_broadcast.broadcast({
        "type": "run_cancelled",
        "runId": run_id,
        "issueNumber": _cancelled_issue,
        "repo": _cancelled_repo,
    }))

    async def _cleanup_after_cancel(task: asyncio.Task, agent: ImplementerAgent) -> None:
        try:
            await asyncio.wait([task], timeout=30.0)
        except Exception:
            pass
        try:
            await agent._cleanup_worktree()
        except Exception:
            pass

    asyncio.create_task(_cleanup_after_cancel(state.task, state.agent))
    return {"ok": True}


@router.get("/runs/{run_id}/logs")
async def get_run_logs(run_id: str) -> list[dict]:
    return await _db.get_run_logs(run_id)


@router.get("/runs/{run_id}/interrupted")
async def get_interrupted_state(run_id: str) -> dict:
    """Return the saved worktree/branch for an interrupted run."""
    state = await _db.get_interrupted_run(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="No interrupted state found")
    return state


@router.post("/push-direct")
async def push_direct(req: PushDirectRequest) -> dict:
    """Push a committed worktree branch and open a PR without an in-memory run.

    Used as a fallback when the server has restarted and the original run is
    gone from memory but the worktree is still on disk.
    """
    worktree = Path(req.worktree_path)
    if not worktree.exists():
        raise HTTPException(status_code=410, detail="worktree_gone")

    # Force-push the branch (it already exists on remote from the previous run)
    result = await asyncio.to_thread(
        subprocess.run,
        ["git", "push", "--force", "-u", "origin", req.branch_name],
        cwd=str(worktree),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git push: {result.stderr}")

    # Open or update the PR via GitHub API
    try:
        gh = Github(GITHUB_TOKEN)
        repo = await asyncio.to_thread(gh.get_repo, req.repo_full_name)
        issue = await asyncio.to_thread(repo.get_issue, req.issue_number)
        title = f"feat: implement #{req.issue_number}: {issue.title}"
        body = f"Fixes #{req.issue_number}\n\n---\n_Implemented by Phoenix_"

        # Check if a PR already exists for this branch
        pulls = await asyncio.to_thread(
            lambda: list(repo.get_pulls(state="open", head=f"{repo.owner.login}:{req.branch_name}"))
        )
        if pulls:
            pr = pulls[0]
        else:
            pr = await asyncio.to_thread(
                repo.create_pull,
                title=title,
                body=body,
                head=req.branch_name,
                base=req.base_branch,
                draft=req.create_draft_pr,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"GitHub PR: {exc}")

    return {"ok": True, "pr_url": pr.html_url}
