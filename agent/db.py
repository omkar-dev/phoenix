"""
Phoenix v5 — SQLite persistence layer

Tables:
  repos            — repo selection history (full_name, last_accessed, access_count)
  issue_movements  — log of Kanban column moves
  run_logs         — persisted SSE events from agent runs

DB lives at  ~/.pnx/pnx.db  (same directory as the base-clone cache).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

DB_PATH = Path.home() / ".pnx" / "pnx.db"

_DDL = """
CREATE TABLE IF NOT EXISTS claude_sessions (
    id                TEXT PRIMARY KEY,
    repo              TEXT NOT NULL,
    project_path      TEXT NOT NULL,
    worktree_path     TEXT,
    claude_session_id TEXT,
    mode              TEXT DEFAULT 'claude_code',
    model             TEXT DEFAULT '',
    api_key           TEXT DEFAULT '',
    status            TEXT DEFAULT 'idle',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claude_sessions_repo ON claude_sessions(repo);

CREATE TABLE IF NOT EXISTS claude_session_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    logged_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claude_session_messages
    ON claude_session_messages(session_id, logged_at);

CREATE TABLE IF NOT EXISTS claude_session_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    logged_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claude_session_events
    ON claude_session_events(session_id, logged_at);

CREATE TABLE IF NOT EXISTS repos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name    TEXT UNIQUE NOT NULL,
    last_accessed TEXT NOT NULL,
    access_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS issue_movements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo         TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    from_column  TEXT NOT NULL,
    to_column    TEXT NOT NULL,
    moved_at     TEXT NOT NULL,
    actor        TEXT
);
CREATE INDEX IF NOT EXISTS idx_movements_repo ON issue_movements(repo);

CREATE TABLE IF NOT EXISTS run_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    repo         TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    event_type   TEXT NOT NULL,
    data         TEXT NOT NULL,
    logged_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_logs_run_id ON run_logs(run_id);

CREATE TABLE IF NOT EXISTS interrupted_runs (
    run_id          TEXT PRIMARY KEY,
    repo            TEXT NOT NULL,
    issue_number    INTEGER NOT NULL,
    worktree_path   TEXT,
    branch_name     TEXT,
    conversation_id TEXT,
    persistence_dir TEXT,
    interrupted_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interrupted_issue ON interrupted_runs(repo, issue_number);
CREATE INDEX IF NOT EXISTS idx_interrupted_branch ON interrupted_runs(repo, branch_name);
"""


async def init_db() -> None:
    """Create DB file and tables if they don't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_DDL)
        # Migration: add actor column to existing issue_movements tables.
        try:
            await db.execute("ALTER TABLE issue_movements ADD COLUMN actor TEXT")
            await db.commit()
        except Exception:
            pass  # column already exists
        # Migration: create interrupted_runs table if not present (added after initial release).
        try:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS interrupted_runs (
                    run_id          TEXT PRIMARY KEY,
                    repo            TEXT NOT NULL,
                    issue_number    INTEGER NOT NULL,
                    worktree_path   TEXT,
                    branch_name     TEXT,
                    conversation_id TEXT,
                    persistence_dir TEXT,
                    interrupted_at  TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_interrupted_issue
                    ON interrupted_runs(repo, issue_number);
                CREATE INDEX IF NOT EXISTS idx_interrupted_branch
                    ON interrupted_runs(repo, branch_name);
            """)
            await db.commit()
        except Exception:
            pass
        # Migration: add conversation_id and persistence_dir columns to existing tables.
        for col in ("conversation_id TEXT", "persistence_dir TEXT"):
            try:
                await db.execute(f"ALTER TABLE interrupted_runs ADD COLUMN {col}")
                await db.commit()
            except Exception:
                pass  # column already exists
        # Migration: create claude_sessions and related tables.
        try:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS claude_sessions (
                    id                TEXT PRIMARY KEY,
                    repo              TEXT NOT NULL,
                    project_path      TEXT NOT NULL,
                    worktree_path     TEXT,
                    claude_session_id TEXT,
                    mode              TEXT DEFAULT 'claude_code',
                    model             TEXT DEFAULT '',
                    status            TEXT DEFAULT 'idle',
                    created_at        TEXT NOT NULL,
                    updated_at        TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_claude_sessions_repo ON claude_sessions(repo);
                CREATE TABLE IF NOT EXISTS claude_session_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    payload     TEXT NOT NULL,
                    logged_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_claude_session_events
                    ON claude_session_events(session_id, logged_at);
                CREATE TABLE IF NOT EXISTS claude_session_messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    logged_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_claude_session_messages
                    ON claude_session_messages(session_id, logged_at);
            """)
            await db.commit()
        except Exception:
            pass
        # Migration: add mode/model/api_key columns to existing claude_sessions tables.
        for col_def in ("mode TEXT DEFAULT 'claude_code'", "model TEXT DEFAULT ''", "api_key TEXT DEFAULT ''"):
            try:
                await db.execute(f"ALTER TABLE claude_sessions ADD COLUMN {col_def}")
                await db.commit()
            except Exception:
                pass


# ── Repos ──────────────────────────────────────────────────────────────────────

async def upsert_repo(full_name: str) -> None:
    """Insert or update a repo, bumping access_count and refreshing last_accessed."""
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO repos (full_name, last_accessed, access_count)
            VALUES (?, ?, 1)
            ON CONFLICT(full_name) DO UPDATE SET
                last_accessed = excluded.last_accessed,
                access_count  = access_count + 1
            """,
            (full_name, now),
        )
        await db.commit()


async def list_repos(limit: int = 50) -> list[dict]:
    """Return repos ordered by most recently accessed."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT full_name, last_accessed, access_count FROM repos "
            "ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_repo(full_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM repos WHERE full_name = ?", (full_name,))
        await db.commit()


