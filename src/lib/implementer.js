import { AGENT_BASE_URL as AGENT_BASE } from './config.js';
import { calcRunCost } from './constants.js';
const LOG_STORE_KEY = 'pnx_agent_logs';
const RUN_STORE_KEY = 'pnx_run_store';
const DISMISSED_SUGGESTIONS_KEY = 'pnx_dismissed_suggestions';

/** @type {Map<number, {status:'pending'|'idle'|'running'|'cancelled'|'done'|'failed'|'interrupted'|'needs_review', step:string, prUrl:string|null, branch:string|null, worktreePath:string|null, model:string|null, cost:{inputTokens:number,outputTokens:number,estimatedUsd:number,model:string}|null}>} */
export const runStore = new Map();

/** @type {Map<number, Array<{type:string,message:string,ts:number,tool?:string,path?:string}>>} */
export const logStore = new Map();

/** @type {Map<number, {title:string, description:string, acceptance_criteria:string[]}>} */
export const suggestionStore = new Map();

/** @type {Set<number>} Issue numbers whose AI suggestion has been dismissed */
export const dismissedSuggestions = new Set();

/** @type {Map<number, number>} Maps issue number → unresolved PR review thread count */
export const prUnresolvedStore = new Map();

/** Update the unresolved PR thread count for an issue and notify listeners */
export function setPrUnresolved(issueNumber, count) {
  prUnresolvedStore.set(issueNumber, count);
  _notify();
}

/** @type {Map<number, boolean>} Maps issue number → whether the PR has merge conflicts */
export const prConflictsStore = new Map();

/** Update the merge conflict state for an issue and notify listeners */
export function setPrConflicts(issueNumber, hasConflicts) {
  prConflictsStore.set(issueNumber, hasConflicts);
  _notify();
}

const _listeners = new Set();

// ── Persistence helpers ───────────────────────────────────────

function _persistLogs() {
  try {
    const data = {};
    logStore.forEach((v, k) => {
      data[k] = v;
    });
    localStorage.setItem(LOG_STORE_KEY, JSON.stringify(data));
  } catch {}
}

function _persistRuns() {
  try {
    const data = {};
    runStore.forEach((v, k) => {
      data[k] = v;
    });
    localStorage.setItem(RUN_STORE_KEY, JSON.stringify(data));
  } catch {}
}

function _persistDismissed() {
  try {
    localStorage.setItem(DISMISSED_SUGGESTIONS_KEY, JSON.stringify([...dismissedSuggestions]));
  } catch {}
}

/** Issue numbers whose runs were still active when the page was last unloaded. */
const _pendingReconnects = [];

// Load persisted state on startup
(function _loadPersisted() {
  try {
    const rawLogs = localStorage.getItem(LOG_STORE_KEY);
    if (rawLogs) {
      const data = JSON.parse(rawLogs);
      Object.entries(data).forEach(([k, v]) => logStore.set(Number(k), v));
    }
  } catch {}
  try {
    const rawRuns = localStorage.getItem(RUN_STORE_KEY);
    if (rawRuns) {
      const data = JSON.parse(rawRuns);
      Object.entries(data).forEach(([k, v]) => {
        if (v.status === 'interrupted') {
          // Preserve interrupted state — user may want to continue
        } else if (v.status === 'pending') {
          // Never got a run_id — definitely interrupted
          v = { ...v, status: 'failed', step: 'Interrupted' };
        } else if (v.status === 'running') {
          if (v.runId) {
            // Agent may still be running server-side; reconnect after module load
            _pendingReconnects.push(Number(k));
          } else {
            // Old format without runId — cannot reconnect
            v = { ...v, status: 'failed', step: 'Interrupted' };
          }
        }
        runStore.set(Number(k), v);
      });
    }
  } catch {}
  try {
    const rawDismissed = localStorage.getItem(DISMISSED_SUGGESTIONS_KEY);
    if (rawDismissed) {
      JSON.parse(rawDismissed).forEach((n) => dismissedSuggestions.add(Number(n)));
    }
  } catch {}
})();

// After all module-level initialisation, attempt to reconnect any runs that
// were still active when the browser last navigated away or refreshed.
if (_pendingReconnects.length > 0) {
  Promise.resolve().then(() => Promise.all(_pendingReconnects.map(_reconnectRun)));
}

export function clearHistory() {
  logStore.clear();
  runStore.clear();
  localStorage.removeItem(LOG_STORE_KEY);
  localStorage.removeItem(RUN_STORE_KEY);
  for (const fn of _listeners) fn(null);
}

/**
 * Dismiss the AI suggestion for an issue. Removes it from suggestionStore
 * and persists the dismissed state so it does not reappear after a page reload.
 * @param {number} issueNumber
 */
