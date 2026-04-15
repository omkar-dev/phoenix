#!/usr/bin/env python3
"""Validate native skill Markdown files against the SKILL_CONTRACT.md interface.

Checks every .md file in agent/native_skills/ (excluding meta files) for:
  - A valid YAML front-matter block with required fields
  - Required H2 sections in the correct order
  - Non-empty content under ## Inputs, ## Outputs, and ## Usage

Usage:
    python scripts/validate_skills.py

Exit codes:
    0  All skill files are valid.
    1  One or more skill files have validation errors.
"""

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SKILLS_DIR = Path(__file__).parent.parent / "agent" / "native_skills"

# Files that live in the skills directory but are not skills.
META_FILES = {"README.md", "SKILL_TEMPLATE.md"}

# Front-matter fields that every skill must define and that must be non-empty.
REQUIRED_FM_KEYS = ["contract_version", "name", "version", "description"]

# H2 sections that must appear in every skill file, in this exact order.
REQUIRED_SECTIONS = ["Description", "Inputs", "Outputs", "Usage"]

# Sections whose body must contain either a Markdown table row or "_None._".
TABLE_OR_NONE_SECTIONS = {"Inputs", "Outputs"}

# snake_case pattern: starts with a lowercase letter, then lowercase letters,
# digits, or underscores only.
_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Return (fields, body) where body is everything after the front-matter.

    Expects the file to begin with ``---``.  A missing or malformed
    front-matter block returns an empty dict and the full content as body.
    """
    if not content.startswith("---"):
        return {}, content

    lines = content.splitlines()
    closing = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = i
            break

    if closing == -1:
        return {}, content

    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip().strip('"').strip("'")

    body = "\n".join(lines[closing + 1 :])
    return fields, body


def _get_h2_sections(body: str) -> list[str]:
    """Return H2 heading names in the order they appear (ignores code blocks)."""
    sections = []
    in_fence = False
    for line in body.splitlines():
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            sections.append(line[3:].strip())
    return sections


def _section_body(body: str, section: str) -> str:
    """Return the text between ``## section`` and the next ``##`` heading."""
    inside = False
    in_fence = False
    collected: list[str] = []
    for line in body.splitlines():
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            if inside:
                break
            if line[3:].strip() == section:
                inside = True
                continue
        if inside:
            collected.append(line)
    return "\n".join(collected)


def _has_table_or_none(section_body: str) -> bool:
    """Return True if the section contains a Markdown table row or ``_None._``."""
    for line in section_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            # Skip pure separator rows (e.g. | --- | --- |)
            inner = stripped.strip("|")
            if any(cell.strip().replace("-", "").replace(":", "") for cell in inner.split("|")):
                return True
        if "_None._" in stripped or "_none._" in stripped.lower():
            return True
    return False


def _has_content(section_body: str) -> bool:
    """Return True if the section has at least one non-empty, non-comment line."""
    in_comment = False
    for line in section_body.splitlines():
        stripped = line.strip()
        if not in_comment and stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped:
            return True
    return False


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_skill(path: Path) -> list[str]:
    """Validate a single skill file.  Returns a list of error strings."""
    errors: list[str] = []
    rel = path.relative_to(SKILLS_DIR.parent.parent)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{rel}: cannot read file: {exc}"]

    # ── Front-matter ──────────────────────────────────────────────────────
    if not content.startswith("---"):
        errors.append(f"{rel}: missing YAML front-matter block (file must start with ---)")
        return errors  # can't validate further without front-matter

    fields, body = _parse_frontmatter(content)

    if not fields:
        errors.append(f"{rel}: front-matter block is present but could not be parsed")

    for key in REQUIRED_FM_KEYS:
        val = fields.get(key, "")
        if not val:
            errors.append(f"{rel}: front-matter missing required field '{key}'")

    # Validate name is snake_case
    name = fields.get("name", "")
    if name and not _SNAKE_CASE_RE.match(name):
        errors.append(
            f"{rel}: front-matter 'name' value {name!r} is not snake_case "
            "(must start with a lowercase letter and contain only lowercase letters, digits, and underscores)"
        )

    # Validate name matches filename stem
    if name and name != path.stem:
        errors.append(
            f"{rel}: front-matter 'name' ({name!r}) does not match filename stem ({path.stem!r})"
        )

    # ── Required sections ─────────────────────────────────────────────────
    present_sections = _get_h2_sections(body)

    for section in REQUIRED_SECTIONS:
        if section not in present_sections:
            errors.append(f"{rel}: missing required section '## {section}'")

    # Check ordering only when all required sections are present.
    if all(s in present_sections for s in REQUIRED_SECTIONS):
        required_positions = [present_sections.index(s) for s in REQUIRED_SECTIONS]
        if required_positions != sorted(required_positions):
            errors.append(
                f"{rel}: required sections are out of order; "
                f"expected Description → Inputs → Outputs → Usage, "
                f"found order: {[s for s in present_sections if s in REQUIRED_SECTIONS]}"
            )

    # ── Section content ───────────────────────────────────────────────────
    for section in TABLE_OR_NONE_SECTIONS:
        if section in present_sections:
            sbody = _section_body(body, section)
            if not _has_table_or_none(sbody):
                errors.append(
                    f"{rel}: '## {section}' must contain a Markdown table or '_None._' "
                    "(the skill accepts/produces nothing)"
                )

    if "Usage" in present_sections:
        ubody = _section_body(body, "Usage")
        if not _has_content(ubody):
            errors.append(f"{rel}: '## Usage' section is empty; add at least one invocation example")

    return errors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    skill_files = sorted(
        p for p in SKILLS_DIR.glob("*.md") if p.name not in META_FILES
    )

    if not skill_files:
        print(f"ERROR: no skill files found in {SKILLS_DIR}", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    failed = 0
    for path in skill_files:
        file_errors = validate_skill(path)
        for err in file_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        if file_errors:
            failed += 1
        all_errors.extend(file_errors)

    total = len(skill_files)
    passed = total - failed

    if all_errors:
        print(
            f"\nSkill validation failed: {len(all_errors)} error(s) across "
            f"{failed}/{total} file(s).",
            file=sys.stderr,
        )
        return 1

    print(f"Skill validation passed: {passed}/{total} file(s) OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
