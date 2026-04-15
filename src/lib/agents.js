import { LANE_ACTIONS, CODE_EDITORS, DEFAULT_AGENT_MAX_ITERATIONS } from './constants.js';
import { AGENT_BASE_URL } from './config.js';
import { nanoid } from 'nanoid';

const DEFAULT_AGENTS = [
  {
    id: 'implementer',
    name: 'ImplementerAgent',
    icon: 'code',
    description: 'Writes code and opens a draft PR automatically',
    provider: 'claude',
    model: 'claude-sonnet-4-6',
    fallbackProvider: 'openai',
    fallbackModel: 'gpt-4o',
    sampling: 'deterministic',
    apiKey: '',
    endpoint: AGENT_BASE_URL,
    lanes: ['todo', 'in_progress'],
    actionType: 'implement',
    autonomy: 'assist',
  },
  {
    id: 'refiner',
    name: 'IssueRefiner',
    icon: 'edit_note',
    description: 'Improves issue descriptions and acceptance criteria',
    provider: 'claude',
    model: 'claude-opus-4-6',
    fallbackProvider: 'openai',
    fallbackModel: 'gpt-4o',
    sampling: 'creative',
    apiKey: '',
    endpoint: AGENT_BASE_URL,
    lanes: ['triage'],
    actionType: 'refine',
    autonomy: 'assist',
  },
];

const DEFAULT_TEAMS = [
  {
    id: 'fullstack',
    name: 'Full Stack',
    mode: 'sequential',
    status: 'production',
    agents: ['refiner', 'implementer'],
  },
];

// ── Agent CRUD ────────────────────────────────────────────────

export function getAgents() {
  try {
    const stored = localStorage.getItem('pnx_agents');
    return stored ? JSON.parse(stored) : DEFAULT_AGENTS;
  } catch {
    return DEFAULT_AGENTS;
  }
}

export function saveAgent(agent) {
  const agents = getAgents();
  const idx = agents.findIndex((a) => a.id === agent.id);
  if (idx > -1) agents[idx] = agent;
  else agents.push({ ...agent, id: agent.id || nanoid() });
  localStorage.setItem('pnx_agents', JSON.stringify(agents));
}

export function removeAgent(id) {
  const agents = getAgents().filter((a) => a.id !== id);
  localStorage.setItem('pnx_agents', JSON.stringify(agents));
}

// ── Team CRUD ─────────────────────────────────────────────────

export function getTeams() {
  try {
    const stored = localStorage.getItem('pnx_teams');
    return stored ? JSON.parse(stored) : DEFAULT_TEAMS;
  } catch {
    return DEFAULT_TEAMS;
  }
}

export function saveTeam(team) {
  const teams = getTeams();
  const idx = teams.findIndex((t) => t.id === team.id);
  if (idx > -1) teams[idx] = team;
  else teams.push({ ...team, id: team.id || nanoid() });
  localStorage.setItem('pnx_teams', JSON.stringify(teams));
}

export function removeTeam(id) {
  const teams = getTeams().filter((t) => t.id !== id);
  localStorage.setItem('pnx_teams', JSON.stringify(teams));
}

// ── Issue → Team assignment ───────────────────────────────────

const ISSUE_TEAMS_KEY = 'pnx_issue_teams';

function _getIssueTeams() {
  try {
    return JSON.parse(localStorage.getItem(ISSUE_TEAMS_KEY) || '{}');
  } catch {
    return {};
  }
}

export function getIssueTeam(repo, issueNumber) {
  const all = _getIssueTeams();
  return all[repo]?.[String(issueNumber)] ?? null;
}

export function setIssueTeam(repo, issueNumber, teamId) {
  const all = _getIssueTeams();
  if (!all[repo]) all[repo] = {};
  if (teamId) all[repo][String(issueNumber)] = teamId;
  else delete all[repo][String(issueNumber)];
  try {
    localStorage.setItem(ISSUE_TEAMS_KEY, JSON.stringify(all));
  } catch {}
}

// ── Issue → Team assignment metadata ─────────────────────────
// Stores AI-assignment details: source, confidence, needsManual, reasoning.

const ISSUE_TEAM_META_KEY = 'pnx_issue_team_meta';

function _getIssueTeamMetaAll() {
  try {
    return JSON.parse(localStorage.getItem(ISSUE_TEAM_META_KEY) || '{}');
  } catch {
    return {};
  }
}

export function getAllIssueTeamMeta() {
  return _getIssueTeamMetaAll();
}

export function getIssueTeamMeta(repo, issueNumber) {
  return _getIssueTeamMetaAll()[repo]?.[String(issueNumber)] ?? null;
}

export function setIssueTeamMeta(repo, issueNumber, meta) {
  const all = _getIssueTeamMetaAll();
  if (!all[repo]) all[repo] = {};
  all[repo][String(issueNumber)] = meta;
  try {
    localStorage.setItem(ISSUE_TEAM_META_KEY, JSON.stringify(all));
  } catch {}
}

export function clearIssueTeamMeta(repo, issueNumber) {
  const all = _getIssueTeamMetaAll();
  if (all[repo]) {
    delete all[repo][String(issueNumber)];
    try {
      localStorage.setItem(ISSUE_TEAM_META_KEY, JSON.stringify(all));
    } catch {}
  }
}

// ── Global AI key/provider ────────────────────────────────────

export function getGlobalAiProvider() {
  return localStorage.getItem('pnx_ai_provider') || 'claude';
}

export function setGlobalAiProvider(provider) {
  localStorage.setItem('pnx_ai_provider', provider);
}

export function getGlobalAiKey() {
  return localStorage.getItem('pnx_ai_key') || '';
}

export function setGlobalAiKey(key) {
  if (key) localStorage.setItem('pnx_ai_key', key);
  else localStorage.removeItem('pnx_ai_key');
}

// ── Agent max iterations ──────────────────────────────────────

export function getAgentMaxIterations() {
  const val = parseInt(localStorage.getItem('pnx_agent_max_iterations'), 10);
  return val > 0 ? val : DEFAULT_AGENT_MAX_ITERATIONS;
}

export function setAgentMaxIterations(n) {
  const val = parseInt(n, 10);
  if (!Number.isFinite(val) || val < 1) return;
  localStorage.setItem('pnx_agent_max_iterations', String(val));
}

// ── Code editor preference ────────────────────────────────────

export function getCustomEditorCmd() {
  return localStorage.getItem('pnx_custom_editor_cmd') || '';
}

export function setCustomEditorCmd(cmd) {
  if (cmd) localStorage.setItem('pnx_custom_editor_cmd', cmd);
  else localStorage.removeItem('pnx_custom_editor_cmd');
}

export function getCodeEditor() {
  const id = localStorage.getItem('pnx_code_editor') ?? 'vscode';
  const editor = CODE_EDITORS.find((e) => e.id === id) ?? CODE_EDITORS[0];
  if (editor.id === 'custom') {
    return { ...editor, cmd: getCustomEditorCmd() };
  }
  return editor;
}

export function setCodeEditor(id) {
  localStorage.setItem('pnx_code_editor', id);
}

// ── Lane action resolver ──────────────────────────────────────

/**
 * Returns the action config for a given column, checking agent lane assignments
 * first, then falling back to the static LANE_ACTIONS default.
 */
export function getLaneAction(colId) {
  const agents = getAgents();
  const agent = agents.find((a) => a.lanes.includes(colId));

  const base = LANE_ACTIONS[colId];
  if (!base) return null;

  if (agent) {
    // Use agent's actionType to pick gradient/icon from base, override label
    return { ...base, type: agent.actionType };
  }
  return base;
}
