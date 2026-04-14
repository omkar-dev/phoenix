import { initBoard, renderBoard } from '../lib/board.js';
import { onRunUpdate } from '../lib/implementer.js';
import { AGENT_BASE_URL, SEMANTIC_BASE_URL } from '../lib/config.js';
import { state } from './state.js';
import { initBoardLoader, showState, loadIssues, getFilters, clearBoard } from './board-loader.js';
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
import { effect } from '@preact/signals';
import {
  pushPanel,
  clearPanelFromUrl,
  getUrlPanel,
  isRestoring,
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

// ── Router: push/clear URL when signal-based panels open/close ─
effect(() => {
  if (isRestoring()) return;
  if (planningPanelOpenSignal.value) {
    pushPanel('planning');
  } else if (getUrlPanel() === 'planning') {
    clearPanelFromUrl();
  }
});

effect(() => {
  if (isRestoring()) return;
  if (agentsPanelOpenSignal.value) {
    pushPanel('agents');
  } else if (getUrlPanel() === 'agents') {
    clearPanelFromUrl();
  }
});

effect(() => {
  if (isRestoring()) return;
  if (teamsPanelOpenSignal.value) {
    pushPanel('teams');
  } else if (getUrlPanel() === 'teams') {
    clearPanelFromUrl();
  }
});

// ── Router init: popstate restores SPA state from URL ─────────
function _closeAllPanels() {
  planningPanelOpenSignal.value = false;
  agentsPanelOpenSignal.value = false;
  teamsPanelOpenSignal.value = false;
  // Settings panel is DOM-based — close directly
  const sp = document.getElementById('settings-panel');
  if (sp) {
    sp.classList.add('hidden');
    sp.classList.remove('flex');
  }
}

function _openPanel(panel) {
  switch (panel) {
    case 'planning':
      planningPanelOpenSignal.value = true;
      break;
    case 'agents':
      agentsPanelOpenSignal.value = true;
      break;
    case 'teams':
      teamsPanelOpenSignal.value = true;
      break;
    case 'settings':
      document.dispatchEvent(new CustomEvent('open-settings-panel'));
      break;
  }
}

initRouter({
  openPanel: _openPanel,
  closeAll: _closeAllPanels,
  loadRepo: (repo) => {
    const input = $('repo-input');
    if (input) input.value = repo;
    // Skip the API call if this repo is already loaded — back/forward between
    // panels should not trigger a full GitHub reload.
    if (repo !== state.repoFullName) loadIssues(repo);
  },
  showEmpty: clearBoard,
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
