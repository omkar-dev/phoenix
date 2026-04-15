"""Tests for Pydantic request/response models."""

import pytest
from pydantic import ValidationError

from models import IssueSpec, MovementBody, RepoBody, RunRequest, TeamAssignmentRequest, TeamAssignmentResult, TeamInfo


def test_issue_spec_minimal():
    spec = IssueSpec(intent="Add dark mode", acceptance_criteria=["Toggle exists"])
    assert spec.technical_notes is None
    assert spec.context_files == []


def test_run_request_defaults():
    req = RunRequest(
        issue_number=1,
        repo_full_name="owner/repo",
        spec=IssueSpec(intent="Fix bug", acceptance_criteria=["Bug is gone"]),
    )
    assert req.base_branch == "main"
    assert req.create_draft_pr is True
    assert req.mcp_servers == []
    assert req.autonomy is None


def test_run_request_requires_issue_number():
    with pytest.raises(ValidationError):
        RunRequest(
            repo_full_name="owner/repo",
            spec=IssueSpec(intent="Fix", acceptance_criteria=[]),
        )


def test_movement_body():
    body = MovementBody(
        repo="owner/repo", issue_number=5,
        from_column="todo", to_column="in_progress"
    )
    assert body.issue_number == 5


def test_repo_body():
    body = RepoBody(full_name="owner/repo")
    assert body.full_name == "owner/repo"


def test_team_info_optional_description():
    t = TeamInfo(id="fullstack", name="Full Stack")
    assert t.description is None


def test_team_assignment_request_defaults():
    req = TeamAssignmentRequest(
        repo="owner/repo",
        issue_number=42,
        issue_title="Fix login bug",
        to_column="todo",
        teams=[TeamInfo(id="fullstack", name="Full Stack")],
    )
    assert req.issue_body == ""
    assert req.llm_api_key is None
    assert req.teams[0].id == "fullstack"


def test_team_assignment_request_requires_fields():
    with pytest.raises(ValidationError):
        TeamAssignmentRequest(repo="owner/repo", issue_number=1, to_column="todo", teams=[])


def test_team_assignment_result_confident():
    result = TeamAssignmentResult(
        team_id="fullstack", team_name="Full Stack",
        confidence=0.85, needs_manual=False,
        reasoning="Full Stack team best matches this issue.",
    )
    assert result.team_id == "fullstack"
    assert not result.needs_manual
    assert result.confidence == 0.85


def test_team_assignment_result_low_confidence():
    result = TeamAssignmentResult(
        team_id=None, team_name=None,
        confidence=0.4, needs_manual=True,
        reasoning="Confidence too low to auto-assign.",
    )
    assert result.team_id is None
    assert result.needs_manual
