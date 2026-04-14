# native_skills

Reusable, composable capabilities that agents can discover and attach at
runtime. Each skill is a self-contained Markdown file that describes **what**
the agent should do and **how** it should behave when the skill is active.

---

## Directory layout

```
agent/native_skills/
├── __init__.py          ← public API (list_skills, load_skill, attach_skills)
├── README.md            ← this file
├── SKILL_TEMPLATE.md    ← copy this to create a new skill
└── <skill_name>.md      ← one file per skill
```

The directory is intentionally **flat**: every skill lives directly here with
no sub-folders. Extensibility (namespacing, versioning, etc.) can be added
later without breaking the existing public API.

---

## Conventions

| Rule | Detail |
|------|--------|
| **One file per skill** | Each `.md` file is exactly one skill. |
| **Filename = skill name** | The file stem (without `.md`) is the identifier used in `load_skill()`. Use `snake_case`. |
| **Reserved filenames** | `README.md` and `SKILL_TEMPLATE.md` are excluded from enumeration; do not use these stems for real skills. |
| **Self-contained** | A skill file must be meaningful on its own — no imports, no external references. |
| **Markdown only** | No JSON, YAML, or other schema formats are required at this stage. |

---

## Public API

```python
from native_skills import list_skills, load_skill, attach_skills
```

### Discovery

```python
# list_skills() — scan the directory and return descriptors for every skill
for skill in list_skills():
    print(skill["name"])      # "write_tests"          — identifier / filename stem
    print(skill["filename"])  # "write_tests.md"       — bare filename
    print(skill["path"])      # "/abs/path/write_tests.md"  — absolute path
    print(skill["title"])     # "Write Tests"          — parsed from the # Skill: heading
```

`list_skills()` returns descriptors sorted alphabetically by name. Reserved files
(`README.md`, `SKILL_TEMPLATE.md`) are excluded automatically. The `title` field
is extracted from the first `# Skill: …` heading in each file; if no such heading
is present the filename stem is used as a fallback.

```python
# load_skill(name) — return the raw Markdown content of a single skill
content = load_skill("write_tests")
```

Raises `FileNotFoundError` for unknown or reserved names.

### Runtime attachment

```python
# attach_skills(*names) — load and stack one or more skills into a single string
```

`attach_skills()` is the primary way agents consume skills at runtime.  It reads
each requested skill file and concatenates the results with Markdown `---`
separators.  The returned string is ready to be injected directly into an agent's
system prompt.

**Single skill**

```python
system_prompt = attach_skills("write_tests")
```

**Multiple skills — additive stacking**

Skills are independent: they share no state and require no conflict-resolution
logic.  Pass as many names as needed in the order you want them applied:

```python
system_prompt = attach_skills("write_tests", "review_code")
```

The output is the two skill documents joined by `\n\n---\n\n`, preserving each
skill's own Markdown structure.

**Integration with `RunRequest`**

The `system_prompt` field on `RunRequest` is prepended to every task prompt
built by `ImplementerAgent._build_prompt()`.  Assign the output of
`attach_skills()` there to activate skills for a specific run:

```python
from native_skills import attach_skills, list_skills
from models import RunRequest, IssueSpec

req = RunRequest(
    issue_number=42,
    repo_full_name="owner/repo",
    spec=IssueSpec(
        intent="Add unit tests for the auth module",
        acceptance_criteria=["All new tests pass on CI"],
    ),
    system_prompt=attach_skills("write_tests"),
)
```

Stack several skills for a run that needs composite behaviour:

```python
req = RunRequest(
    issue_number=99,
    repo_full_name="owner/repo",
    spec=IssueSpec(intent="Refactor auth module", acceptance_criteria=["No regressions"]),
    system_prompt=attach_skills("write_tests", "review_code"),
)
```

**Sandbox compatibility**

`attach_skills()` is filesystem-only.  It makes no network calls, relies on no
installed entry points or `pkg_resources` metadata, and accesses no paths outside
the `native_skills/` package directory.  It works identically in unrestricted and
sandboxed/restricted execution environments.

---

## Adding a new skill

1. Copy `SKILL_TEMPLATE.md` to `<your_skill_name>.md` in this directory.
2. Fill in every section of the template (purpose, instructions, examples).
3. Verify it appears in `list_skills()`:

   ```python
   python -c "from native_skills import list_skills; print(list_skills())"
   ```

4. Open a PR — no other files need to be changed.

---

## Coexistence with existing tooling

Native skills **do not replace** the OpenHands SDK tools (`FileEditorTool`,
`TerminalTool`, MCP servers, etc.) registered in `agent.py`. They are
supplementary textual capabilities — think of them as reusable prompt
fragments that shape agent behaviour for a specific task type, loaded
alongside the standard tool set.

---

## Reference skill walkthrough: `summarize_issue`

`summarize_issue` is the canonical reference implementation.  Walk through it
end-to-end when learning the system or reviewing a new skill contribution.

### 1 — Discover the skill

```python
from native_skills import list_skills

for skill in list_skills():
    print(skill["name"], "—", skill["title"])
# code_review     — Code Review
# summarize_issue — Summarize Issue
# write_tests     — Write Tests
```

### 2 — Inspect the raw content

```python
from native_skills import load_skill

print(load_skill("summarize_issue"))
# Prints the full Markdown, including front-matter and all contract sections.
```

### 3 — Attach to a run (single skill)

```python
from native_skills import attach_skills
from models import RunRequest, IssueSpec

req = RunRequest(
    issue_number=7,
    repo_full_name="owner/repo",
    spec=IssueSpec(
        intent="Fix the dark-mode toggle causing a full page reload",
        acceptance_criteria=["Toggle switches theme without reload"],
    ),
    # attach_skills() returns the Markdown text ready to inject into the prompt.
    system_prompt=attach_skills("summarize_issue"),
)
```

The agent receives the skill text prepended to every task prompt via
`ImplementerAgent._build_prompt()`.  No other configuration is required.

### 4 — Stack multiple skills

Skills are independent and additive.  Pass several names to `attach_skills()`
in the order you want them applied:

```python
# Summarise the issue first, then generate tests for the acceptance criteria.
req = RunRequest(
    issue_number=7,
    repo_full_name="owner/repo",
    spec=IssueSpec(
        intent="Fix the dark-mode toggle causing a full page reload",
        acceptance_criteria=["Toggle switches theme without reload"],
    ),
    system_prompt=attach_skills("summarize_issue", "write_tests"),
)
```

### 5 — Sandbox compatibility

`attach_skills()` is filesystem-only: no network calls, no installed entry
points, no paths outside `native_skills/`.  In sandboxed OpenHands runs the
skill content reaches the agent through one of two complementary paths:

| Path | How |
|------|-----|
| **`AGENTS.md`** | Persistent memory loaded automatically at conversation start; `AGENTS.md` lists `summarize_issue` so the agent is always aware of it. |
| **`spec.context_files`** | Pass `"agent/native_skills/summarize_issue.md"` in `RunRequest.spec.context_files`; the agent reads it as part of its working context. |

Both paths deliver the same Markdown content — the agent can act on it
immediately without any adapter layer.
