# Phoenix — Repository Knowledge

## Architecture

- **Frontend**: Astro + Preact islands (`src/components/islands/*.tsx`), vanilla JS scripts (`src/scripts/`), shared libs (`src/lib/`)
- **Backend**: FastAPI server (`agent/`) with SQLite persistence, git worktrees per issue, OpenHands SDK for AI agents

## Key Patterns

### Storage
- All user preferences and config are stored in `localStorage` via helpers in `src/lib/agents.js`
- Storage key convention: `pnx_<feature_name>` (e.g. `pnx_agents`, `pnx_nix_scripts`)
- Per-repo data uses an object keyed by `repoFullName`

### "Open in Editor" / "Open Code" Workflow
- `DetailsTab` in `IssueDrawer.tsx` contains `handleOpenEditor()`
- If a worktree already exists (`run.worktreePath`), calls `POST /open-editor`
- Otherwise, calls `POST /worktree` which: clones/fetches repo, creates git worktree, runs any `nix_scripts`, then launches the editor
- Nix environment: if `shell.nix` or `default.nix` exists in the worktree, scripts run via `nix-shell --run`; otherwise via `sh -c`

### Nix Scripts Feature (added)
- **Model**: `WorktreeRequest.nix_scripts: list[str]` in `agent/models.py`
- **Backend execution**: `agent/routes/worktree.py` — scripts run sequentially after worktree setup, HTTP 500 with detailed message on failure
- **Storage**: `getNixScripts/saveNixScript/removeNixScript` in `src/lib/agents.js`, keyed by `repoFullName`
- **UI**: `NixScriptsEditor` component in `IssueDrawer.tsx`, rendered in `DetailsTab` above the action buttons
- **Error display**: `openEditorError` state in `DetailsTab`, shown as a dismissible red banner below the action buttons

### Backend Models
- `WorktreeRequest` — for creating worktrees (`/worktree`)
- `OpenEditorRequest` — for opening a path in editor (`/open-editor`)
- `RunRequest` — for creating agent runs (`/runs`)

### Frontend Signals
- Preact signals in `src/lib/signals.js` bridge vanilla JS ↔ island state
- `drawerSignal` controls the IssueDrawer; `runsSignal`, `logsSignal`, `suggestionsSignal` for run state

## Dev Notes
- ESLint config ignores `.tsx` files when run standalone (they're linted via the Astro plugin)
- `astro check` requires `@astrojs/check` and `typescript` packages
- Python syntax validation: `python3 -c "import ast; ast.parse(open('file.py').read())"`
