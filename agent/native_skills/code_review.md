---
contract_version: "1.0.0"
name: code_review
version: "1.0.0"
description: "Review a set of code changes for correctness, security, style, and maintainability, then produce a structured report."
author: "Phoenix native skills maintainers"
tags: ["code-review", "quality", "security", "maintainability"]
since: "1.0.0"
---

# Skill: Code Review

## Description

When applied, this skill directs the agent to perform a thorough code review
of the supplied diff or changed files. The review evaluates correctness (logic
errors, off-by-one errors, missing edge cases), security (injection risks,
credential exposure, insufficient validation), style (adherence to project
conventions and linting rules), and maintainability (readability, complexity,
test coverage). The output is a structured, actionable report.

This skill complements `write_tests` in the super-power composition pattern:
reviewing changes first surfaces issues that the test-writing step can then
directly target.

## Inputs

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `changed_files` | `list[string]` | Yes | Relative paths to the files to review. |
| `diff` | `string` | No | Raw unified diff. If provided, used in preference to reading files directly. |
| `focus_areas` | `list[string]` | No | Specific concerns to prioritise (e.g. `["security", "performance"]`). Defaults to all four categories. |
| `severity_threshold` | `string` | No | Minimum severity to include in the report: `low`, `medium`, or `high`. Defaults to `low` (all findings). |

## Outputs

| Name | Type | Description |
| ---- | ---- | ----------- |
| `summary` | `string` | One-paragraph overview of the changes and the overall review verdict. |
| `findings` | `list[object]` | Each finding has `severity` (`low`/`medium`/`high`), `category`, `file`, `line` (optional), and `message`. |
| `approved` | `boolean` | `true` if no `high`-severity findings exist and the changes are ready to merge. |

## Usage

```text
Apply the code_review skill to the following changed files:
  - agent/native_skills/__init__.py

Focus areas: correctness, security
Severity threshold: medium

Produce a structured review report. Flag any finding at medium severity or
above. Set approved=true only if no high-severity issues are found.
```

---

## Examples

### Input

```text
Changed files:
  - agent/routes/repos.py

Diff:
  --- a/agent/routes/repos.py
  +++ b/agent/routes/repos.py
  @@ -1,6 +1,9 @@
  +import subprocess
   import db as _db
   from fastapi import APIRouter, Query
  ...
  +    subprocess.run(body.full_name, shell=True)
```

### Expected output

```text
Summary: The change introduces a subprocess call using shell=True with user-
supplied input. This is a critical shell-injection vulnerability.

Findings:
  - severity: high
    category: security
    file: agent/routes/repos.py
    line: 9
    message: >
      subprocess.run() with shell=True and unsanitised user input allows
      arbitrary command execution. Remove the subprocess call or sanitise
      input and use shell=False with an explicit argument list.

approved: false
```

## Limitations

- The agent reviews only the files and diff provided. It cannot catch issues
  that arise from interactions with code not included in the input.
- Performance analysis is limited to obvious algorithmic concerns (e.g. O(n²)
  loops); profiling-level insights require runtime data.
- The `approved` flag reflects only the findings visible to the agent; it is
  not a substitute for CI checks or human review.

## See Also

- [`write_tests.md`](./write_tests.md) — write tests after the review identifies gaps
- [`SKILL_TEMPLATE.md`](./SKILL_TEMPLATE.md) — template for authoring new skills
- [`SKILL_CONTRACT.md`](../../SKILL_CONTRACT.md) — full contract specification
