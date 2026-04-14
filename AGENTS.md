# Phoenix Repository Notes

## Frontend Architecture

Single-page Astro app at `src/pages/index.astro`. All frontend logic lives in `src/`.

### Navigation / Router

`src/scripts/router.js` — Hash-based SPA router using the browser History API.

- `navigate(view)` — close all panels, push `history.pushState({ view })`, open panel.
- `initRouter()` — seed history state from URL hash on page load; call once in `main.js`.
- `popstate` handler registered at module load — restores correct panel on back/forward.
- Recognised views: `board`, `settings`, `planning`, `teams`, `agents`, `rail`.

Panel buttons in `main.js` call `_navToggle(view)`: navigate to a panel or `history.back()` if already on it.

Panel close buttons must:
1. Immediately close the panel (set signal to `false` or hide DOM).
2. Call `if (history.state?.view === '<viewName>') history.back()` to keep history in sync.

### Signal-based panels (Preact islands)

All panels except Settings use `@preact/signals` from `src/lib/signals.js`:
- `planningPanelOpenSignal`, `teamsPanelOpenSignal`, `agentsPanelOpenSignal`, `railOpenSignal`

Settings is a vanilla DOM panel at `#settings-panel`, opened via `open-settings-panel` CustomEvent.

### Key files

| File | Purpose |
|---|---|
| `src/scripts/router.js` | Browser history navigation |
| `src/scripts/main.js` | App entry: panel button listeners, initRouter |
| `src/lib/signals.js` | Shared reactive state (Preact signals) |
| `src/scripts/board-loader.js` | Issue loading, filter UI, new-issue modal |
| `src/scripts/state.js` | Shared mutable app state object |
| `src/lib/board.js` | Kanban board rendering |
| `src/lib/github-api.js` | GitHub REST API calls |

### ESLint globals

`history` and `location` are declared in `eslint.config.js` `browserGlobals` so router code is lint-clean.
