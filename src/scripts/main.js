import { initBoard, renderBoard, setMultiSelectMode, getSelectedIssues } from '../lib/board.js';
import { onRunUpdate, connectGlobalEvents } from '../lib/implementer.js';
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
  claudeSessionOpenSignal,
  fleetPanelOpenSignal,
  batchConfirmSignal,
  openDrawer,
} from '../lib/signals.js';
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
connectGlobalEvents(AGENT_BASE_URL);

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
$('claude-session-btn')?.addEventListener('click', () => {
  claudeSessionOpenSignal.value = !claudeSessionOpenSignal.value;
});
$('fleet-btn')?.addEventListener('click', () => {
  fleetPanelOpenSignal.value = !fleetPanelOpenSignal.value;
});

// ── Multi-select / batch spawn (Phase 8) ──────────────────────────────────────
let _multiSelectActive = false;
$('multi-select-btn')?.addEventListener('click', () => {
  _multiSelectActive = !_multiSelectActive;
  setMultiSelectMode(_multiSelectActive);
  const btn = $('multi-select-btn');
  if (btn) {
    btn.style.background = _multiSelectActive ? '#dae2ff' : '#f8f9fd';
    btn.style.color = _multiSelectActive ? '#1d4ed8' : '';
  }
});

$('batch-run-btn')?.addEventListener('click', () => {
  const issues = getSelectedIssues();
  if (!issues.length) return;
  // Build BatchIssue array from current issue objects
  const batchIssues = issues.map((issue) => ({
    number: issue.number,
    title: issue.title,
    repoFullName: state.repoFullName,
    spec: {
      intent: issue.title,
      acceptance_criteria: issue.body
        ? issue.body.split('\n').filter((l) => l.trim().startsWith('- [ ]') || l.trim().startsWith('- [x]')).map((l) => l.replace(/^- \[.\]\s*/, ''))
        : [],
    },
  }));
  batchConfirmSignal.value = { issues: batchIssues };
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