export function dismissSuggestion(issueNumber) {
  dismissedSuggestions.add(issueNumber);
  suggestionStore.delete(issueNumber);
  _persistDismissed();
  for (const fn of _listeners) fn(issueNumber);
}

/** Active EventSource per issue number — used for cancellation */
const _eventSources = new Map();

/** Active PR-polling timers — poll /status until pr_url appears */
const _prPollers = new Map();

/**
 * Poll /runs/{runId}/status every 8 s until pr_url is set (background PR creation).
 * Stops after 40 attempts (~5 min) and logs an error if still nothing.
 */
function _pollForPr(n, runId, endpoint) {
  if (_prPollers.has(n)) return;
  let attempts = 0;
  const MAX = 40;

  function poll() {
    fetch(`${endpoint}/runs/${runId}/status`)
      .then((r) => r.json())
      .then((status) => {
        attempts++;
        if (status.pr_url) {
          _prPollers.delete(n);
          const cur = runStore.get(n);
          _set(n, { ...cur, status: 'done', step: 'PR opened', prUrl: status.pr_url });
          _log(n, { type: 'done', message: `PR opened → ${status.pr_url}` });
        } else if (attempts < MAX) {
          _prPollers.set(n, setTimeout(poll, 8_000));
        } else {
          _prPollers.delete(n);
          _log(n, { type: 'error', message: 'PR creation timed out — check GitHub manually' });
        }
      })
      .catch(() => {
        attempts++;
        if (attempts < MAX) _prPollers.set(n, setTimeout(poll, 8_000));
        else _prPollers.delete(n);
      });
  }

  // First check after 6 s — PR creation usually takes 2-4 s
  _prPollers.set(n, setTimeout(poll, 6_000));
}

export function onRunUpdate(fn) {
  _listeners.add(fn);
  return () => _listeners.delete(fn);
}

function _set(n, state) {
  runStore.set(n, state);
  _persistRuns();
  for (const fn of _listeners) fn(n);
}

function _log(n, entry) {
  if (!logStore.has(n)) logStore.set(n, []);
  const arr = logStore.get(n);
  if (entry.type === 'thinking') {
    // Replace the last thinking entry in-place so heartbeats don't pile up
    const lastIdx = arr.findLastIndex((e) => e.type === 'thinking');
    if (lastIdx !== -1) {
      arr[lastIdx] = { ...entry, ts: Date.now() };
      _persistLogs();
      for (const fn of _listeners) fn(n);
      return;
    }
  }
  if (entry.type === 'reasoning') {
    // Accumulate streaming chunks into the last reasoning entry
    if (arr.length > 0 && arr[arr.length - 1].type === 'reasoning') {
      arr[arr.length - 1] = {
        ...arr[arr.length - 1],
        message: arr[arr.length - 1].message + (entry.message ?? ''),
      };
      _persistLogs();
      for (const fn of _listeners) fn(n);
      return;
    }
  }
  arr.push({ ...entry, ts: Date.now() });
  _persistLogs();
  for (const fn of _listeners) fn(n);
}

// ── Implement (write code + open PR) ─────────────────────────

/**
 * @param {object} issue  GitHub issue object
 * @param {string} repoFullName  "owner/repo"
 * @param {{ endpoint?: string, mcpServers?: object[], autonomy?: string,
 *           llmModel?: string, llmApiKey?: string, fallbackLlmModel?: string,
 *           systemPrompt?: string, purpose?: string, reasoningPattern?: string,
 *           guardrailsAlways?: string, guardrailsNever?: string, sampling?: string,
 *           userPrompt?: string }} [agentConfig]
 */