# ── Issue movements ────────────────────────────────────────────────────────────

async def log_movement(
    repo: str, issue_number: int, from_column: str, to_column: str,
    actor: str | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO issue_movements (repo, issue_number, from_column, to_column, moved_at, actor)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (repo, issue_number, from_column, to_column, now, actor),
        )
        await db.commit()


async def list_movements(
    repo: str | None = None, limit: int = 200
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if repo:
            async with db.execute(
                "SELECT * FROM issue_movements WHERE repo = ? "
                "ORDER BY moved_at DESC LIMIT ?",
                (repo, limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        async with db.execute(
            "SELECT * FROM issue_movements ORDER BY moved_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Run logs ───────────────────────────────────────────────────────────────────

async def append_run_log(
    run_id: str,
    repo: str,
    issue_number: int,
    event_type: str,
    data: dict,
) -> None:
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO run_logs (run_id, repo, issue_number, event_type, data, logged_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, repo, issue_number, event_type, json.dumps(data), now),
        )
        await db.commit()


async def save_interrupted_run(
    run_id: str,
    repo: str,
    issue_number: int,
    worktree_path: str | None,
    branch_name: str | None,
    conversation_id: str | None = None,
    persistence_dir: str | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO interrupted_runs
                (run_id, repo, issue_number, worktree_path, branch_name,
                 conversation_id, persistence_dir, interrupted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, repo, issue_number, worktree_path, branch_name,
             conversation_id, persistence_dir, now),
        )
        await db.commit()


async def get_interrupted_run(run_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM interrupted_runs WHERE run_id = ?", (run_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_latest_interrupted_run(repo: str, issue_number: int) -> dict | None:
    """Return the most recent interrupted run for a given issue."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM interrupted_runs WHERE repo = ? AND issue_number = ? "
            "ORDER BY interrupted_at DESC LIMIT 1",
            (repo, issue_number),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_interrupted_run_by_branch(repo: str, branch_name: str) -> dict | None:
    """Return the most recent interrupted run for a given branch name."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM interrupted_runs WHERE repo = ? AND branch_name = ? "
            "ORDER BY interrupted_at DESC LIMIT 1",
            (repo, branch_name),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def delete_interrupted_run(run_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM interrupted_runs WHERE run_id = ?", (run_id,))
        await db.commit()


async def get_run_logs(run_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM run_logs WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ) as cur:
            rows = await cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"])
        except (json.JSONDecodeError, TypeError):
            pass
        result.append(d)
    return result


# ── Claude Sessions ────────────────────────────────────────────────────────────

async def create_claude_session(
    session_id: str,
    repo: str,
    project_path: str,
    worktree_path: str | None = None,
    mode: str = "claude_code",
    model: str = "",
) -> None:
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO claude_sessions
                (id, repo, project_path, worktree_path, mode, model, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, repo, project_path, worktree_path, mode, model, now, now),
        )
        await db.commit()


async def get_claude_session(session_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM claude_sessions WHERE id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def update_claude_session(session_id: str, **kwargs) -> None:
    if not kwargs:
        return
    now = datetime.now(UTC).isoformat()
    kwargs["updated_at"] = now
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [session_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE claude_sessions SET {fields} WHERE id = ?", values
        )
        await db.commit()


async def list_claude_sessions(repo: str | None = None, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if repo:
            async with db.execute(
                "SELECT * FROM claude_sessions WHERE repo = ? ORDER BY updated_at DESC LIMIT ?",
                (repo, limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM claude_sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def delete_claude_session(session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM claude_session_events WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM claude_sessions WHERE id = ?", (session_id,))
        await db.commit()


async def append_claude_session_event(
    session_id: str, event_type: str, payload: dict
) -> None:
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO claude_session_events (session_id, event_type, payload, logged_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, event_type, json.dumps(payload), now),
        )
        await db.commit()


async def append_claude_session_message(session_id: str, role: str, content: str) -> None:
    """Persist a conversation message for API-mode history."""
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO claude_session_messages (session_id, role, content, logged_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        await db.commit()


async def get_claude_session_messages(session_id: str) -> list[dict]:
    """Return full conversation history for API-mode sessions (oldest first)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content FROM claude_session_messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def get_claude_session_events(session_id: str, limit: int = 200) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT event_type, payload, logged_at FROM claude_session_events "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ) as cur:
            rows = await cur.fetchall()
    result = []
    for r in rows:
        try:
            payload = json.loads(r["payload"])
        except (json.JSONDecodeError, TypeError):
            payload = {}
        result.append({"event_type": r["event_type"], "payload": payload, "logged_at": r["logged_at"]})
    return result
