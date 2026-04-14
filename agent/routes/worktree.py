import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from github import Github

from config import BASE_REPOS_DIR, GITHUB_TOKEN, _repo_locks
from models import OpenEditorRequest, WorktreeRequest

router = APIRouter()


@router.post("/worktree")
async def create_worktree(req: WorktreeRequest) -> dict:
    """Create (or reuse) a persistent worktree for an issue and open it in the editor."""
    repo_key = req.repo_full_name.replace("/", "-")
    base_dir = BASE_REPOS_DIR / repo_key

    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(req.repo_full_name)
    clone_url = repo.clone_url.replace("https://", f"https://x-access-token:{GITHUB_TOKEN}@")

    if repo_key not in _repo_locks:
        _repo_locks[repo_key] = asyncio.Lock()

    worktree_path = BASE_REPOS_DIR / f"{repo_key}-issue-{req.issue_number}"

    async with _repo_locks[repo_key]:
        # Ensure base clone exists
        if not base_dir.exists():
            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", "-b", req.base_branch,
                clone_url, str(base_dir),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise HTTPException(500, f"git clone failed: {stderr.decode().strip()}")
        else:
            proc = await asyncio.create_subprocess_exec(
                "git", "remote", "set-url", "origin", clone_url,
                cwd=base_dir, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            proc = await asyncio.create_subprocess_exec(
                "git", "fetch", "--depth", "1", "origin", req.base_branch,
                cwd=base_dir, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        # Reuse existing worktree if already created for this issue
        if not worktree_path.exists():
            base_branch = f"pnx/issue-{req.issue_number}"
            # Prune stale worktree refs and remove any leftover branch with the same name
            # so that a previous run doesn't block this one.
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "prune",
                cwd=base_dir, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            proc = await asyncio.create_subprocess_exec(
                "git", "branch", "-D", base_branch,
                cwd=base_dir, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            branch = base_branch
            for _attempt in range(1, 100):
                proc = await asyncio.create_subprocess_exec(
                    "git", "worktree", "add", "-b", branch,
                    str(worktree_path), f"origin/{req.base_branch}",
                    cwd=base_dir, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode == 0:
                    break
                err_msg = stderr.decode().strip()
                if "already exists" in err_msg and _attempt < 99:
                    branch = f"{base_branch}-{_attempt + 1}"
                    continue
                raise HTTPException(500, f"git worktree add failed: {err_msg}")

    # Run any custom scripts (e.g. nix-shell, nix develop, cargo build) inside
    # the worktree before opening the editor.  Scripts run sequentially; the
    # first failure aborts the sequence and surfaces a clear error to the caller.
    for idx, script in enumerate(req.custom_scripts, 1):
        proc = await asyncio.create_subprocess_exec(
            "sh", "-c", script,
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_output = stderr.decode().strip() or "(no error output)"
            raise HTTPException(
                status_code=422,
                detail=f"Script {idx} failed (exit {proc.returncode}): {err_output}",
            )

    asyncio.create_task(
        asyncio.create_subprocess_exec(
            req.editor_cmd, str(worktree_path),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
    )
    return {"ok": True, "path": str(worktree_path)}


@router.post("/open-editor")
async def open_editor(req: OpenEditorRequest) -> dict:
    p = Path(req.path).resolve()
    allowed = [
        BASE_REPOS_DIR.resolve(),
        Path(tempfile.gettempdir()).resolve(),
    ]
    if not any(str(p).startswith(str(a)) for a in allowed):
        raise HTTPException(status_code=400, detail="Path outside allowed worktree area")
    asyncio.create_task(
        asyncio.create_subprocess_exec(
            req.cmd, str(p),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    return {"ok": True}
