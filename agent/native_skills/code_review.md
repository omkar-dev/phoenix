---
contract_version: "1.0.0"
name: code_review
version: "1.0.0"
description: "Review code changes for correctness, style, and maintainability."
---

# Skill: Code Review

## Description

Examine diffs and source files to surface bugs, style violations, security
concerns, and opportunities for improvement. Focus on the most impactful
issues rather than exhaustive nitpicking. Every comment must explain *why*
the issue matters and, where possible, suggest a concrete fix.

## Inputs

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| diff | string | Yes | The unified diff or set of changed files to review |
| context_files | list[str] | No | Additional source files that provide context for the changes |
| checklist | list[str] | No | Extra criteria to evaluate (e.g. "check for SQL injection") |

## Outputs

| Name | Type | Description |
| ---- | ---- | ----------- |
| review_comments | list[str] | Ordered list of findings, each prefixed with a severity tag |
| summary | string | One-paragraph overview of the overall quality and key risks |

## Usage

```text
Review the following diff for correctness, security issues, and adherence to
project conventions. For each finding include: file name, line number (if
applicable), severity (CRITICAL / WARNING / SUGGESTION), a description of the
problem, and a recommended fix.

<diff>
{{ diff }}
</diff>
```

---

## Examples

### Input

```text
Review this diff for a Python FastAPI route handler that stores user input
directly in a SQLite query string.
```

### Expected output

```text
CRITICAL — app/routes/users.py:14
Raw user input is interpolated directly into the SQL query string, enabling
SQL injection. Replace with a parameterised query:

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

## Limitations

- Cannot execute the code, run tests, or verify that suggested fixes compile.
- Effectiveness degrades for very large diffs (> 500 changed lines); consider
  splitting the review into focused chunks.
- Language-specific style rules should be provided via `checklist` when they
  differ from common conventions.

## See Also

- [write_tests.md](write_tests.md) — pair code review with test generation for
  comprehensive quality assurance
- [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md) — template for authoring new skills
