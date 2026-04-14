# native_skills

Reusable, composable capabilities that agents can discover and attach at
runtime. Each skill is a self-contained Markdown file that describes **what**
the agent should do and **how** it should behave when the skill is active.

---

## Directory layout

```
agent/native_skills/
├── __init__.py          ← public API (list_skills, load_skill, get_skill_metadata, compose_skills)
├── README.md            ← this file
├── SKILL_TEMPLATE.md    ← copy this to create a new skill
├── code_review.md       ← built-in skill: structured code review
└── write_tests.md       ← built-in skill: write unit tests for code changes
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
| **Front-matter required** | Every skill must open with a YAML front-matter block containing `contract_version`, `name`, `version`, and `description`. See [`SKILL_CONTRACT.md`](../../SKILL_CONTRACT.md). |

---

## Public API

```python
from native_skills import list_skills, load_skill, get_skill_metadata, compose_skills

# 1. Discover all skills
for skill in list_skills():
    print(skill["name"])      # "write_tests"
    print(skill["filename"])  # "write_tests.md"
    print(skill["path"])      # "/absolute/path/to/write_tests.md"

# 2. Load a skill's full Markdown content
content = load_skill("write_tests")

# 3. Inspect a skill's front-matter metadata without loading the full body
meta = get_skill_metadata("write_tests")
# → {"contract_version": "1.0.0", "name": "write_tests", "version": "1.0.0", ...}

# 4. Super-power composition — stack multiple skills into one context blob
combined = compose_skills(["code_review", "write_tests"])
```

`list_skills()` returns skills sorted alphabetically. `load_skill(name)` and
`get_skill_metadata(name)` raise `FileNotFoundError` for unknown or reserved
names. `compose_skills(names)` raises `FileNotFoundError` on the first unknown
name encountered.

---

## How agents discover and consume skills

### Standard environments (direct filesystem access)

```python
from native_skills import list_skills, load_skill

skill_context = "\n\n".join(load_skill(s["name"]) for s in list_skills())
# Prepend skill_context to the agent's system prompt or task description.
```

### OpenHands / sandboxed environments

OpenHands agents run inside a sandbox where the agent process itself may not
have unrestricted filesystem access.  Two complementary paths are available:

1. **`AGENTS.md` (persistent memory)** — The repository-level `AGENTS.md`
   file is loaded automatically by the OpenHands SDK at the start of every
   conversation.  Reference or inline skill content there so the agent's
   context always includes it without runtime glob access.

2. **`context_files` in `RunRequest`** — When launching a run via the `/runs`
   API, include skill file paths in `spec.context_files`:

   ```python
   from native_skills import list_skills

   spec = IssueSpec(
       intent="...",
       acceptance_criteria=["..."],
       context_files=[s["path"] for s in list_skills()],
   )
   ```

   The agent reads those files as part of its working context before it
   begins the task.

---

## Super-power composition

Skills follow an **additive / stacking** model: each skill added to an agent's
context extends what the agent can do without modifying any other skill.

`compose_skills()` is the primary entry point for this pattern.  It joins
multiple skill files into a single Markdown document separated by horizontal
rules, producing one context blob that can be fed directly to any LLM or agent
runtime:

```python
from native_skills import compose_skills

# Give an agent both review and test-writing capabilities in one call.
super_power = compose_skills(["code_review", "write_tests"])
```

**Why this is powerful:**

- `code_review` alone teaches an agent to find bugs and surface risks.
- `write_tests` alone teaches an agent to produce test suites.
- `compose_skills(["code_review", "write_tests"])` produces an agent that
  reviews changes *and then* writes tests that specifically target the issues
  it found — a capability neither skill can achieve independently.

**Design rules for composable skills:**

| Rule | Rationale |
|------|-----------|
| Each skill is independent | No skill assumes another is present. |
| No conflict-resolution logic | If two skills overlap, both are available; the agent decides. |
| Additive only | A skill never modifies another skill's file. |
| Order is meaningful to the agent, not the API | `compose_skills` preserves list order, so put context-setting skills first. |

---

## Adding a new skill

1. Copy `SKILL_TEMPLATE.md` to `<your_skill_name>.md` in this directory.
2. Fill in the YAML front-matter (`contract_version`, `name`, `version`,
   `description`) and the required sections (`## Description`, `## Inputs`,
   `## Outputs`, `## Usage`).
3. Verify your skill appears in `list_skills()` and its metadata is readable:

   ```bash
   cd agent
   python -c "
   from native_skills import list_skills, get_skill_metadata
   print(list_skills())
   print(get_skill_metadata('<your_skill_name>'))
   "
   ```

4. Add unit tests in `agent/tests/test_native_skills.py` following the
   existing test patterns (see the `TestWriteTestsSkill` class for an example).
5. Open a PR — no other files need to be changed.

See [`SKILL_CONTRACT.md`](../../SKILL_CONTRACT.md) for the full specification
of required fields, sections, and validation rules.

---

## Coexistence with existing tooling

Native skills **do not replace** the OpenHands SDK tools (`FileEditorTool`,
`TerminalTool`, MCP servers, etc.) registered in `agent.py`. They are
supplementary textual capabilities — think of them as reusable prompt
fragments that shape agent behaviour for a specific task type, loaded
alongside the standard tool set.
