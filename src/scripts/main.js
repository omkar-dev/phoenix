import { initBoard, renderBoard } from '../lib/board.js';
import { onRunUpdate } from '../lib/implementer.js';
import { AGENT_BASE_URL, SEMANTIC_BASE_URL } from '../lib/config.js';
import { state } from './state.js';
import { initBoardLoader, showState, loadIssues, getFilters } from './board-loader.js';
import { initTokenRepo } from './token-repo.js';
import { triggerImplement } from './run-dispatcher.js';
import { openDrawer } from '../lib/signals.js';
import { navigate, initRouter } from './router.js';
import { bus, Events } from '../lib/event-bus.js';
import { initFavicon } from '../lib/favicon.js';

const $ = (id) => document.getElementById(id);

// ── State callbacks (set before initBoard) ────────────────────
// openDrawer() writes drawerSignal — the IssueDrawer island reads it.
state.onOpenDrawer = openDrawer;
state.onImplement = (issue) => triggerImplement(issue);

initBoard(state);

// ── Module init ───────────────────────────────────────────────
initBoardLoader();
initTokenRepo();

// ── Run updates → board only (islands auto-update via signals) ─
onRunUpdate(() => {
  if (state.allIssues.length > 0) renderBoard(getFilters);
  bus.emit(Events.RUN_UPDATE);
});

// ── Panel navigation (via router for back/forward support) ────
function _navToggle(view) {
  if (history.state?.view === view) {
    // Already on this view → go back (closes the panel)
    history.back();
  } else {
    navigate(view);
  }
}

$('settings-btn')?.addEventListener('click', () => _navToggle('settings'));
$('agent-rail-btn')?.addEventListener('click', () => _navToggle('rail'));
$('agents-btn')?.addEventListener('click', () => _navToggle('agents'));
$('teams-btn')?.addEventListener('click', () => _navToggle('teams'));
$('planning-btn')?.addEventListener('click', () => _navToggle('planning'));

// ── Service health checks ─────────────────────────────────────

async function checkServices() {
  const setHealth = (dotId, labelId, ok, label) => {
    const dot = $(dotId),
      lbl = $(labelId);
    if (!dot || !lbl) return;
    dot.style.background = ok ? '#16a34a' : '#ba1a1a';
    lbl.style.color = ok ? '#16a34a' : '#ba1a1a';
    lbl.textContent = label;
  };

  let agentOk = false;
  let semanticOk = false;

  try {
    const r = await fetch(`${AGENT_BASE_URL}/health`, { signal: AbortSignal.timeout(3000) });
    agentOk = r.ok;
    setHealth('health-agent-dot', 'health-agent-label', agentOk, agentOk ? 'online' : 'error');
  } catch {
    setHealth('health-agent-dot', 'health-agent-label', false, 'offline');
  }

  try {
    await fetch(`${SEMANTIC_BASE_URL}/health`, { signal: AbortSignal.timeout(3000) });
    semanticOk = true;
    setHealth('health-semantic-dot', 'health-semantic-label', true, 'online');
  } catch {
    setHealth('health-semantic-dot', 'health-semantic-label', false, 'offline');
  }

  bus.emit(Events.SERVICE_HEALTH, { agent: agentOk, semantic: semanticOk });
}

checkServices();
setInterval(checkServices, 30_000);

// ── Favicon ──────────────────────────────────────────────────
initFavicon();

// ── Init ─────────────────────────────────────────────────────
initRouter();
showState('empty');
const lastRepo = localStorage.getItem('last_repo');
if (lastRepo) {
  $('repo-input').value = lastRepo;
  loadIssues(lastRepo);
}
