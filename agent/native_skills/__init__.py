"""
native_skills — reusable, composable agent capabilities.

Each skill is a single Markdown file (.md) in this directory.
The public API lets callers discover and load skills without knowing
the underlying file paths.

Usage::

    from native_skills import list_skills, load_skill, attach_skills

    for skill in list_skills():
        print(skill["name"])   # e.g. "write_tests"
        print(skill["title"])  # e.g. "Write Tests"

    content = load_skill("write_tests")   # returns the Markdown text

    # Attach one or more skills for injection into an agent's system prompt
    prompt_fragment = attach_skills("write_tests")
    prompt_fragment = attach_skills("write_tests", "review_code")  # stacked
"""

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent

# Files that live in this directory but are not skills themselves.
_META_FILES = {"README.md", "SKILL_TEMPLATE.md"}


def _parse_title(path: Path) -> str:
    """Extract the human-readable title from the first heading in a skill file.

    Recognises ``# Skill: <title>`` (canonical form from the template) and
    plain ``# <title>`` headings as a fallback.  Returns the filename stem if
    no heading is found or the file cannot be read.
    """
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# Skill:"):
                return stripped[len("# Skill:"):].strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except OSError:
        pass
    return path.stem


def list_skills() -> list[dict]:
    """Return metadata for every available skill, sorted alphabetically by name.

    Each entry is a dict with:
      - ``name``     (str) — the skill identifier (filename stem, no ``.md``)
      - ``filename`` (str) — the bare filename, e.g. ``write_tests.md``
      - ``path``     (str) — absolute path to the Markdown file
      - ``title``    (str) — human-readable title parsed from the Markdown heading
    """
    skills = []
    for path in sorted(_SKILLS_DIR.glob("*.md")):
        if path.name not in _META_FILES:
            skills.append(
                {
                    "name": path.stem,
                    "filename": path.name,
                    "path": str(path),
                    "title": _parse_title(path),
                }
            )
    return skills


def load_skill(name: str) -> str:
    """Return the Markdown content of a skill identified by *name* (the stem, without ``.md``).

    Raises:
        FileNotFoundError: if no skill with that name exists, or if *name*
            matches a reserved meta-file (``README``, ``SKILL_TEMPLATE``).
    """
    candidate = _SKILLS_DIR / f"{name}.md"
    if candidate.name in _META_FILES or not candidate.exists():
        raise FileNotFoundError(f"Skill {name!r} not found in {_SKILLS_DIR}")
    return candidate.read_text(encoding="utf-8")


def attach_skills(*names: str) -> str:
    """Load one or more skills and combine them into a single string.

    Skills are concatenated in the order given, separated by a Markdown
    horizontal rule (``---``).  The result is ready to be prepended to an
    agent's system prompt or task description.

    Stacking is purely additive — skills are independent and share no state,
    so any number can be combined without conflict-resolution logic.

    The implementation is filesystem-only: no network calls, no installed
    entry points, and no paths outside this package directory are accessed.
    It therefore works identically in unrestricted and sandboxed environments.

    Args:
        *names: One or more skill identifiers (filename stems without ``.md``).

    Returns:
        A Markdown string containing every requested skill's content, separated
        by ``---`` rules.  When a single skill is requested the output is just
        that skill's raw Markdown with no extra wrapper.

    Raises:
        FileNotFoundError: if any requested skill name does not exist or is
            reserved (``README``, ``SKILL_TEMPLATE``).

    Examples::

        # Single skill
        system_prompt = attach_skills("write_tests")

        # Multiple skills stacked additively
        system_prompt = attach_skills("write_tests", "review_code")

        # Inject into a RunRequest system_prompt field
        from models import RunRequest, IssueSpec
        req = RunRequest(
            issue_number=42,
            repo_full_name="owner/repo",
            spec=IssueSpec(intent="Add unit tests", acceptance_criteria=["Tests pass"]),
            system_prompt=attach_skills("write_tests"),
        )
    """
    parts = [load_skill(name).strip() for name in names]
    return "\n\n---\n\n".join(parts)
