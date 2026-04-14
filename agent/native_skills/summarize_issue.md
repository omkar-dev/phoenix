---
contract_version: "1.0.0"
name: summarize_issue
version: "1.0.0"
description: "Distil a GitHub issue into a concise structured summary an agent can act on immediately."
tags: ["reference", "summarization", "issue-management"]
---

# Skill: Summarize Issue

<!-- ────────────────────────────────────────────────────────────────────────
  CONTRIBUTOR GUIDE — every section comment below is intentional.

  This file is the canonical reference implementation of the skill contract
  defined in SKILL_CONTRACT.md.  It demonstrates every required section, the
  recommended style, and the inline-comment conventions that help reviewers
  understand each piece.

  Checklist before submitting a new skill:
    1.  Front-matter: contract_version, name (snake_case), version, description.
    2.  Required body sections in order: Description → Inputs → Outputs → Usage.
    3.  Optional sections (Examples, Limitations, See Also) appear after Usage.
    4.  Replace or remove ALL placeholder comments.
    5.  Run: python -c "from native_skills import list_skills; print(list_skills())"
        and confirm the skill appears.
──────────────────────────────────────────────────────────────────────────── -->

## Description

<!-- Two–four sentences.  Expand on the front-matter description field —
     add motivation and nuance; do NOT just repeat it verbatim. -->

Read an issue title and body and produce a short, structured summary that
highlights the problem being solved, the goal, and the concrete acceptance
criteria.  The output is designed to be prepended to an implementation task so
the agent always has a crisp statement of intent — regardless of how verbose or
ambiguous the original issue text is.  Because the skill performs no I/O it
works identically whether the agent runs in an unrestricted environment or
inside a sandboxed container.

## Inputs

<!-- A table with columns Name | Type | Required | Description.
     One row per parameter.  Use _None._ if there are no inputs. -->

| Name         | Type      | Required | Description                                                                 |
| ------------ | --------- | -------- | --------------------------------------------------------------------------- |
| `title`      | `string`  | Yes      | The issue title (one line).                                                 |
| `body`       | `string`  | Yes      | The full issue body (Markdown accepted).                                    |
| `max_points` | `integer` | No       | Maximum bullet points per section (default: `5`).  Use `0` for no limit.   |

## Outputs

<!-- A table with columns Name | Type | Description.
     One row per output value.  Use _None._ if there are no outputs. -->

| Name      | Type     | Description                                                                     |
| --------- | -------- | ------------------------------------------------------------------------------- |
| `summary` | `string` | Structured Markdown with **Problem**, **Goal**, and **Acceptance Criteria** sections. |

## Usage

<!-- Minimal, copy-paste-ready invocation.  Show the required inputs.
     Use {{ variable }} placeholders for dynamic values. -->

```text
Summarize the following GitHub issue.  Return a structured Markdown block with
exactly three H3 sections — ### Problem, ### Goal, ### Acceptance Criteria —
each containing at most {{ max_points | default: 5 }} bullet points.
Do not include any text outside these three sections.

### Issue title
{{ title }}

### Issue body
{{ body }}
```

---

## Examples

<!-- At least one realistic input + expected-output pair.  More is better. -->

### Input

```text
Title: Dark-mode toggle on the Settings page causes the page to reload

Body:
When a user clicks the dark-mode toggle on the Settings page, the entire page
reloads instead of switching themes in place.  This is jarring and loses any
unsaved form state.

Acceptance criteria:
- Toggling dark mode must not trigger a full page reload.
- The selected theme must persist across page refreshes (localStorage).
- The toggle must be accessible (keyboard + screen reader).
```

### Expected output

```markdown
### Problem
- Clicking the dark-mode toggle triggers a full page reload.
- The reload discards unsaved form state on the Settings page.

### Goal
- Switch themes in-place without a page reload.
- Persist the selected theme in `localStorage`.

### Acceptance Criteria
- Toggle does not reload the page.
- Theme persists after a manual browser refresh.
- Toggle is keyboard-navigable and screen-reader accessible.
```

---

## Limitations

<!-- Known constraints an agent or user should be aware of. -->

- The skill summarises text only; it does not fetch, validate, or modify any
  issue data in GitHub.
- For very long bodies (> 2 000 words), instruct the agent to focus on the
  first "Acceptance Criteria" or "Requirements" section if one is present.
- Output quality depends on the clarity of the original issue.  Poorly written
  issues may produce summaries that omit important context.

## See Also

<!-- Relative links to related skills or external docs. -->

- [write_tests.md](write_tests.md) — once the issue is summarised, generate
  tests from the acceptance criteria.
- [code_review.md](code_review.md) — pair with code review after implementation.
- [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md) — blank template for new skills.
- [SKILL_CONTRACT.md](../../SKILL_CONTRACT.md) — full contract specification.