export async function implement(issue, repoFullName, agentConfig = {}) {
  const n = issue.number;
  const endpoint = agentConfig.endpoint ?? AGENT_BASE;
  const _model = agentConfig.llmModel ?? null;
  const _existingLogs = logStore.get(n) ?? [];
  const _runIndex = _existingLogs.filter((e) => e.type === 'run_start').length + 1;
  logStore.set(n, [
    ..._existingLogs,
    { type: 'run_start', ts: Date.now(), actionType: 'implement', runIndex: _runIndex },
  ]);
  _set(n, {
    status: 'pending',
    step: 'Queuing…',
    prUrl: null,
    actionType: 'implement',
    worktreePath: null,
    model: _model,
    cost: null,
    _endpoint: endpoint,
    repoFullName,
  });

  // Log team + agent context so the user knows what's running
  if (agentConfig.teamName) {
    const modeLabel = agentConfig.teamMode ? ` · ${agentConfig.teamMode}` : '';
    _log(n, { type: 'info', message: `Team: ${agentConfig.teamName}${modeLabel}` });
  }
  if (agentConfig.agentName) {
    const modelLabel = agentConfig.agentModel ? ` (${agentConfig.agentModel})` : '';
    _log(n, { type: 'info', message: `Agent: ${agentConfig.agentName}${modelLabel}` });
  }

  _log(n, { type: 'progress', message: 'Starting agent…' });

  let streamUrl;
  try {
    const res = await fetch(`${endpoint}/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        issue_number: n,
        repo_full_name: repoFullName,
        spec: _buildSpec(issue, agentConfig.userPrompt),
        base_branch: 'main',
        create_draft_pr: agentConfig.createDraftPr ?? true,
        mcp_servers: agentConfig.mcpServers ?? [],
        ...(agentConfig.llmModel ? { llm_model: agentConfig.llmModel } : {}),
        ...(agentConfig.llmApiKey ? { llm_api_key: agentConfig.llmApiKey } : {}),
        ...(agentConfig.llmBaseUrl ? { llm_base_url: agentConfig.llmBaseUrl } : {}),
        ...(agentConfig.fallbackLlmModel
          ? { fallback_llm_model: agentConfig.fallbackLlmModel }
          : {}),
        ...(agentConfig.systemPrompt ? { system_prompt: agentConfig.systemPrompt } : {}),
        ...(agentConfig.purpose ? { purpose: agentConfig.purpose } : {}),
        ...(agentConfig.reasoningPattern
          ? { reasoning_pattern: agentConfig.reasoningPattern }
          : {}),
        ...(agentConfig.guardrailsAlways
          ? { guardrails_always: agentConfig.guardrailsAlways }
          : {}),
        ...(agentConfig.guardrailsNever ? { guardrails_never: agentConfig.guardrailsNever } : {}),
        ...(agentConfig.sampling ? { sampling: agentConfig.sampling } : {}),
        ...(agentConfig.autonomy ? { autonomy: agentConfig.autonomy } : {}),
        ...(agentConfig.maxIterations ? { max_iterations: agentConfig.maxIterations } : {}),
        ...(agentConfig.existingBranch ? { existing_branch: agentConfig.existingBranch } : {}),
        ...(agentConfig.criticEnabled ? {
          critic: {
            enabled: true,
            threshold: agentConfig.criticThreshold ?? 0.75,
            max_cycles: agentConfig.criticMaxCycles ?? 2,
          },
        } : {}),
      }),
    });
    if (!res.ok) throw new Error(`Agent server ${res.status}`);
    ({ stream_url: streamUrl } = await res.json());
    const pendingRun = runStore.get(n);
    _set(n, { ...pendingRun, status: 'running', step: 'Agent queued — opening stream…' });
    _log(n, { type: 'progress', message: 'Agent queued — opening stream…' });
  } catch (err) {
    _set(n, { status: 'failed', step: err.message, prUrl: null });
    _log(n, { type: 'error', message: err.message });
    return;
  }

  // Store runId so we can reconnect after a page refresh
  const _runId = streamUrl.split('/').filter(Boolean).at(-2);
  _set(n, { ...runStore.get(n), runId: _runId });
  _openStream(n, `${endpoint}${streamUrl}`);
}

// ── SSE stream handler (shared by implement and reconnect) ────

/**
 * Open an EventSource for a running agent run.
 *
 * @param {number} issueNumber
 * @param {string} url            Full URL to the SSE stream endpoint
 * @param {number} [skipBeforeTs] Skip events with a timestamp at-or-before this
 *                                value (ms since epoch).  Used during reconnect
 *                                to avoid replaying events already loaded from DB.
 */
function _openStream(issueNumber, url, skipBeforeTs = 0) {
  const es = new EventSource(url);
  _eventSources.set(issueNumber, es);
  let errorStreak = 0;

  es.onmessage = (e) => {
    errorStreak = 0;
    const event = JSON.parse(e.data);

    // Skip events already replayed from DB logs during a post-refresh reconnect
    if (skipBeforeTs > 0 && event.timestamp) {
      if (new Date(event.timestamp).getTime() <= skipBeforeTs) return;
    }

    const cur = runStore.get(issueNumber) ?? { status: 'running', step: '', prUrl: null };

    switch (event.type) {
      case 'progress':
        if (event.data.step === 'thinking') {
          _set(issueNumber, { ...cur, step: event.data.message });
          _log(issueNumber, { type: 'thinking', message: event.data.message });
        } else {
          _set(issueNumber, {
            ...cur,
            step: event.data.message,
            worktreePath: event.data.worktree_path ?? cur.worktreePath ?? null,
          });
          _log(issueNumber, { type: 'progress', message: event.data.message });
        }
        break;
      case 'reasoning':
        _set(issueNumber, { ...cur, step: 'Thinking…' });
        _log(issueNumber, { type: 'reasoning', message: event.data.content ?? 'Thinking…' });
        break;
      case 'tool_call':
        _set(issueNumber, { ...cur, step: `${event.data.tool}: ${event.data.path ?? ''}`.trimEnd() });
        _log(issueNumber, {
          type: 'tool_call',
          message: event.data.tool,
          tool: event.data.tool,
          path: event.data.path ?? '',
        });
        break;
      case 'tool_result': {
        // Strip ANSI escape codes, then show first meaningful line + line count
        // eslint-disable-next-line no-control-regex
        const clean = (event.data.output ?? '').replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, '').trim();
        const lines = clean.split('\n').filter((l) => l.trim());
        const firstLine = (lines[0] ?? '').slice(0, 140);
        const extra = lines.length > 1 ? `  (+${lines.length - 1} lines)` : '';
        if (firstLine) _log(issueNumber, { type: 'tool_result', message: firstLine + extra });
        break;
      }
      case 'needs_review':
        _set(issueNumber, {
          ...cur,
          status: 'needs_review',
          step: 'Ready to push',
          prUrl: null,
          runId: event.data.run_id,
          branch: event.data.branch,
          worktreePath: event.data.worktree_path ?? cur.worktreePath ?? null,
        });
        _log(issueNumber, {
          type: 'done',
          message: `Changes committed on ${event.data.branch} — ready to push`,
        });
        es.close();
        _eventSources.delete(issueNumber);
        break;
      case 'complete': {
        const usage = event.data.usage;
        const cost = usage
          ? {
              inputTokens: usage.input_tokens ?? 0,
              outputTokens: usage.output_tokens ?? 0,
              estimatedUsd: calcRunCost(usage.input_tokens ?? 0, usage.output_tokens ?? 0, cur.model ?? ''),
              model: cur.model ?? '',
            }
          : cur.cost ?? null;
        const runId = cur.runId;
        const endpoint = cur._endpoint ?? AGENT_BASE;
        if (event.data.pr_pending) {
          // Branch pushed; PR is being created in background — poll status for pr_url
          _set(issueNumber, { ...cur, status: 'done', step: 'PR being created…', prUrl: null, cost });
          _log(issueNumber, {
            type: 'done',
            message: `Branch pushed (${event.data.branch}) — PR being created in background…`,
          });
          _pollForPr(issueNumber, runId, endpoint);
        } else {
          _set(issueNumber, {
            ...cur,
            status: 'done',
            step: 'PR opened',
            prUrl: event.data.pr_url ?? null,
            cost,
          });
          _log(issueNumber, { type: 'done', message: `PR opened → ${event.data.pr_url ?? ''}` });
        }
        es.close();
        _eventSources.delete(issueNumber);
        break;
      }
      case 'error':
        _set(issueNumber, { status: 'failed', step: event.data.message, prUrl: null });
        _log(issueNumber, { type: 'error', message: event.data.message });
        es.close();
        _eventSources.delete(issueNumber);
        break;
      case 'interrupted': {
        // Agent hit its iteration limit — partial work is preserved on the branch.
        const { message, worktree_path, branch } = event.data;
        _set(issueNumber, {
          ...cur,
          status: 'interrupted',
          step: message || 'Reached maximum iterations',
          branch: branch ?? cur.branch ?? null,
          worktreePath: worktree_path ?? cur.worktreePath ?? null,
          prUrl: null,
        });
        _log(issueNumber, {
          type: 'interrupted',
          message: message || 'Agent interrupted — iterations limit reached. Click Continue to resume.',
        });
        es.close();
        _eventSources.delete(issueNumber);
        break;
      }
      case 'close':
        if (cur?.status === 'running') {
          _set(issueNumber, { ...cur, status: 'failed', step: 'Agent stopped unexpectedly', prUrl: null });
          _log(issueNumber, { type: 'error', message: 'Agent run ended without completing' });
        }
        es.close();
        _eventSources.delete(issueNumber);
        break;
    }
  };

  es.onerror = () => {
    const cur = runStore.get(issueNumber);
    if (cur?.status !== 'running') return; // already terminal — do nothing
    errorStreak++;

    if (errorStreak <= 5) {
      // Transient drop (proxy timeout, network blip) — browser will auto-reconnect.
      _set(issueNumber, { ...cur, step: `Reconnecting… (attempt ${errorStreak})` });
      _log(issueNumber, { type: 'thinking', message: `SSE reconnecting… (attempt ${errorStreak})` });
      return; // do NOT close — let EventSource auto-retry
    }

    // 5 consecutive errors — check server status before giving up
    es.close();
    _eventSources.delete(issueNumber);
    const runId = cur.runId;
    const endpoint = cur._endpoint ?? AGENT_BASE;
    fetch(`${endpoint}/runs/${runId}/status`)
      .then((r) => r.json())
      .then((status) => {
        const latest = runStore.get(issueNumber);
        if (status.status === 'complete') {
          if (status.pr_url) {
            _set(issueNumber, { ...latest, status: 'done', step: 'PR opened', prUrl: status.pr_url });
            _log(issueNumber, { type: 'done', message: `PR opened → ${status.pr_url}` });
          } else {
            _set(issueNumber, { ...latest, status: 'done', step: 'PR being created…', prUrl: null });
            _log(issueNumber, { type: 'done', message: 'Branch pushed — PR being created in background…' });
            _pollForPr(issueNumber, runId, endpoint);
          }
        } else if (status.status === 'running') {
          // Server says still running — reconnect once more with a fresh EventSource
          _log(issueNumber, { type: 'thinking', message: 'Reconnecting after repeated drops…' });
          _openStream(issueNumber, url);
        } else {
          _set(issueNumber, { status: 'failed', step: status.error || 'Connection lost', prUrl: null });
          _log(issueNumber, { type: 'error', message: status.error || 'SSE connection lost' });
        }
      })
      .catch(() => {
        const latest = runStore.get(issueNumber);
        if (latest?.status === 'running') {
          _set(issueNumber, { status: 'failed', step: 'Connection lost', prUrl: null });
          _log(issueNumber, { type: 'error', message: 'SSE connection lost — server unreachable' });
        }
      });
  };
}

// ── Post-refresh reconnection helpers ─────────────────────────

/**
 * Convert a single DB log row (from GET /runs/{id}/logs) into a frontend log
 * entry suitable for logStore.
 * Returns null for event types that should not appear in the log.
 *
 * @param {{ event_type: string, data: object, logged_at: string }} dbLog
 */
function _dbLogToEntry(dbLog) {
  const data = dbLog.data ?? {};
  const ts = new Date(dbLog.logged_at).getTime();

  switch (dbLog.event_type) {
    case 'start':
      return { type: 'progress', message: `Started: issue #${data.issue_number ?? ''}`, ts };
    case 'progress':
      return data.step === 'thinking'
        ? { type: 'thinking', message: data.message ?? '', ts }
        : { type: 'progress', message: data.message ?? '', ts };
    case 'reasoning':
      return { type: 'reasoning', message: data.content ?? '', ts };
    case 'tool_call':
      return { type: 'tool_call', message: data.tool ?? '', tool: data.tool, path: data.path ?? '', ts };
    case 'tool_result': {
      // eslint-disable-next-line no-control-regex
      const clean = (data.output ?? '').replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, '').trim();
      const lines = clean.split('\n').filter((l) => l.trim());
      const firstLine = (lines[0] ?? '').slice(0, 140);
      const extra = lines.length > 1 ? `  (+${lines.length - 1} lines)` : '';
      return firstLine ? { type: 'tool_result', message: firstLine + extra, ts } : null;
    }
    case 'needs_review':
      return { type: 'done', message: `Changes committed on ${data.branch ?? 'branch'} — ready to push`, ts };
    case 'complete':
      return {
        type: 'done',
        message: data.pr_pending
          ? `Branch pushed (${data.branch ?? ''}) — PR being created…`
          : `Complete${data.pr_url ? ` → ${data.pr_url}` : ''}`,
        ts,
      };
    case 'error':
      return { type: 'error', message: data.message ?? 'Error', ts };
    case 'pr_ready':
      return { type: 'done', message: `PR opened → ${data.pr_url ?? ''}`, ts };
    case 'close':
    case 'ping':
      return null;
    default:
      return null;
  }
}

