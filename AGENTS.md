# Repository Knowledge

## Architecture
- **Frontend**: Astro + Preact islands (`src/`), with vanilla JS scripts in `src/scripts/` and library code in `src/lib/`
- **Backend**: FastAPI agent server (`agent/`) on port 8001, semantic server on port 3001
- **State**: Client-side localStorage for user preferences; SQLite (`~/.pnx/pnx.db`) for server-side persistence

## Key Patterns
- **Settings persistence**: `src/lib/agents.js` exports getter/setter pairs (e.g. `getCodeEditor`/`setCodeEditor`) that wrap `localStorage`
- **Constants**: `src/lib/constants.js` defines arrays/objects for UI options (editors, providers, columns)
- **Settings UI**: `src/components/SettingsPanel.astro` — init functions wired in `open-settings-panel` event handler
- **Open in editor**: All call sites use `getCodeEditor().cmd` — modifying `getCodeEditor()` propagates everywhere (drawer.js, board.js, IssueDrawer.tsx)
- **Backend editor endpoints**: `/worktree` creates a git worktree and opens editor; `/open-editor` opens an existing path — both accept `cmd` parameter

## Code Editor Settings
- Predefined editors in `CODE_EDITORS` constant + custom option
- Custom editor command stored in `pnx_custom_editor_cmd` localStorage key
- `getCodeEditor()` returns `{ id, name, cmd, icon }` — for custom, `cmd` comes from localStorage with 'code' fallback
