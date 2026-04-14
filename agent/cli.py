"""
Phoenix v5 — CLI tool for interacting with the project board.

Entry point: `pnx` (registered in pyproject.toml).

Subcommands:
    pnx improve <issue_number>   Trigger the AI refine workflow for an issue
    pnx start   <issue_number>   Move an issue to "In Progress" on the board
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

# Status labels that correspond to board columns (mirrors src/lib/constants.js).
_STATUS_KEYWORDS = {
    "in progress": "in_progress",
    "wip": "in_progress",
    "doing": "in_progress",
    "in-progress": "in_progress",
    "in review": "in_review",
    "review": "in_review",
    "pr open": "in_review",
    "in-review": "in_review",
    "todo": "todo",
    "to do": "todo",
    "to-do": "todo",
    "ready": "todo",
    "backlog": "todo",
    "done": "done",
    "completed": "done",
    "released": "done",
    "closed": "done",
    "merged": "done",
}

_IN_PROGRESS_LABEL = {"name": "in progress", "color": "003d9b"}

_DEFAULT_AGENT_URL = "http://localhost:8001"


def _resolve_repo(args_repo: str | None) -> str:
    """Resolve the repository full name from CLI arg, env var, or git remote."""
    if args_repo:
        return args_repo

    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # SSH: git@github.com:owner/repo.git
            m = re.match(r"git@[^:]+:(.+?)(?:\.git)?$", url)
            if m:
                return m.group(1)
            # HTTPS: https://github.com/owner/repo.git
            m = re.match(r"https?://[^/]+/(.+?)(?:\.git)?$", url)
            if m:
                return m.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return ""


def _is_status_label(label_name: str) -> bool:
    """Check if a label name is a board status label."""
    lower = label_name.lower()
    return any(kw in lower for kw in _STATUS_KEYWORDS)


def _get_github() -> "Github":
    """Return a PyGithub client, or exit if GITHUB_TOKEN is missing."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is required.", file=sys.stderr)
        sys.exit(1)
    from github import Github

    return Github(token)


