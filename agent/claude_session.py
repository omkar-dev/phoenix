"""
Phoenix v5 — Persistent Claude Code Session Manager

Manages long-lived interactive Claude Code CLI sessions at the project level.
Each session gets an isolated git worktree and persists the Claude CLI session
ID so conversations can be resumed across page reloads via --resume.

Architecture:
  - One ClaudeSessionManager singleton (shared by all WebSocket connections)
  - Per message: spawn `claude --output-format stream-json [-p msg | --resume id -p msg]`
  - Capture system.init session_id from first invocation; pass to --resume on all subsequent ones
  - Stream JSON events to all attached WebSocket clients
  - Persist events to SQLite for history replay on reconnect
"""

import asyncio
import json
import shutil
import tempfile
import uuid
from pathlib import Path

import litellm

import db as _db
from config import BASE_REPOS_DIR, GITHUB_TOKEN, _repo_locks

# litellm model strings and API bases per mode.
# copilot uses the OpenAI-compatible GitHub Models endpoint.
_MODE_CONFIG: dict[str, dict] = {
    "claude":  {"prefix": "",        "api_base": None},
    "openai":  {"prefix": "openai/", "api_base": None},
    "copilot": {"prefix": "openai/", "api_base": "https://api.githubcopilot.com"},
}


