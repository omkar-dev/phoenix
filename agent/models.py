
from typing import Optional

from pydantic import BaseModel, Field


class IssueSpec(BaseModel):
    intent: str
    acceptance_criteria: list[str]
    technical_notes: str | None = None
    context_files: list[str] = Field(default_factory=list)
    additional_comments: Optional[str] = None  # extra context provided during reimplementation


class McpServer(BaseModel):
    id: str
    name: str
    url: str
    transport: str = "sse"
    token: str = ""


class RunRequest(BaseModel):
    issue_number: int
    repo_full_name: str  # "owner/repo"
    spec: IssueSpec
    base_branch: str = "main"
    create_draft_pr: bool = True
    mcp_servers: list[McpServer] = Field(default_factory=list)
    # LLM selection — falls back to ANTHROPIC_API_KEY / LLM_MODEL env vars if not supplied.
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None         # e.g. https://api.anthropic.com
    fallback_llm_model: str | None = None   # used if primary model fails
    # Agent personality & behaviour
    system_prompt: Optional[str] = None         # prepended to every task prompt
    purpose: Optional[str] = None               # one-line agent role description
    reasoning_pattern: Optional[str] = None     # e.g. "observe-plan-act"
    guardrails_always: Optional[str] = None     # things the agent must always do
    guardrails_never: Optional[str] = None      # things the agent must never do
    sampling: Optional[str] = None              # deterministic | balanced | creative
    autonomy: Optional[str] = None              # assist | semi-autonomous | autonomous
    max_iterations: Optional[int] = Field(None, ge=1, description="Max agent iterations per run")
    existing_branch: Optional[str] = None       # when set, check out this branch and push to it (no new PR)


class RunEvent(BaseModel):
    type: str  # start | progress | reasoning | tool_call | tool_result | complete | error | close | ping
    timestamp: str
    data: dict


class WorktreeRequest(BaseModel):
    issue_number: int
    repo_full_name: str
    base_branch: str = "main"
    editor_cmd: str = "code"


class OpenEditorRequest(BaseModel):
    path: str
    cmd: str = "code"


class RefineRequest(BaseModel):
    title: str
    body: str
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    system_prompt: str | None = None
    user_prompt: str | None = None
    sampling: str | None = None


class RepoBody(BaseModel):
    full_name: str


class MovementBody(BaseModel):
    repo: str
    issue_number: int
    from_column: str
    to_column: str
    actor: str | None = None


class PushDirectRequest(BaseModel):
    worktree_path: str
    branch_name: str
    repo_full_name: str
    issue_number: int
    base_branch: str = "main"
    create_draft_pr: bool = True