/**
 * Fetch the persisted log events for a run from the backend DB, populate
 * logStore with them (replacing any locally-cached entries), and return
 * metadata needed for reconnection dedup.
 *
 * @returns {Promise<{lastTs:number, lastEventType:string|null, lastEventData:object}>}
 */
async function _loadBackendLogs(issueNumber, runId, endpoint) {
  try {
    const resp = await fetch(`${endpoint}/runs/${runId}/logs`);
    if (!resp.ok) return { lastTs: 0, lastEventType: null, lastEventData: {} };
    const dbLogs = await resp.json();

    // Replace localStorage-cached logs with the authoritative backend history
    logStore.set(issueNumber, []);
    let lastTs = 0;
    let lastEventType = null;
    let lastEventData = {};

    for (const dbLog of dbLogs) {
      const entry = _dbLogToEntry(dbLog);
      if (entry) {
        logStore.get(issueNumber).push(entry);
        if (entry.ts > lastTs) lastTs = entry.ts;
      }
      if (!['close', 'ping'].includes(dbLog.event_type)) {
        lastEventType = dbLog.event_type;
        lastEventData = dbLog.data ?? {};
      }
    }

    _persistLogs();
    for (const fn of _listeners) fn(issueNumber);
    return { lastTs, lastEventType, lastEventData };
  } catch {
    return { lastTs: 0, lastEventType: null, lastEventData: {} };
  }
}

