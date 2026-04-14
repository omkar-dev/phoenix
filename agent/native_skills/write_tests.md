---
contract_version: "1.0.0"
name: write_tests
version: "1.0.0"
description: "Given a set of code changes, write comprehensive unit tests that verify correct behaviour in isolation."
author: "Phoenix native skills maintainers"
tags: ["testing", "quality", "pytest", "unit-tests"]
since: "1.0.0"
---

# Skill: Write Tests

## Description

When applied, this skill directs the agent to analyse one or more changed
source files and produce a matching suite of unit tests. Tests must cover the
happy path, relevant edge cases, and expected error conditions. The agent
follows the project's existing test conventions (file layout, import style,
fixture patterns) so the new tests integrate without manual adjustment.

The skill targets Python projects using `pytest` and `pytest-asyncio`, which
is the test stack used in this repository, but its principles transfer to any
unit-testing framework.

## Inputs

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `changed_files` | `list[string]` | Yes | Relative paths to the source files that were added or modified. |
| `test_framework` | `string` | No | Testing framework to use. Defaults to `pytest`. |
| `coverage_targets` | `list[string]` | No | Specific functions or classes that must be tested. If omitted, the agent determines targets from `changed_files`. |
| `style_reference` | `string` | No | Relative path to an existing test file whose style the new tests should mirror. If omitted, the agent inspects `tests/` automatically. |

## Outputs

| Name | Type | Description |
| ---- | ---- | ----------- |
| `test_file` | `string` | Path of the created or updated test file (e.g. `agent/tests/test_<module>.py`). |
| `test_count` | `integer` | Number of test functions written. |
| `coverage_note` | `string` | Brief prose describing what is covered and any intentionally omitted cases. |

## Usage

```text
Apply the write_tests skill to the following changed files:
  - agent/native_skills/__init__.py

Framework: pytest
Style reference: agent/tests/test_models.py

Write unit tests that cover list_skills(), load_skill(), get_skill_metadata(),
and compose_skills(). Include tests for the FileNotFoundError cases and for
the reserved-name guard.
```

---

## Examples

### Input

```text
Changed files:
  - agent/db.py  (new function: delete_repo)

Write tests for the new delete_repo() function. Mirror the style of
agent/tests/test_db.py. Ensure the test verifies:
  1. A repo that exists is removed.
  2. Calling delete_repo() on a non-existent repo does not raise.
```

### Expected output

```python
# agent/tests/test_db.py  (additions)

async def test_delete_repo_removes_entry(tmp_db):
    await db.init_db()
    await db.upsert_repo("owner/repo")
    await db.delete_repo("owner/repo")
    assert await db.list_repos() == []


async def test_delete_repo_nonexistent_is_silent(tmp_db):
    await db.init_db()
    await db.delete_repo("owner/nonexistent")   # must not raise
```

---

## Limitations

- The skill produces `pytest`-style tests. Projects using `unittest`, `nose`,
  or another framework need the `test_framework` input set explicitly — the
  agent will adapt its output accordingly, but quality may vary for less common
  frameworks.
- Tests that require live network access, running databases, or third-party
  credentials are outside scope. The agent should write tests that work with
  `tmp_path`, monkeypatching, or in-process fakes instead.
- The skill cannot infer the correct test for code paths hidden behind
  dynamic dispatch or heavy metaprogramming without additional context.

## See Also

- [`code_review.md`](./code_review.md) — review the changes before writing tests
- [`SKILL_TEMPLATE.md`](./SKILL_TEMPLATE.md) — template for authoring new skills
- [`SKILL_CONTRACT.md`](../../SKILL_CONTRACT.md) — full contract specification
