import { effect } from '@preact/signals';
import { initBoard, renderBoard } from '../lib/board.js';
import { onRunUpdate } from '../lib/implementer.js';
import { AGENT_BASE_URL, SEMANTIC_BASE_URL } from '../lib/config.js';
import { state } from './state.js';
import { initBoardLoader, showState, loadIssues, getFilters } from './board-loader.js';
import { initTokenRepo } from './token-repo.js';
import { triggerImplement } from './run-dispatcher.js';
import {
  railOpenSignal,
  agentsPanelOpenSignal,
  teamsPanelOpenSignal,
  planningPanelOpenSignal,
  openDrawer,
} from '../lib/signals.js';
import { bus, Events } from '../lib/event-bus.js';
import { initFavicon } from '../lib/favicon.js';
import {
  getParams,
  setPanel,
  clearPanelFromUrl,
  isRestoring,
  restoreFromUrl,
  initRouter,
} from './router.js';

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

// ── Panel helpers used by router ──────────────────────────────
function _openPanel(name) {
  switch (name) {
    case 'planning': planningPanelOpenSignal.value = true; break;
    case 'agents':   agentsPanelOpenSignal.value   = true; break;
    case 'teams':    teamsPanelOpenSignal.value     = true; break;
    case 'settings': document.dispatchEvent(new CustomEvent('open-settings-panel')); break;
  }
}

function _closeAllPanels() {
  planningPanelOpenSignal.value = false;
  agentsPanelOpenSignal.value   = false;
  teamsPanelOpenSignal.value    = false;
  document.dispatchEvent(new CustomEvent('close-settings-panel'));
}

// ── Restore panel state from URL before effects are registered ─
// This must run before the effect() blocks below so the initial
// effect evaluation sees the correct signal values and does not
// incorrectly clear a ?panel= param that belongs to the current page.
restoreFromUrl({
  openPanel: _openPanel,
  closeAll:  _closeAllPanels,
  loadRepo:  loadIssues,
  showEmpty: () => showState('empty'),
});

// ── Signal-based panel toggles (Preact islands) ───────────────
$('agent-rail-btn')?.addEventListener('click', () => {
  railOpenSignal.value = !railOpenSignal.value;
});
$('agents-btn')?.addEventListener('click', () => {
  agentsPanelOpenSignal.value = !agentsPanelOpenSignal.value;
});
$('teams-btn')?.addEventListener('click', () => {
  teamsPanelOpenSignal.value = !teamsPanelOpenSignal.value;
});
$('planning-btn')?.addEventListener('click', () => {
  planningPanelOpenSignal.value = !planningPanelOpenSignal.value;
});

// ── URL ↔ panel signal effects ────────────────────────────────
// Each effect mirrors its signal into ?panel=<name>.
// The isRestoring() guard prevents URL writes during the initial
// restoreFromUrl() pass (which already has the correct URL).
effect(() => {
  if (planningPanelOpenSignal.value) {
    if (!isRestoring()) setPanel('planning');
  } else if (getParams().get('panel') === 'planning') {
    if (!isRestoring()) clearPanelFromUrl();
  }
});

effect(() => {
  if (agentsPanelOpenSignal.value) {
    if (!isRestoring()) setPanel('agents');
  } else if (getParams().get('panel') === 'agents') {
    if (!isRestoring()) clearPanelFromUrl();
  }
});

effect(() => {
  if (teamsPanelOpenSignal.value) {
    if (!isRestoring()) setPanel('teams');
  } else if (getParams().get('panel') === 'teams') {
    if (!isRestoring()) clearPanelFromUrl();
  }
});

// ── Popstate (back/forward) ───────────────────────────────────
initRouter({
  onPanel: (name) => {
    _closeAllPanels();
    if (name) _openPanel(name);
  },
  onRepo: loadIssues,
});

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
showState('empty');
const lastRepo = localStorage.getItem('last_repo');
if (lastRepo) {
  $('repo-input').value = lastRepo;
  loadIssues(lastRepo);
}