/**
 * Check the backend for the current state of a run that was active when the
 * page last unloaded, and reconnect or update local state accordingly.
 *
 * Called as a microtask after the module finishes loading so that all
 * subscribers (signals, board) are already registered.
 *
 * @param {number} issueNumber
 */
async function _reconnectRun(issueNumber) {
  const run = runStore.get(issueNumber);
  if (!run) return;

  const runId = run.runId;
  const endpoint = run._endpoint ?? AGENT_BASE;

  // Brief "reconnecting" label while we query the server
  _set(issueNumber, { ...run, status: 'running', step: 'Reconnecting…' });

  try {
    const resp = await fetch(`${endpoint}/runs/${runId}/status`, {
      signal: AbortSignal.timeout(5000),
    });

    if (!resp.ok) {
      // 404 = server was restarted and lost in-memory run state.
      // Try loading DB logs to distinguish between a clean failure and an interrupted run.
      try {
        const { lastEventType, lastEventData } = await _loadBackendLogs(issueNumber, runId, endpoint);
        if (lastEventType === 'interrupted') {
          _set(issueNumber, {
            ...runStore.get(issueNumber),
            status: 'interrupted',
            step: lastEventData?.message || 'Reached maximum iterations',
            branch: lastEventData?.branch ?? null,
            worktreePath: lastEventData?.worktree_path ?? null,
          });
          return;
        }
      } catch { /* ignore — fall through to failed */ }
      _set(issueNumber, { ...runStore.get(issueNumber), status: 'failed', step: 'Interrupted' });
      return;
    }

    const status = await resp.json();

    // Interrupted runs: restore state and stop — don't reopen stream.
    if (status.status === 'interrupted') {
      _set(issueNumber, {
        ...runStore.get(issueNumber),
        status: 'interrupted',
        step: status.error || 'Reached maximum iterations',
        branch: status.branch ?? null,
        worktreePath: status.worktree_path ?? null,
      });
      return;
    }

    // Load authoritative log history from the DB regardless of outcome
    const { lastTs, lastEventType, lastEventData } = await _loadBackendLogs(issueNumber, runId, endpoint);

    if (status.status === 'running') {
      // Agent is still running — reattach to the live SSE stream.
      // Events with timestamps <= lastTs are already in logStore; skip them.
      _set(issueNumber, { ...runStore.get(issueNumber), status: 'running', step: 'Reconnected' });
      _log(issueNumber, { type: 'progress', message: 'Reconnected after page refresh' });
      _openStream(issueNumber, `${endpoint}/runs/${runId}/stream`, lastTs);
    } else if (status.status === 'complete') {
      // Agent finished while the frontend was disconnected
      const cur = runStore.get(issueNumber);
      if (lastEventType === 'needs_review') {
        // assist / semi-autonomous mode: changes committed, awaiting push
        _set(issueNumber, {
          ...cur,
          status: 'needs_review',
          step: 'Ready to push',
          prUrl: null,
          runId: lastEventData.run_id ?? runId,
          branch: lastEventData.branch ?? status.branch ?? null,
          worktreePath: lastEventData.worktree_path ?? null,
        });
      } else if (status.pr_url) {
        _set(issueNumber, { ...cur, status: 'done', step: 'PR opened', prUrl: status.pr_url });
        _log(issueNumber, { type: 'done', message: `PR opened → ${status.pr_url}` });
      } else if (lastEventType === 'complete' && lastEventData.pr_pending) {
        // PR creation was still in progress — resume polling
        _set(issueNumber, { ...cur, status: 'done', step: 'PR being created…', prUrl: null });
        _pollForPr(issueNumber, runId, endpoint);
      } else {
        _set(issueNumber, { ...cur, status: 'done', step: 'Complete', prUrl: null });
      }
    } else {
      // failed or unrecognised — surface the error message if available
      _set(issueNumber, {
        ...runStore.get(issueNumber),
        status: 'failed',
        step: status.error ?? 'Failed',
      });
    }
  } catch {
    _set(issueNumber, { ...runStore.get(issueNumber), status: 'failed', step: 'Interrupted' });
  }
}

