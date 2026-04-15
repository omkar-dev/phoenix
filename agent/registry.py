import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import ImplementerAgent


@dataclass
class AgentResult:
    success: bool
    branch_name: str | None = None
    pr_url: str | None = None
    files_changed: list[str] = field(default_factory=list)
    summary: str = ""
    error: str | None = None
    interrupted: bool = False       # True when MaxIterationsReached (partial work preserved)
    worktree_path: str | None = None  # preserved worktree dir when interrupted
    branch: str | None = None         # branch name when interrupted


@dataclass
class RunState:
    run_id: str
    agent: "ImplementerAgent"
    task: asyncio.Task
    result: AgentResult | None = None


_runs: dict[str, RunState] = {}