def cmd_improve(args: argparse.Namespace) -> int:
    """Handle `pnx improve <issue_number>`."""
    repo_name = _resolve_repo(args.repo)
    if not repo_name:
        print(
            "Error: Could not determine repository. "
            "Use --repo owner/repo or set GITHUB_REPOSITORY.",
            file=sys.stderr,
        )
        return 1

    issue_number = args.issue_number
    agent_url = args.agent_url.rstrip("/")

    # Validate issue exists via GitHub API
    gh = _get_github()
    try:
        repo = gh.get_repo(repo_name)
    except Exception as exc:
        print(f"Error: Repository '{repo_name}' not found: {exc}", file=sys.stderr)
        return 1

    try:
        issue = repo.get_issue(issue_number)
    except Exception:
        print(
            f"Error: Issue #{issue_number} not found in {repo_name}.",
            file=sys.stderr,
        )
        return 1

    if issue.pull_request:
        print(
            f"Error: #{issue_number} is a pull request, not an issue.",
            file=sys.stderr,
        )
        return 1

    # POST /refine to agent server
    payload = json.dumps({
        "title": issue.title,
        "body": issue.body or "",
    }).encode()

    try:
        req = urllib.request.Request(
            f"{agent_url}/refine",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
    except urllib.error.URLError as exc:
        print(
            f"Error: Cannot connect to agent server at {agent_url}: {exc.reason}",
            file=sys.stderr,
        )
        print(
            "Hint: Make sure the agent server is running (./start.sh or make dev).",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"Error: Failed to reach agent server: {exc}", file=sys.stderr)
        return 1

    data = json.loads(resp.read().decode())
    stream_url = data.get("stream_url")
    if not stream_url:
        print("Error: Agent server returned no stream URL.", file=sys.stderr)
        return 1

    print(f"Improving issue #{issue_number}: {issue.title}")
    print(f"Streaming from {agent_url}{stream_url}…\n")

    # Stream SSE events
    return _stream_refine_events(agent_url, stream_url)


def _stream_refine_events(agent_url: str, stream_url: str) -> int:
    """Connect to the SSE stream and print events to the terminal."""
    try:
        req = urllib.request.Request(
            f"{agent_url}{stream_url}",
            headers={"Accept": "text/event-stream"},
        )
        resp = urllib.request.urlopen(req, timeout=120)
    except Exception as exc:
        print(f"Error: Failed to connect to SSE stream: {exc}", file=sys.stderr)
        return 1

    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")
        event_data = event.get("data", {})

        if event_type == "reasoning":
            content = event_data.get("content", "")
            if content:
                print(f"  💭 {content}")
        elif event_type == "progress":
            msg = event_data.get("message", "")
            if msg:
                print(f"  ⏳ {msg}")
        elif event_type == "suggestion":
            _print_suggestion(event_data)
        elif event_type == "error":
            msg = event_data.get("message", "Unknown error")
            print(f"\n  ❌ Error: {msg}", file=sys.stderr)
            return 1
        elif event_type in ("complete", "close"):
            break
        elif event_type == "ping":
            continue

    print("\n✅ Improve workflow complete.")
    return 0


def _print_suggestion(data: dict) -> None:
    """Pretty-print a refinement suggestion."""
    print("\n── Refined Issue ──────────────────────────────────")
    if data.get("title"):
        print(f"  Title: {data['title']}")
    if data.get("description"):
        print(f"\n  Description:\n    {data['description']}")
    criteria = data.get("acceptance_criteria", [])
    if criteria:
        print("\n  Acceptance Criteria:")
        for c in criteria:
            print(f"    ✓ {c}")
    completeness = data.get("overall_completeness")
    if completeness is not None:
        print(f"\n  Completeness: {completeness:.0%}")
    print("───────────────────────────────────────────────────")


def cmd_start(args: argparse.Namespace) -> int:
    """Handle `pnx start <issue_number>`."""
    repo_name = _resolve_repo(args.repo)
    if not repo_name:
        print(
            "Error: Could not determine repository. "
            "Use --repo owner/repo or set GITHUB_REPOSITORY.",
            file=sys.stderr,
        )
        return 1

    issue_number = args.issue_number

    gh = _get_github()
    try:
        repo = gh.get_repo(repo_name)
    except Exception as exc:
        print(f"Error: Repository '{repo_name}' not found: {exc}", file=sys.stderr)
        return 1

    try:
        issue = repo.get_issue(issue_number)
    except Exception:
        print(
            f"Error: Issue #{issue_number} not found in {repo_name}.",
            file=sys.stderr,
        )
        return 1

    if issue.pull_request:
        print(
            f"Error: #{issue_number} is a pull request, not an issue.",
            file=sys.stderr,
        )
        return 1

    if issue.state != "open":
        print(
            f"Error: Issue #{issue_number} is {issue.state}, not open.",
            file=sys.stderr,
        )
        return 1

    # Compute new labels: remove status labels, add "in progress"
    current_labels = [lbl.name for lbl in issue.labels]
    non_status = [name for name in current_labels if not _is_status_label(name)]
    new_labels = non_status + [_IN_PROGRESS_LABEL["name"]]

    # Ensure the "in progress" label exists in the repo
    try:
        repo.get_label(_IN_PROGRESS_LABEL["name"])
    except Exception:
        try:
            repo.create_label(
                name=_IN_PROGRESS_LABEL["name"],
                color=_IN_PROGRESS_LABEL["color"],
            )
        except Exception:
            pass  # 422 = already exists, or no permission — continue anyway

    # Determine the source column for the movement log
    from_column = "triage"
    for name in current_labels:
        lower = name.lower()
        for kw, col in _STATUS_KEYWORDS.items():
            if kw in lower:
                from_column = col
                break

    # Update the issue labels
    try:
        issue.edit(labels=new_labels)
    except Exception as exc:
        print(f"Error: Failed to update labels on #{issue_number}: {exc}", file=sys.stderr)
        return 1

    print(f"✅ Issue #{issue_number} ({issue.title}) moved to In Progress.")

    # Best-effort: log movement to agent server
    agent_url = args.agent_url.rstrip("/")
    _log_movement(agent_url, repo_name, issue_number, from_column, "in_progress")

    return 0


def _log_movement(
    agent_url: str,
    repo: str,
    issue_number: int,
    from_column: str,
    to_column: str,
) -> None:
    """Best-effort POST to /movements on the agent server."""
    payload = json.dumps({
        "repo": repo,
        "issue_number": issue_number,
        "from_column": from_column,
        "to_column": to_column,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{agent_url}/movements",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Agent server may not be running — that's fine


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pnx",
        description="Phoenix CLI — interact with the project board from the terminal.",
        epilog="Examples:\n"
        "  pnx improve 42              Refine issue #42 with AI\n"
        "  pnx start 42 --repo o/r     Move issue #42 to In Progress\n"
        "  pnx improve 7 --agent-url http://localhost:9001\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo",
        default=None,
        metavar="OWNER/REPO",
        help="GitHub repository (default: auto-detect from git remote or GITHUB_REPOSITORY env)",
    )
    parser.add_argument(
        "--agent-url",
        default=os.environ.get("AGENT_URL", _DEFAULT_AGENT_URL),
        metavar="URL",
        help=f"Agent server URL (default: {_DEFAULT_AGENT_URL}, overridable via AGENT_URL env)",
    )

    sub = parser.add_subparsers(dest="command", title="commands")

    improve = sub.add_parser(
        "improve",
        help="Trigger the AI improve/refine workflow for an issue",
        description="Sends the issue to the AI refiner and streams the result.",
    )
    improve.add_argument(
        "issue_number",
        type=_positive_int,
        help="GitHub issue number",
    )

    start = sub.add_parser(
        "start",
        help="Start work on an issue (move to In Progress)",
        description="Transitions the issue to 'In Progress' by updating its labels.",
    )
    start.add_argument(
        "issue_number",
        type=_positive_int,
        help="GitHub issue number",
    )

    return parser


def _positive_int(value: str) -> int:
    """Argparse type validator for positive integers."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid issue number '{value}': must be a positive integer"
        )
    if n <= 0:
        raise argparse.ArgumentTypeError(
            f"invalid issue number '{value}': must be a positive integer"
        )
    return n


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "improve":
        sys.exit(cmd_improve(args))
    elif args.command == "start":
        sys.exit(cmd_start(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
