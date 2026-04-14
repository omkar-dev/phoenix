"""Tests for the pnx CLI tool."""

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from cli import (
    _build_parser,
    _is_status_label,
    _positive_int,
    _resolve_repo,
)


# ── Argument parsing ────────────────────────────────────────────


class TestParser:
    def test_no_args_shows_help(self, capsys):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_improve_requires_issue_number(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["improve"])

    def test_start_requires_issue_number(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["start"])

    def test_improve_parses_issue_number(self):
        parser = _build_parser()
        args = parser.parse_args(["improve", "42"])
        assert args.command == "improve"
        assert args.issue_number == 42

    def test_start_parses_issue_number(self):
        parser = _build_parser()
        args = parser.parse_args(["start", "7"])
        assert args.command == "start"
        assert args.issue_number == 7

    def test_repo_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--repo", "owner/repo", "start", "1"])
        assert args.repo == "owner/repo"

    def test_agent_url_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--agent-url", "http://myhost:9000", "improve", "1"])
        assert args.agent_url == "http://myhost:9000"

    def test_default_agent_url(self):
        parser = _build_parser()
        args = parser.parse_args(["start", "1"])
        assert "localhost" in args.agent_url


# ── Positive int validator ──────────────────────────────────────


class TestPositiveInt:
    def test_valid(self):
        assert _positive_int("42") == 42
        assert _positive_int("1") == 1

    def test_zero_rejected(self):
        with pytest.raises(Exception):
            _positive_int("0")

    def test_negative_rejected(self):
        with pytest.raises(Exception):
            _positive_int("-5")

    def test_non_numeric_rejected(self):
        with pytest.raises(Exception):
            _positive_int("abc")

    def test_float_rejected(self):
        with pytest.raises(Exception):
            _positive_int("3.14")


# ── Status label detection ──────────────────────────────────────


class TestIsStatusLabel:
    def test_in_progress(self):
        assert _is_status_label("in progress") is True
        assert _is_status_label("In Progress") is True

    def test_todo(self):
        assert _is_status_label("to do") is True
        assert _is_status_label("todo") is True

    def test_done(self):
        assert _is_status_label("done") is True
        assert _is_status_label("completed") is True

    def test_review(self):
        assert _is_status_label("in review") is True

    def test_non_status(self):
        assert _is_status_label("bug") is False
        assert _is_status_label("enhancement") is False
        assert _is_status_label("documentation") is False

    def test_wip(self):
        assert _is_status_label("wip") is True


# ── Repo resolution ─────────────────────────────────────────────


class TestResolveRepo:
    def test_explicit_arg(self):
        assert _resolve_repo("owner/repo") == "owner/repo"

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "org/project")
        assert _resolve_repo(None) == "org/project"

    def test_git_remote_ssh(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:owner/repo.git\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _resolve_repo(None) == "owner/repo"

    def test_git_remote_https(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _resolve_repo(None) == "owner/repo"

    def test_git_remote_https_no_dot_git(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/owner/repo\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _resolve_repo(None) == "owner/repo"

    def test_no_git(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert _resolve_repo(None) == ""

    def test_explicit_arg_takes_priority(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "env/repo")
        assert _resolve_repo("arg/repo") == "arg/repo"


# ── Integration: main() exit codes ──────────────────────────────


class TestMainExitCodes:
    def test_no_command_exits_zero(self):
        """No subcommand prints help and exits 0."""
        from cli import main

        with patch("sys.argv", ["pnx"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_invalid_issue_number_exits_nonzero(self):
        """Non-numeric issue number causes argparse to exit 2."""
        from cli import main

        with patch("sys.argv", ["pnx", "improve", "abc"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0

    def test_improve_missing_repo_exits_nonzero(self, monkeypatch):
        """improve with no repo returns exit code 1."""
        from cli import main

        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        with (
            patch("sys.argv", ["pnx", "improve", "42"]),
            patch("subprocess.run", side_effect=FileNotFoundError),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_start_missing_repo_exits_nonzero(self, monkeypatch):
        """start with no repo returns exit code 1."""
        from cli import main

        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        with (
            patch("sys.argv", ["pnx", "--repo", "", "start", "42"]),
            patch("subprocess.run", side_effect=FileNotFoundError),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
