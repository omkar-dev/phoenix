# Contributing a Native Skill

This guide explains how to add a new native skill to Phoenix — step by step,
from an empty file to a merged pull request. After reading it you will
understand the Markdown contract every skill must satisfy, how agents discover
and attach skills at runtime, and how to stack multiple skills additively for
composite agent behaviour.

> **Testing guidance** for native skills (unit tests, contract validation
> tooling, etc.) is intentionally out of scope here and will be addressed in a
> dedicated future issue. Open a PR without tests for now.

---

## Contents

1. [What a native skill is (and is not)](#1-what-a-native-skill-is-and-is-not)
2. [Step-by-step: creating a new skill](#2-step-by-step-creating-a-new-skill)
3. [Markdown front-matter reference](#3-markdown-front-matter-reference)
4. [Required sections reference](#4-required-sections-reference)
5. [Optional sections reference](#5-optional-sections-reference)
6. [How agents discover and attach skills](#6-how-agents-discover-and-attach-skills)
7. [Worked example: creating `label_issue` from scratch](#7-worked-example-creating-label_issue-from-scratch)
8. [Stacking multiple skills](#8-stacking-multiple-skills)
9. [Pre-merge checklist](#9-pre-merge-checklist)

---

## 1. What a native skill is (and is not)

A **native skill** is a single, self-contained Markdown file that describes one
capability an agent can perform: what it does, what it needs as input, and what
it produces as output. The Markdown file is the interface — no Python class,
JSON schema, or plugin registration is required.

### Skills coexist with existing tooling — they do not replace it

Native skills are supplementary **textual capabilities** (reusable prompt
fragments) that shape agent behaviour for a specific task type. They exist
alongside, and are loaded in addition to, the standard OpenHands SDK tools
already registered in `agent/agent.py` — `FileEditorTool`, `TerminalTool`, MCP
servers, and any other tools configured per run.

**A skill must not:**

- Wrap, shadow, or replace an existing SDK tool or plugin.
- Declare itself as the sole mechanism for something already covered by the
  standard tool set (e.g. file editing, terminal commands, GitHub API calls).
- Depend on another skill's presence in order to function correctly.

**A skill should:**

- Describe a reusable, task-specific behaviour that benefits from consistent
  prompt guidance across many runs.
- Operate purely from text context — it performs no I/O of its own; the agent
  uses its existing tools to act on the skill's guidance.

---

## 2. Step-by-step: creating a new skill

### Step 1 — copy the template

```bash
cp agent/native_skills/SKILL_TEMPLATE.md agent/native_skills/<your_skill_name>.md
```

Use `snake_case` for the filename. The stem (without `.md`) becomes the skill's
identifier in the public API.

```bash
# Good
agent/native_skills/label_issue.md
agent/native_skills/generate_changelog.md

# Bad — wrong case, wrong separator
agent/native_skills/LabelIssue.md
agent/native_skills/generate-changelog.md
```

### Step 2 — fill in the front-matter

Open the new file and update the YAML block at the very top:

```yaml
---
contract_version: "1.0.0"
name: label_issue          # must match the filename stem exactly
version: "1.0.0"
description: "Suggest one or more GitHub labels for an issue based on its title and body."
---
```

See [§ 3 Markdown front-matter reference](#3-markdown-front-matter-reference)
for the full field list.

### Step 3 — write the `## Description` section

Two to four sentences. Expand on the `description` front-matter field — add
motivation and nuance; do **not** repeat it verbatim.

```markdown
## Description

Read a GitHub issue title and body and recommend the most appropriate labels
from the repository's existing label set. The output is a ranked list of label
names with a one-sentence rationale for each suggestion. This skill helps
triage teams apply consistent labels without reading every issue manually, and
it works entirely from text — it performs no GitHub API calls.
```

### Step 4 — write the `## Inputs` section

A Markdown table with columns `Name`, `Type`, `Required`, and `Description`.
One row per input. If the skill takes no inputs write `_None._`.

```markdown
## Inputs

| Name        | Type        | Required | Description                                                |
| ----------- | ----------- | -------- | ---------------------------------------------------------- |
| `title`     | `string`    | Yes      | The issue title (one line).                                |
| `body`      | `string`    | Yes      | The full issue body (Markdown accepted).                   |
| `label_set` | `list[str]` | Yes      | Candidate labels available in the repository.              |
| `max_labels`| `integer`   | No       | Maximum number of labels to suggest (default: `3`).        |
```

### Step 5 — write the `## Outputs` section

A table with columns `Name`, `Type`, and `Description`. If the skill produces
no outputs write `_None._`.

```markdown
## Outputs

| Name          | Type        | Description                                               |
| ------------- | ----------- | --------------------------------------------------------- |
| `suggestions` | `list[str]` | Ordered list of label names, most confident first.        |
| `rationale`   | `string`    | One sentence per label explaining why it was chosen.      |
```

### Step 6 — write the `## Usage` section

Show the minimal, copy-paste-ready invocation. Use `{{ variable }}` placeholders
for dynamic values.

````markdown
## Usage

```text
Review the following GitHub issue and suggest up to {{ max_labels | default: 3 }}
labels from the candidate set below. Return the label names as a Markdown list,
most confident first, with one sentence of rationale per label.

Candidate labels:
{{ label_set | join: ", " }}

Issue title: {{ title }}

Issue body:
{{ body }}
```
````

### Step 7 — add optional sections (if useful)

After `## Usage` you may add any of:

- `## Examples` — concrete input/output pairs.
- `## Limitations` — known constraints or surprising behaviours.
- `## See Also` — relative links to related skill files.

Delete any optional section you do not need.

### Step 8 — verify the skill is discoverable

```bash
cd agent
python -c "from native_skills import list_skills; [print(s['name'], '-', s['title']) for s in list_skills()]"
```

Your new skill should appear in the alphabetically sorted list.

### Step 9 — open a pull request

No other files need to change. Open a PR with:

- **Title:** `feat(skills): add <skill_name> skill`
- **Description:** one paragraph explaining what the skill does and when to
  use it.

---

## 3. Markdown front-matter reference

The YAML front-matter block must be the very first thing in the file, delimited
by `---`.

### Required fields

| Field              | Type     | Description                                                                 |
| ------------------ | -------- | --------------------------------------------------------------------------- |
| `contract_version` | `string` | Version of the skill contract this file conforms to. Use `"1.0.0"`.        |
| `name`             | `string` | Machine-readable identifier — `snake_case`, unique within `native_skills/`. |
| `version`          | `string` | The skill's own semantic version. Start at `"1.0.0"`.                      |
| `description`      | `string` | One sentence summarising what the skill does.                               |

### Optional fields

| Field    | Type           | Description                                                              |
| -------- | -------------- | ------------------------------------------------------------------------ |
| `author` | `string`       | Team or individual responsible for maintaining this skill.               |
| `tags`   | `list[string]` | Searchable labels (e.g. `["triage", "github"]`).                        |
| `since`  | `string`       | First `contract_version` that introduced this skill (e.g. `"1.0.0"`).   |

### Minimal valid front-matter

```yaml
---
contract_version: "1.0.0"
name: my_skill
version: "1.0.0"
description: "Does one specific thing very well."
---
```

### Versioning

- **`contract_version`** — bump only when conforming to a new revision of
  `SKILL_CONTRACT.md` (maintained by the native skills module maintainers).
- **`version`** — bump yourself when you change the skill. Follow Semantic
  Versioning: major for breaking input/output changes, minor for backward-
  compatible additions, patch for documentation fixes.

See [SKILL_CONTRACT.md](SKILL_CONTRACT.md) for the authoritative specification.

---

## 4. Required sections reference

The four sections below must appear in every skill file, **in this order**,
each as an H2 heading (`##`).

### `## Description`

Prose explanation of what the skill does and why it exists. Two to four
sentences. Do not repeat the `description` front-matter field verbatim — add
context and motivation instead.

### `## Inputs`

Markdown table with columns `Name`, `Type`, `Required`, `Description`. One row
per input. Write `_None._` if the skill accepts no inputs.

### `## Outputs`

Markdown table with columns `Name`, `Type`, `Description`. One row per output.
Write `_None._` if the skill produces no outputs.

### `## Usage`

A code block (or prose) showing the minimal invocation. At minimum this must
demonstrate all required inputs. Use `{{ variable }}` placeholders for dynamic
values. The content here is what an agent actually reads when it activates the
skill, so write it as a direct instruction to the agent.

---

## 5. Optional sections reference

These sections may appear after `## Usage` in any order. Delete any that do not
apply to your skill.

| Section          | Purpose                                                                            |
| ---------------- | ---------------------------------------------------------------------------------- |
| `## Examples`    | Additional concrete invocations illustrating edge cases or common patterns.        |
| `## Limitations` | Known constraints, unsupported environments, or behaviours that may surprise users. |
| `## See Also`    | Relative links to related skill files or external documentation.                   |

---

## 6. How agents discover and attach skills

### Discovery — `list_skills()`

```python
from native_skills import list_skills

for skill in list_skills():
    print(skill["name"])      # "label_issue"
    print(skill["filename"])  # "label_issue.md"
    print(skill["path"])      # "/abs/path/to/label_issue.md"
    print(skill["title"])     # "Label Issue"
```

`list_skills()` scans `agent/native_skills/`, ignores `README.md` and
`SKILL_TEMPLATE.md`, and returns descriptors sorted alphabetically by name. The
`title` is extracted from the first `# Skill: …` heading in the file.

No registration step is needed — dropping a correctly named `.md` file into the
directory is sufficient for it to appear in `list_skills()`.

### Loading — `load_skill(name)`

```python
from native_skills import load_skill

content = load_skill("label_issue")   # returns the raw Markdown string
```

Raises `FileNotFoundError` for unknown or reserved names.

### Attaching — `attach_skills(*names)`

`attach_skills()` is the primary way agents consume skills at runtime. It loads
each requested skill file and concatenates the results with Markdown `---`
separators, returning a string ready to be injected into an agent's system
prompt.

```python
from native_skills import attach_skills

# Single skill
system_prompt = attach_skills("label_issue")

# Multiple skills — stacked additively (see § 8)
system_prompt = attach_skills("summarize_issue", "label_issue")
```

### Injecting into a run — `RunRequest.system_prompt`

The `system_prompt` field on `RunRequest` is prepended to every task prompt
built by `ImplementerAgent._build_prompt()`. Set it to the output of
`attach_skills()` to activate skills for a specific run:

```python
from native_skills import attach_skills
from models import RunRequest, IssueSpec

req = RunRequest(
    issue_number=42,
    repo_full_name="owner/repo",
    spec=IssueSpec(
        intent="Triage and label the backlog",
        acceptance_criteria=["Each issue has at least one label"],
    ),
    system_prompt=attach_skills("label_issue"),
)
```

### Discovery in sandboxed / OpenHands environments

`attach_skills()` is filesystem-only — no network calls, no installed entry
points, no paths outside `native_skills/`. In sandboxed OpenHands runs the
skill content reaches the agent through one of two complementary paths:

| Path | Mechanism |
| ---- | --------- |
| **`AGENTS.md`** | Loaded automatically at conversation start. Reference or inline skill names there so the agent is always aware of them. |
| **`spec.context_files`** | Pass `"agent/native_skills/label_issue.md"` in `RunRequest.spec.context_files`; the agent reads it as part of its working context. |

Both paths deliver the same Markdown content — no additional adapter is needed.

---

## 7. Worked example: creating `label_issue` from scratch

This section walks through the complete creation of
[`agent/native_skills/label_issue.md`](agent/native_skills/label_issue.md)
using [`agent/native_skills/summarize_issue.md`](agent/native_skills/summarize_issue.md)
as the reference model. Read `summarize_issue.md` first — it is the canonical
reference implementation and demonstrates every required section and inline
comment convention.

### 7.1 — Identify the gap

`summarize_issue` distils an issue into a structured Problem/Goal/Acceptance-
Criteria block. There is no existing skill that suggests which GitHub labels to
apply. Label suggestion:

- is a distinct, reusable behaviour useful across many repositories
- operates purely from text (no API calls required)
- has clear, testable inputs and outputs
- is independent of `summarize_issue` and can be used with or without it

This makes it a good candidate for a new skill.

### 7.2 — Copy the template

```bash
cp agent/native_skills/SKILL_TEMPLATE.md agent/native_skills/label_issue.md
```

### 7.3 — Write the front-matter

Following `summarize_issue` as a model, set all four required fields:

```yaml
---
contract_version: "1.0.0"
name: label_issue
version: "1.0.0"
description: "Suggest one or more GitHub labels for an issue based on its title and body."
---
```

The `name` field matches the filename stem. The `description` is a single
sentence — more detail goes in `## Description`.

### 7.4 — Add the `# Skill:` heading

```markdown
# Skill: Label Issue
```

`list_skills()` parses this heading to populate the `title` field in skill
descriptors. Without it, the title falls back to the filename stem.

### 7.5 — Write `## Description`

Model after `summarize_issue`'s Description: two to four sentences that add
context beyond the front-matter.

```markdown
## Description

Read a GitHub issue title and body and recommend the most appropriate labels
from the repository's existing label set. The output is a short, ranked list of
label names accompanied by a one-sentence rationale for each suggestion. This
skill helps triage teams apply consistent labels without reading every issue
manually, and it works entirely from text — it performs no GitHub API calls.
```

### 7.6 — Write `## Inputs`

`summarize_issue` takes `title`, `body`, and an optional `max_points`. Mirror
that pattern: required inputs first, optional inputs second.

```markdown
## Inputs

| Name         | Type        | Required | Description                                                 |
| ------------ | ----------- | -------- | ----------------------------------------------------------- |
| `title`      | `string`    | Yes      | The issue title (one line).                                 |
| `body`       | `string`    | Yes      | The full issue body (Markdown accepted).                    |
| `label_set`  | `list[str]` | Yes      | Candidate labels available in the repository.               |
| `max_labels` | `integer`   | No       | Maximum number of labels to suggest (default: `3`).         |
```

### 7.7 — Write `## Outputs`

```markdown
## Outputs

| Name          | Type        | Description                                               |
| ------------- | ----------- | --------------------------------------------------------- |
| `suggestions` | `list[str]` | Ordered list of label names, most confident first.        |
| `rationale`   | `string`    | One sentence per label explaining why it was chosen.      |
```

### 7.8 — Write `## Usage`

The Usage block is what the agent actually reads. Write it as a direct
instruction — the same style used in `summarize_issue`'s Usage block.

````markdown
## Usage

```text
Review the following GitHub issue and suggest up to {{ max_labels | default: 3 }}
labels from the candidate set below. Return the label names as a Markdown list,
most confident first, with one sentence of rationale per label.

Candidate labels:
{{ label_set | join: ", " }}

Issue title:
{{ title }}

Issue body:
{{ body }}
```
````

### 7.9 — Add optional sections

Following `summarize_issue`, add `## Examples`, `## Limitations`, and
`## See Also`.

```markdown
## Examples

### Input

\```text
Candidate labels: bug, enhancement, documentation, good first issue, performance

Title: Dark-mode toggle on the Settings page causes the page to reload

Body:
When a user clicks the dark-mode toggle on the Settings page, the entire
page reloads instead of switching themes in place.
\```

### Expected output

\```markdown
- **bug** — the toggle triggers an unintended full page reload.
- **good first issue** — the fix is localised to one UI event handler.
\```

## Limitations

- Only considers labels you supply in `label_set`; will not invent new labels.
- Accuracy degrades for very short issue bodies (fewer than two sentences).
- Does not apply labels — only suggests them.

## See Also

- [summarize_issue.md](summarize_issue.md) — pair with issue summarisation for richer triage.
- [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md) — blank template for authoring new skills.
- [SKILL_CONTRACT.md](../../SKILL_CONTRACT.md) — full contract specification.
```

### 7.10 — Verify discovery

```bash
cd agent
python -c "
from native_skills import list_skills, load_skill, attach_skills
# Confirm it appears in the registry
skills = {s['name']: s['title'] for s in list_skills()}
print(skills)
# Confirm raw content loads
content = load_skill('label_issue')
assert '## Inputs' in content
# Confirm attach_skills works
prompt = attach_skills('label_issue')
assert 'Label Issue' in prompt
print('All checks passed.')
"
```

Expected output:

```
{'code_review': 'Code Review', 'label_issue': 'Label Issue', 'summarize_issue': 'Summarize Issue', 'write_tests': 'Write Tests'}
All checks passed.
```

The finished file is committed at
[`agent/native_skills/label_issue.md`](agent/native_skills/label_issue.md).

---

## 8. Stacking multiple skills

Skills are **independent and additive**. Pass any number of skill names to
`attach_skills()` in the order you want them applied. Each skill's Markdown is
concatenated, separated by `---`, into a single string. No conflict-resolution
logic is needed — the agent receives all skill guidance simultaneously and
applies whichever is relevant to the current task.

### Why stacking works without coordination

Each skill file is self-contained: it makes no assumption about the presence or
absence of other skills. Adding skill B to an agent that already has skill A
requires no changes to either file. The composition is purely mechanical —
string concatenation — so there is nothing to break.

### Concrete example: two skills attached simultaneously

The following run first summarises an issue (via `summarize_issue`), then
suggests labels for it (via `label_issue`):

```python
from native_skills import attach_skills
from models import RunRequest, IssueSpec

req = RunRequest(
    issue_number=17,
    repo_full_name="owner/repo",
    spec=IssueSpec(
        intent="Triage the dark-mode toggle regression",
        acceptance_criteria=[
            "Issue has a structured summary",
            "At least one label is suggested",
        ],
    ),
    # Both skills are active for this run.
    # summarize_issue runs first (left-to-right order), label_issue second.
    system_prompt=attach_skills("summarize_issue", "label_issue"),
)
```

The value of `req.system_prompt` is the two skill documents joined by
`\n\n---\n\n`:

```
---
contract_version: "1.0.0"
name: summarize_issue
...
---

# Skill: Summarize Issue

## Description
...

---

---
contract_version: "1.0.0"
name: label_issue
...
---

# Skill: Label Issue

## Description
...
```

Both skill prompts are injected into the agent's context before every task
prompt. The agent sees both sets of instructions at once and applies them to the
same issue without any pipeline coordination.

### Stacking three or more skills

```python
# Summarise → label → generate tests for the acceptance criteria
system_prompt = attach_skills("summarize_issue", "label_issue", "write_tests")
```

Pass names in the conceptual order you want the agent to think about them.
Ordering rarely matters in practice because the agent processes all skill
contexts holistically, but consistent ordering makes code easier to read.

### When not to stack

Do not stack a skill with itself (e.g. `attach_skills("label_issue", "label_issue")`):
`load_skill()` will succeed but the duplicated instructions waste context tokens
without adding value. If two skills substantially overlap in responsibility,
consider whether one should be refactored before stacking them.

---

## 9. Pre-merge checklist

Before opening a PR, verify every item below:

- [ ] Filename is `snake_case` and ends in `.md`.
- [ ] Front-matter block is present, delimited by `---`, and appears first.
- [ ] All four required front-matter fields are set: `contract_version`, `name`,
      `version`, `description`.
- [ ] `name` matches the filename stem exactly.
- [ ] `# Skill: <Title>` heading is present immediately after the front-matter.
- [ ] All four required sections exist in order: `## Description`, `## Inputs`,
      `## Outputs`, `## Usage`.
- [ ] `## Inputs` and `## Outputs` each contain a populated table or `_None._`.
- [ ] `## Usage` contains at least one concrete example.
- [ ] All placeholder comments from the template have been removed.
- [ ] The skill appears in `list_skills()` (run the verification command in § 7.10).
- [ ] The skill does **not** wrap, shadow, or replace an existing SDK tool.
- [ ] `load_skill("<name>")` returns the file content without error.
- [ ] `attach_skills("<name>")` returns a non-empty string without error.
