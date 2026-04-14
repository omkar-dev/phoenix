# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## What is Phoenix?

Phoenix is an AI-powered GitHub Kanban board that assigns issues to AI agents (via OpenHands SDK + Claude) for automatic implementation. It has three services: a FastAPI backend agent, a semantic similarity microservice, and an Astro frontend.

## Commands

### Development
```bash
make install          # Install all dependencies (frontend + backend)
make dev              # Run all three services (agent:8001, semantic:3001, frontend:4321)
make dev-frontend     # Frontend only
make dev-backend      # Agent service only
make dev-semantic     # Semantic service only
```

### Testing
```bash
make test             # Run backend tests (frontend tests: make test-frontend)
cd agent && pytest    # Run backend tests
cd agent && pytest tests/test_file.py::test_name  # Run a single test
```

### Linting & Formatting
```bash
make lint             # Lint both Python and frontend
make lint-python      # ruff check agent/
make lint-frontend    # eslint . (via npm run lint)
make format-frontend  # prettier --write . (via npm run format)
make format-python    # ruff format agent/
make format-frontend  # prettier --write src/
make typecheck        # astro check (frontend types)
```

### Build
```bash
make build            # Astro production build
make clean            # Remove build artifacts
```

## Architecture

**Three-service design:**
- **Agent service** (`agent/app.py`, port 8001) — FastAPI app orchestrating AI agent runs, git worktrees, and GitHub PR creation
- **Semantic service** (`agent/semantic_server.py`, port 3001) — TF-IDF cosine similarity for issue deduplication (stdlib only, no ML dependencies)
- **Frontend** (`src/`, port 4321) — Astro 5 + Preact + TailwindCSS v4 single-page Kanban board

**Frontend lib/ vs scripts/ split** (see `src/ARCHITECTURE.md`):
- `src/lib/` — Pure business logic, no DOM access. Testable and importable.
- `src/scripts/` — DOM wiring, event handlers, UI initialization. Imports from `lib/`.
- `src/scripts/state.js` — Singleton shared mutable state (currentRepo, allIssues, columns, duplicates)
- Service URLs come from `src/lib/config.js` via `import.meta.env.PUBLIC_*` (set at build time)

**Backend structure:**
- `agent/agent.py` — Core `ImplementerAgent` class: OpenHands SDK integration, file intelligence, worktree-based git isolation, SSE event streaming
- `agent/routes/` — Thin FastAPI route handlers (runs, refine, worktree, repos, movements, notes)
- `agent/db.py` — Async SQLite (`~/.pnx/pnx.db`) via aiosqlite for repos, movements, run logs
- `agent/models.py` — Pydantic request/response models
- `agent/registry.py` — In-memory registry of active runs
- `agent/config.py` — Environment-based settings with per-repo async locks
- `agent/native_skills/` — Markdown-based skill definitions loaded by OpenHands SDK (see `SKILL_CONTRACT.md`).
  Reference skill: **`summarize_issue`** (`agent/native_skills/summarize_issue.md`) — distils an issue into
  a structured Problem / Goal / Acceptance-Criteria summary; attach via `attach_skills("summarize_issue")`.
  Other available skills: `code_review`, `write_tests`.

**Git workflow:** Per-repo base clone at `~/.pnx/repos/{owner}/{repo}`, per-issue worktree for isolation, automatic branch naming from issue number.

## Key Conventions

**Python (ruff enforced):** 88-char line length, double quotes, async/await throughout, parameterized SQL only, type hints on public functions.

**JavaScript:** ES modules only, `lib/` modules must not touch DOM, service URLs from `lib/config.js` (never hardcoded).

**Commits:** Conventional format (`feat:`, `fix:`, `docs:`, `chore:`).

## Environment Variables

Required: `GITHUB_TOKEN`, `ANTHROPIC_API_KEY` (or set per-agent in UI).
Optional: `LLM_MODEL` (default `anthropic/claude-sonnet-4-6`), `CORS_ORIGINS`, `PNX_REPOS_DIR`.
Frontend build-time: `PUBLIC_AGENT_URL` (default `http://localhost:8001`), `PUBLIC_SEMANTIC_URL` (default `http://localhost:3001`).

## CI

GitHub Actions runs on push/PR to main: ruff lint+format check, pytest (Python 3.12/3.13 matrix), ESLint, `astro check`, and `astro build` for frontend.