async def _git(*args: str, cwd: Path) -> tuple[int, str]:
    """Run a git command, return (returncode, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    return proc.returncode, stderr.decode().strip()


async def setup_session_worktree(
    session_id: str,
    repo_full_name: str,
    clone_url: str,
    base_branch: str = "main",
) -> Path:
    """Ensure a base clone exists and create an isolated worktree for the session.

    Reuses the same BASE_REPOS_DIR shallow-clone cache as ImplementerAgent so
    the first session for a repo is fast if a run has already been executed.
    """
    repo_key = repo_full_name.replace("/", "-")
    base_dir = BASE_REPOS_DIR / repo_key
    auth_url = clone_url.replace("https://", f"https://x-access-token:{GITHUB_TOKEN}@")

    if repo_key not in _repo_locks:
        _repo_locks[repo_key] = asyncio.Lock()
    lock = _repo_locks[repo_key]

    async with lock:
        if not base_dir.exists():
            BASE_REPOS_DIR.mkdir(parents=True, exist_ok=True)
            rc, err = await _git(
                "clone", "--depth", "1", "-b", base_branch, auth_url, str(base_dir),
                cwd=BASE_REPOS_DIR,
            )
            if rc != 0:
                raise RuntimeError(f"git clone failed: {err}")
        else:
            await _git("remote", "set-url", "origin", auth_url, cwd=base_dir)
            rc, err = await _git(
                "fetch", "--depth", "1", "origin", base_branch, cwd=base_dir
            )
            if rc != 0:
                raise RuntimeError(f"git fetch failed: {err}")
            await _git("reset", "--hard", f"origin/{base_branch}", cwd=base_dir)

        # Prune stale worktree metadata before adding a new one.
        await _git("worktree", "prune", cwd=base_dir)

        worktree_path = Path(tempfile.gettempdir()) / f"pnx-session-{session_id[:8]}"
        branch_name = f"pnx/session-{session_id[:8]}"

        # Remove a leftover branch from a crashed previous session.
        await _git("branch", "-D", branch_name, cwd=base_dir)

        rc, err = await _git(
            "worktree", "add", "-b", branch_name,
            str(worktree_path), f"origin/{base_branch}",
            cwd=base_dir,
        )
        if rc != 0:
            raise RuntimeError(f"git worktree add failed: {err}")

    return worktree_path


async def cleanup_session_worktree(
    repo_full_name: str, worktree_path: str | None, branch_name: str | None
) -> None:
    """Remove the session worktree and its branch (best-effort, errors silenced)."""
    if not worktree_path:
        return
    repo_key = repo_full_name.replace("/", "-")
    base_dir = BASE_REPOS_DIR / repo_key
    wt = Path(worktree_path)
    try:
        if base_dir.exists():
            await _git("worktree", "remove", "--force", str(wt), cwd=base_dir)
            if branch_name:
                await _git("branch", "-D", branch_name, cwd=base_dir)
    except Exception:
        pass
    try:
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)
    except Exception:
        pass


class ClaudeSessionManager:
    """Singleton that manages Claude Code CLI sessions and WebSocket clients."""

    def __init__(self) -> None:
        # session_id → set of connected WebSocket objects
        self._ws_clients: dict[str, set] = {}
        # session_id → True while a claude subprocess is running
        self._running: dict[str, bool] = {}

    # ── WebSocket client management ───────────────────────────────────────────

    async def attach(self, session_id: str, websocket) -> None:
        """Add a WebSocket client and replay recent history to it."""
        if session_id not in self._ws_clients:
            self._ws_clients[session_id] = set()
        self._ws_clients[session_id].add(websocket)

        # Replay persisted events so the reconnecting client sees past output.
        events = await _db.get_claude_session_events(session_id, limit=200)
        for ev in events:
            try:
                await websocket.send_json(ev["payload"])
            except Exception:
                break

        # Send current running status.
        is_running = self._running.get(session_id, False)
        try:
            await websocket.send_json({
                "type": "phoenix_status",
                "status": "running" if is_running else "idle",
            })
        except Exception:
            pass

    def detach(self, session_id: str, websocket) -> None:
        """Remove a WebSocket client from the broadcast set."""
        clients = self._ws_clients.get(session_id)
        if clients:
            clients.discard(websocket)

    async def _broadcast(self, session_id: str, event: dict) -> None:
        """Send an event to all connected WebSocket clients for this session."""
        clients = self._ws_clients.get(session_id, set())
        dead: set = set()
        for ws in list(clients):
            try:
                await ws.send_json(event)
            except Exception:
                dead.add(ws)
        clients -= dead

    # ── Message sending ───────────────────────────────────────────────────────

    async def send_message(self, session_id: str, message: str) -> None:
        """Invoke the Claude CLI, stream events to clients, and persist to DB.

        Safe to call concurrently — if a message is already being processed for
        this session the new one is queued after the current one finishes.
        """
        # Simple serialisation: wait until any prior invocation completes.
        while self._running.get(session_id, False):
            await asyncio.sleep(0.1)

        self._running[session_id] = True
        await self._broadcast(session_id, {"type": "phoenix_status", "status": "running"})

        try:
            await self._invoke_claude(session_id, message)
        except Exception as exc:
            err_event = {"type": "error", "message": str(exc)}
            await self._broadcast(session_id, err_event)
            asyncio.create_task(
                _db.append_claude_session_event(session_id, "error", err_event)
            )
        finally:
            self._running[session_id] = False
            await self._broadcast(session_id, {"type": "phoenix_status", "status": "idle"})

    async def _invoke_claude(self, session_id: str, message: str) -> None:
        """Dispatch to CLI or API mode depending on session configuration."""
        session = await _db.get_claude_session(session_id)
        if not session:
            raise RuntimeError(f"Session {session_id} not found")

        mode = session.get("mode") or "claude_code"

        # Broadcast + persist user message (common to all modes).
        user_event = {"type": "user", "content": message}
        await _db.append_claude_session_event(session_id, "user", user_event)
        await self._broadcast(session_id, user_event)

        if mode == "claude_code":
            await self._invoke_cli(session_id, session, message)
        else:
            await self._invoke_api(session_id, session, message, mode)

    async def _invoke_cli(self, session_id: str, session: dict, message: str) -> None:
        """Spawn a `claude` subprocess for one turn and stream its stream-json output."""
        raw_worktree = session.get("worktree_path")
        if raw_worktree and Path(raw_worktree).exists():
            worktree_path = raw_worktree
        elif session.get("project_path") and Path(session["project_path"]).exists():
            worktree_path = session["project_path"]
        else:
            # project_path doesn't exist on this machine — use a stable temp dir
            fallback = Path(tempfile.gettempdir()) / f"pnx-session-cwd-{session_id[:8]}"
            fallback.mkdir(parents=True, exist_ok=True)
            worktree_path = str(fallback)
        claude_session_id = session.get("claude_session_id")

        # -p / --print enables non-interactive mode; --output-format only works with -p.
        # --include-partial-messages streams assistant text as it is generated.
        cmd = ["claude", "-p", message,
               "--output-format", "stream-json",
               "--include-partial-messages"]
        if claude_session_id:
            cmd = ["claude", "--resume", claude_session_id,
                   "-p", message,
                   "--output-format", "stream-json",
                   "--include-partial-messages"]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        new_claude_session_id: str | None = None

        async for raw_line in proc.stdout:
            line = raw_line.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if (
                event.get("type") == "system"
                and event.get("subtype") == "init"
                and not new_claude_session_id
            ):
                new_claude_session_id = event.get("session_id")

            await self._broadcast(session_id, event)
            asyncio.create_task(
                _db.append_claude_session_event(session_id, event.get("type", "unknown"), event)
            )

        await proc.wait()

        stderr_bytes = await proc.stderr.read()
        if proc.returncode != 0 and stderr_bytes:
            err_text = stderr_bytes.decode().strip()
            err_event = {"type": "error", "message": err_text}
            await self._broadcast(session_id, err_event)
            asyncio.create_task(
                _db.append_claude_session_event(session_id, "error", err_event)
            )

        if new_claude_session_id:
            await _db.update_claude_session(
                session_id, claude_session_id=new_claude_session_id, status="idle"
            )

    async def _invoke_api(
        self, session_id: str, session: dict, message: str, mode: str
    ) -> None:
        """Call an LLM API via litellm, streaming the response to WebSocket clients.

        Conversation history is stored in claude_session_messages so context
        is preserved across turns without needing --resume.
        """
        cfg = _MODE_CONFIG.get(mode, {"prefix": "", "api_base": None})
        model_name = session.get("model") or "claude-sonnet-4-6"
        litellm_model = cfg["prefix"] + model_name
        api_key: str | None = session.get("api_key") or None
        api_base: str | None = cfg["api_base"]

        # Build messages from stored history + new user message.
        history = await _db.get_claude_session_messages(session_id)
        messages = history + [{"role": "user", "content": message}]

        # Persist user message before calling API.
        await _db.append_claude_session_message(session_id, "user", message)

        try:
            kwargs: dict = dict(model=litellm_model, messages=messages, stream=True)
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["api_base"] = api_base

            response = await litellm.acompletion(**kwargs)

            full_content = ""
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if not delta:
                    continue
                full_content += delta
                chunk_event = {"type": "assistant", "content": delta, "streaming": True}
                await self._broadcast(session_id, chunk_event)
                asyncio.create_task(
                    _db.append_claude_session_event(session_id, "assistant", chunk_event)
                )

            result_event = {"type": "result", "subtype": "success", "result": full_content}
            await self._broadcast(session_id, result_event)
            asyncio.create_task(
                _db.append_claude_session_event(session_id, "result", result_event)
            )

            await _db.append_claude_session_message(session_id, "assistant", full_content)

        except Exception as exc:
            raise RuntimeError(f"API call failed ({litellm_model}): {exc}") from exc

    # ── Session creation helper ───────────────────────────────────────────────

    async def create(
        self,
        session_id: str,
        repo: str,
        project_path: str,
        clone_url: str | None = None,
        base_branch: str = "main",
        mode: str = "claude_code",
        model: str = "",
        api_key: str = "",
    ) -> str:
        """Create a DB record; if clone_url provided, also set up a git worktree."""
        worktree_path: str | None = None
        # Only set up a worktree for claude_code mode (API modes don't need local files).
        if clone_url and mode == "claude_code":
            try:
                wt = await setup_session_worktree(
                    session_id, repo, clone_url, base_branch
                )
                worktree_path = str(wt)
            except Exception:
                worktree_path = None

        await _db.create_claude_session(
            session_id, repo, project_path, worktree_path, mode=mode, model=model
        )
        # Store api_key separately so it isn't exposed in list/get responses.
        if api_key:
            await _db.update_claude_session(session_id, api_key=api_key)
        return worktree_path or project_path


# Module-level singleton shared by all route handlers.
manager = ClaudeSessionManager()
