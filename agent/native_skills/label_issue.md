---
contract_version: "1.0.0"
name: label_issue
version: "1.0.0"
description: "Suggest one or more GitHub labels for an issue based on its title and body."
---

# Skill: Label Issue

## Description

Read a GitHub issue title and body and recommend the most appropriate labels
from the repository's existing label set. The output is a short, ranked list of
label names accompanied by a one-sentence rationale for each suggestion. This
skill helps triage teams apply consistent labels without reading every issue
manually, and it works entirely from text — it performs no GitHub API calls.

## Inputs

| Name           | Type        | Required | Description                                                                      |
| -------------- | ----------- | -------- | -------------------------------------------------------------------------------- |
| `title`        | `string`    | Yes      | The issue title (one line).                                                      |
| `body`         | `string`    | Yes      | The full issue body (Markdown accepted).                                         |
| `label_set`    | `list[str]` | Yes      | The candidate labels available in the repository (e.g. `["bug", "enhancement"]`). |
| `max_labels`   | `integer`   | No       | Maximum number of labels to suggest (default: `3`).                             |

## Outputs

| Name          | Type        | Description                                                                                   |
| ------------- | ----------- | --------------------------------------------------------------------------------------------- |
| `suggestions` | `list[str]` | Ordered list of recommended label names, most confident first.                                |
| `rationale`   | `string`    | Brief explanation (one sentence per label) of why each label was chosen.                      |

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

---

## Examples

### Input

```text
Candidate labels: bug, enhancement, documentation, good first issue, performance

Title: Dark-mode toggle on the Settings page causes the page to reload

Body:
When a user clicks the dark-mode toggle on the Settings page, the entire
page reloads instead of switching themes in place. This is jarring and
loses any unsaved form state. Expected behaviour: toggle switches theme
without a reload.
```

### Expected output

```markdown
- **bug** — the toggle triggers an unintended full page reload, which is a
  defect in the existing behaviour.
- **good first issue** — the fix is localised to one UI event handler and
  requires no backend changes, making it accessible to new contributors.
```

## Limitations

- The skill only considers the `label_set` you supply; it will not invent
  labels outside that list.
- Accuracy degrades if the issue body is very short (fewer than two sentences)
  or if the `label_set` contains ambiguous or overlapping labels.
- The skill does not apply labels — it only suggests them. A human or
  automation layer must make the actual GitHub API call.

## See Also

- [summarize_issue.md](summarize_issue.md) — distil the issue into a structured
  summary before or after labelling to create a richer triage record.
- [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md) — blank template for authoring new skills.
- [SKILL_CONTRACT.md](../../SKILL_CONTRACT.md) — full contract specification.