// ── Refine (improve issue description) ───────────────────────

export async function refine(issue, agentConfig = {}) {
  const n = issue.number;
  const endpoint = agentConfig.endpoint ?? AGENT_BASE;
  const _existingRefLogs = logStore.get(n) ?? [];
  const _refRunIndex = _existingRefLogs.filter((e) => e.type === 'run_start').length + 1;
  logStore.set(n, [
    ..._existingRefLogs,
    { type: 'run_start', ts: Date.now(), actionType: 'refine', runIndex: _refRunIndex },
  ]);
  _set(n, {
    status: 'pending',
    step: 'Analyzing issue…',
    prUrl: null,
    actionType: 'refine',
    model: agentConfig.llmModel ?? null,
    cost: null,
    _endpoint: endpoint,
  });

  if (agentConfig.teamName) {
    const modeLabel = agentConfig.teamMode ? ` · ${agentConfig.teamMode}` : '';
    _log(n, { type: 'info', message: `Team: ${agentConfig.teamName}${modeLabel}` });
  }
  if (agentConfig.agentName) {
    const modelLabel = agentConfig.agentModel ? ` (${agentConfig.agentModel})` : '';
    _log(n, { type: 'info', message: `Agent: ${agentConfig.agentName}${modelLabel}` });
  }

  _log(n, { type: 'progress', message: 'Sending to IssueRefiner…' });

  let streamUrl;
  try {
    const res = await fetch(`${endpoint}/refine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: issue.title,
        body: issue.body ?? '',
        ...(agentConfig.llmModel ? { llm_model: agentConfig.llmModel } : {}),
        ...(agentConfig.llmApiKey ? { llm_api_key: agentConfig.llmApiKey } : {}),
        ...(agentConfig.llmBaseUrl ? { llm_base_url: agentConfig.llmBaseUrl } : {}),
        ...(agentConfig.systemPrompt ? { system_prompt: agentConfig.systemPrompt } : {}),
        ...(agentConfig.userPrompt ? { user_prompt: agentConfig.userPrompt } : {}),
        ...(agentConfig.sampling ? { sampling: agentConfig.sampling } : {}),
      }),
    });
    if (!res.ok) throw new Error(`Agent server ${res.status}`);
    ({ stream_url: streamUrl } = await res.json());
    const pendingRefine = runStore.get(n);
    _set(n, { ...pendingRefine, status: 'running' });
    _log(n, { type: 'progress', message: 'Refiner started — streaming reasoning…' });
  } catch (err) {
    _set(n, { status: 'failed', step: err.message, prUrl: null });
    _log(n, { type: 'error', message: err.message });
    return;
  }

  const es = new EventSource(`${endpoint}${streamUrl}`);
  _eventSources.set(n, es);

  es.onmessage = (e) => {
    const event = JSON.parse(e.data);
    const cur = runStore.get(n) ?? { status: 'running', step: '', prUrl: null };

    switch (event.type) {
      case 'reasoning':
        _set(n, { ...cur, step: 'Thinking…' });
        _log(n, { type: 'reasoning', message: event.data.content ?? '' });
        break;
      case 'progress':
        _set(n, { ...cur, step: event.data.message });
        _log(n, { type: 'progress', message: event.data.message });
        break;
      case 'suggestion':
        suggestionStore.set(n, event.data);
        _log(n, { type: 'done', message: 'AI suggestion ready — see Details tab' });
        for (const fn of _listeners) fn(n);
        break;
      case 'complete': {
        const usage = event.data.usage;
        const cur2 = runStore.get(n);
        const cost2 = usage
          ? {
              inputTokens: usage.input_tokens ?? 0,
              outputTokens: usage.output_tokens ?? 0,
              estimatedUsd: calcRunCost(usage.input_tokens ?? 0, usage.output_tokens ?? 0, cur2?.model ?? ''),
              model: cur2?.model ?? '',
            }
          : cur2?.cost ?? null;
        _set(n, { ...cur2, status: 'done', step: 'Refinement complete', prUrl: null, cost: cost2 });
        es.close();
        _eventSources.delete(n);
        break;
      }
      case 'error':
        _set(n, { status: 'failed', step: event.data.message, prUrl: null });
        _log(n, { type: 'error', message: event.data.message });
        es.close();
        _eventSources.delete(n);
        break;
      case 'close':
        es.close();
        _eventSources.delete(n);
        break;
    }
  };

  es.onerror = () => {
    const cur = runStore.get(n);
    if (cur?.status === 'running') {
      _set(n, { status: 'failed', step: 'Connection lost', prUrl: null });
      _log(n, { type: 'error', message: 'SSE connection lost' });
    }
    es.close();
    _eventSources.delete(n);
  };
}

// ── Push committed branch + open PR ──────────────────────────

export async function pushRun(issueNumber, repoFullName = null) {
  const run = runStore.get(issueNumber);
  if (!run?.runId) return;
  const runId = run.runId;
  const repo = run.repoFullName ?? repoFullName;

  _set(issueNumber, { ...run, status: 'running', step: 'Pushing branch…' });
  _log(issueNumber, { type: 'progress', message: 'Pushing branch to GitHub…' });

  try {
    let res = await fetch(`${AGENT_BASE}/runs/${runId}/push`, { method: 'POST' });

    // Server was restarted — run is gone from memory but worktree is still on disk.
    // Fall back to /push-direct using the branch + worktree path stored locally.
    if (res.status === 404 && run.branch && run.worktreePath && repo) {
      res = await fetch(`${AGENT_BASE}/push-direct`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          worktree_path: run.worktreePath,
          branch_name: run.branch,
          repo_full_name: repo,
          issue_number: issueNumber,
        }),
      });
    }

    const data = await res.json();

    // Worktree was cleaned up after server restart — code changes are gone, must re-run.
    if (res.status === 410 && data.detail === 'worktree_gone') {
      _set(issueNumber, { status: 'idle', step: '', prUrl: null });
      _log(issueNumber, { type: 'error', message: 'Worktree was cleaned up — please re-run the implementation.' });
      return;
    }

    if (!res.ok) throw new Error(data.detail ?? `Server ${res.status}`);
    _set(issueNumber, {
      ...runStore.get(issueNumber),
      status: 'done',
      step: 'PR opened',
      prUrl: data.pr_url,
    });
    _log(issueNumber, { type: 'done', message: `PR opened → ${data.pr_url ?? ''}` });
  } catch (err) {
    _set(issueNumber, {
      ...runStore.get(issueNumber),
      status: 'needs_review',
      step: 'Push failed — retry?',
    });
    _log(issueNumber, { type: 'error', message: err.message });
  }
}

// ── Cancel a running run ──────────────────────────────────────

export function cancelRun(issueNumber) {
  const es = _eventSources.get(issueNumber);
  if (es) {
    es.close();
    _eventSources.delete(issueNumber);
  }
  const run = runStore.get(issueNumber);
  // Best-effort: tell the backend to stop the run (ignore failures)
  if (run?.runId) {
    fetch(`${run._endpoint ?? AGENT_BASE}/runs/${run.runId}/cancel`, { method: 'POST' }).catch(() => {});
  }
  _set(issueNumber, { ...(run ?? {}), status: 'cancelled', step: 'Cancelled by user', prUrl: run?.prUrl ?? null });
  _log(issueNumber, { type: 'error', message: 'Stopped by user' });
}

// ── Continue an interrupted run ───────────────────────────────

/**
 * Mark an interrupted run as ready for continuation.
 * Returns the saved branch name so the caller can pass it as `existingBranch`
 * when spawning a new implement run.
 *
 * @param {number} issueNumber
 * @returns {{ branch: string|null, worktreePath: string|null }}
 */
export function getInterruptedState(issueNumber) {
  const run = runStore.get(issueNumber);
  if (run?.status !== 'interrupted') return { branch: null, worktreePath: null };
  return { branch: run.branch ?? null, worktreePath: run.worktreePath ?? null };
}

// ── Delegation log helper ─────────────────────────────────────

/**
 * Emits a `delegation` log entry visible in the Agent Logs tab.
 * Call this just before handing off from one team agent to the next.
 */
export function logDelegation(issueNumber, fromAgentName, toAgentName) {
  _log(issueNumber, {
    type: 'delegation',
    message: `${fromAgentName} → ${toAgentName}`,
    from: fromAgentName,
    to: toAgentName,
  });
}

// ── Helpers ───────────────────────────────────────────────────

function _buildSpec(issue, userPrompt = null) {
  const body = issue.body ?? '';
  return {
    intent: issue.title,
    acceptance_criteria: _extractCriteria(body),
    technical_notes: body.slice(0, 2000) || null,
    context_files: [],
    ...(userPrompt ? { additional_comments: userPrompt } : {}),
  };
}

// ── MCP connectivity check ────────────────────────────────────

/**
 * Pings an MCP server URL to verify it is reachable.
 * Uses no-cors mode so cross-origin servers respond without CORS headers.
 * Resolves to {ok:true} if any network response arrives within 5 s,
 * or {ok:false, error:string} on timeout / network failure.
 */
export async function pingMcpServer(url) {
  try {
    const controller = new AbortController();
    const timerId = setTimeout(() => controller.abort(), 5000);
    await fetch(url, { signal: controller.signal, method: 'HEAD', mode: 'no-cors' });
    clearTimeout(timerId);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.name === 'AbortError' ? 'Timeout' : 'Unreachable' };
  }
}

function _extractCriteria(body) {
  const bullets = body
    .split('\n')
    .filter((l) => /^[-*]\s/.test(l))
    .slice(0, 10);
  if (bullets.length > 0) return bullets.map((l) => l.replace(/^[-*]\s+/, ''));
  const first = body.trim().slice(0, 200);
  return first ? [first] : ['See issue for details'];
}
