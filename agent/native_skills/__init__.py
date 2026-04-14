"""
native_skills — reusable, composable agent capabilities.

Each skill is a single Markdown file (.md) in this directory.
The public API lets callers discover, inspect, load, and compose skills
without knowing the underlying file paths.

Usage::

    from native_skills import list_skills, load_skill, compose_skills, get_skill_metadata

    for skill in list_skills():
        print(skill["name"])   # e.g. "write_tests"

    content  = load_skill("write_tests")        # returns the Markdown text
    metadata = get_skill_metadata("write_tests") # returns parsed front-matter dict

    # Super-power composition: stack multiple skills into one context blob
    combined = compose_skills(["write_tests", "code_review"])
"""

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent

# Files that live in this directory but are not skills themselves.
_META_FILES = {"README.md", "SKILL_TEMPLATE.md"}

_COMPOSE_SEPARATOR = "\n\n---\n\n"


def list_skills() -> list[dict]:
    """Return metadata for every available skill, sorted alphabetically by name.

    Each entry is a dict with:
      - ``name``     (str) — the skill identifier (filename stem, no ``.md``)
      - ``filename`` (str) — the bare filename, e.g. ``write_tests.md``
      - ``path``     (str) — absolute path to the Markdown file
    """
    skills = []
    for path in sorted(_SKILLS_DIR.glob("*.md")):
        if path.name not in _META_FILES:
            skills.append(
                {
                    "name": path.stem,
                    "filename": path.name,
                    "path": str(path),
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


def get_skill_metadata(name: str) -> dict:
    """Return parsed front-matter fields for the skill identified by *name*.

    Reads the YAML front-matter block (the ``---``-delimited section at the
    top of the skill file) and returns its key/value pairs as a plain dict.
    Values are returned as strings; no type coercion is applied.

    Raises:
        FileNotFoundError: same conditions as :func:`load_skill`.
    """
    content = load_skill(name)  # propagates FileNotFoundError
    if not content.startswith("---"):
        return {}
    try:
        end = content.index("---", 3)
    except ValueError:
        return {}
    fm_text = content[3:end].strip()
    metadata: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            metadata[key.strip()] = val.strip().strip('"')
    return metadata


def compose_skills(names: list[str]) -> str:
    """Return the combined Markdown content of multiple skills, stacked additively.

    This is the **super-power composition** entry point: each skill adds its
    full capability description to the combined context.  When an agent receives
    the composed output it has access to all stacked skill instructions
    simultaneously — no ordering or dependency logic is applied.

    Skills are joined by a Markdown horizontal rule (``---``) so the combined
    document remains readable as plain Markdown.

    Args:
        names: Ordered list of skill name stems (without ``.md``).  Duplicates
            are allowed; the same skill will appear multiple times in the output.

    Returns:
        A single Markdown string containing all requested skills.

    Raises:
        FileNotFoundError: if any name in *names* is unknown or reserved.
            The error is raised immediately; no partial result is returned.
    """
    parts = [load_skill(name) for name in names]
    return _COMPOSE_SEPARATOR.join(parts)
