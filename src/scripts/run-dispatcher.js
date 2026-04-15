/**
 * run-dispatcher.js
 *
 * Business logic for dispatching agent runs: maps an issue + repo state to the
 * right agent(s) or team, then calls implement() / refine().
 *
 * Extracted from drawer.js so both the legacy drawer and the new Preact island
 * can import it without pulling in DOM code.
 */
import {
  implement,
  refine,
  cancelRun,
  pushRun,
  onRunUpdate,
  runStore,
  suggestionStore,
  logDelegation,
  getInterruptedState,
} from '../lib/implementer.js';
import { getAgents, getTeams, getIssueTeam, getGlobalAiKey, getAgentMaxIterations } from '../lib/agents.js';
import { moveCard } from '../lib/board.js';
import { getFilters } from './board-loader.js';
import { state } from './state.js';

export { cancelRun, pushRun };

// ── Agent config builder ──────────────────────────────────────────────────────

function _agentConfig(agent, team = null) {
  if (!agent) return {};
  const _prefixModel = (provider, model) => {
    if (!model) return undefined;
    return (provider === 'openai' || provider === 'copilot') && !model.startsWith('openai/')
      ? `openai/${model}`
      : model;
  };
  return {
    endpoint: agent.endpoint,
    mcpServers: agent.mcpServers ?? [],
    autonomy: agent.autonomy || undefined,
    llmModel: _prefixModel(agent.provider, agent.model),
    llmApiKey: agent.apiKey || getGlobalAiKey() || undefined,
    llmBaseUrl: agent.llmBaseUrl || undefined,
    fallbackLlmModel: _prefixModel(agent.fallbackProvider, agent.fallbackModel),
    systemPrompt: agent.systemPrompt || undefined,
    purpose: agent.purpose || undefined,
    reasoningPattern: agent.reasoningPattern || undefined,
    guardrailsAlways: agent.guardrailsAlways || undefined,
    guardrailsNever: agent.guardrailsNever || undefined,
    sampling: agent.sampling || undefined,
    criticEnabled: agent.criticEnabled ?? false,
    criticThreshold: agent.criticThreshold ?? 0.75,
    criticMaxCycles: agent.criticMaxCycles ?? 2,
    agentName: agent.name || agent.id,
    agentModel: agent.model || agent.provider,
    agentActionType: agent.actionType || 'implement',
    maxIterations: getAgentMaxIterations(),
    teamName: team?.name || null,
    teamMode: team?.mode || null,
  };
}

// ── Dispatcher ────────────────────────────────────────────────────────────────

export async function triggerImplement(issue, overrideAgentId = null) {
  let issueColId = null;
  for (const [colId, col] of Object.entries(state.columns)) {
    if (col.issues?.some((i) => i.number === issue.number)) {
      issueColId = colId;
      break;
    }
  }

  // Move issue to "In Progress" if it's in a pre-progress column
  const PRE_PROGRESS = new Set(['triage', 'todo']);
  if (issueColId && PRE_PROGRESS.has(issueColId)) {
    moveCard(issue.number, issueColId, 'in_progress', getFilters);
    issueColId = 'in_progress';
  }

  const teams = getTeams();
  const agents = getAgents();

  const issueRepo = state.issueSourceRepo || state.repoFullName;

  if (overrideAgentId) {
    const agent = agents.find((a) => a.id === overrideAgentId);
    if (agent) {
      implement(issue, issueRepo, _agentConfig(agent, null));
      return;
    }
  }

  const assignedTeamId = state.repoFullName ? getIssueTeam(state.repoFullName, issue.number) : null;
  const assignedTeam = assignedTeamId ? teams.find((t) => t.id === assignedTeamId) : null;

  const prodTeam =
    assignedTeam ??
    teams.find(
      (t) =>
        t.status === 'production' &&
        (t.agents ?? []).some((id) =>
          agents.find((a) => a.id === id && (a.lanes ?? []).includes(issueColId))
        )
    );

  if (prodTeam && prodTeam.mode === 'sequential') {
    const teamAgents = (prodTeam.agents ?? [])
      .map((id) => agents.find((a) => a.id === id))
      .filter(Boolean);

    let currentIssue = issue;
    for (let i = 0; i < teamAgents.length; i++) {
      const agent = teamAgents[i];
      const nextAgent = teamAgents[i + 1];

      if (agent.actionType === 'refine') {
        refine(currentIssue, _agentConfig(agent, prodTeam));
        await new Promise((resolve) => {
          const unsub = onRunUpdate((n) => {
            if (n !== issue.number) return;
            const run = runStore.get(n);
            if (run?.status === 'done' || run?.status === 'failed') {
              unsub();
              resolve();
            }
          });
        });
        const suggestion = suggestionStore.get(issue.number);
        if (suggestion) {
          currentIssue = {
            ...currentIssue,
            title: suggestion.title || currentIssue.title,
            body: [
              suggestion.description || currentIssue.body,
              ...(suggestion.acceptance_criteria?.length
                ? [
                    '\n### Acceptance Criteria',
                    ...suggestion.acceptance_criteria.map((c) => `- [ ] ${c}`),
                  ]
                : []),
            ].join('\n'),
          };
        }
        if (nextAgent) logDelegation(issue.number, agent.name, nextAgent.name);
      } else {
        implement(currentIssue, issueRepo, _agentConfig(agent, prodTeam));
        return;
      }
    }
    return;
  }

  if (prodTeam && prodTeam.mode === 'parallel') {
    const teamAgents = (prodTeam.agents ?? [])
      .map((id) => agents.find((a) => a.id === id))
      .filter(Boolean);
    teamAgents.forEach((agent) => {
      if (agent.actionType === 'refine') {
        refine(issue, _agentConfig(agent, prodTeam));
      } else {
        implement(issue, issueRepo, _agentConfig(agent, prodTeam));
      }
    });
    return;
  }

  const agent =
    agents.find((a) => a.actionType === 'implement' && (a.lanes ?? []).includes(issueColId)) ??
    agents.find((a) => a.actionType === 'implement') ??
    agents.find((a) => a.id === 'implementer');

  implement(issue, issueRepo, _agentConfig(agent, null));
}

export function triggerRefine(issue, userPrompt = '') {
  const agents = getAgents();
  const agent =
    agents.find((a) => a.actionType === 'refine') ??
    agents.find((a) => a.id === 'refiner');
  refine(issue, { ..._agentConfig(agent, null), ...(userPrompt ? { userPrompt } : {}) });
}

/**
 * Re-run implementation with an optional user prompt providing additional context.
 * Used when a run is already done/needs_review and the user wants to iterate.
 *
 * @param {object} issue  GitHub issue object
 * @param {string} [userPrompt]  Additional instructions for the agent
 * @param {string|null} [overrideAgentId]
 */
export function triggerReimplement(issue, userPrompt = '', overrideAgentId = null) {
  const agents = getAgents();
  const issueRepo = state.issueSourceRepo || state.repoFullName;

  let agent = null;
  if (overrideAgentId) {
    agent = agents.find((a) => a.id === overrideAgentId) ?? null;
  }
  if (!agent) {
    agent =
      agents.find((a) => a.actionType === 'implement') ??
      agents.find((a) => a.id === 'implementer');
  }

  implement(issue, issueRepo, { ..._agentConfig(agent, null), ...(userPrompt ? { userPrompt } : {}) });
}

/**
 * Continue an interrupted run from where it left off.
 * Reuses the existing branch so the agent picks up all partial work.
 *
 * @param {object} issue  GitHub issue object
 * @param {string} [userPrompt]  Optional additional guidance
 * @param {string|null} [overrideAgentId]
 */
export function triggerContinue(issue, userPrompt = '', overrideAgentId = null) {
  const agents = getAgents();
  const issueRepo = state.issueSourceRepo || state.repoFullName;
  const { branch } = getInterruptedState(issue.number);

  let agent = null;
  if (overrideAgentId) {
    agent = agents.find((a) => a.id === overrideAgentId) ?? null;
  }
  if (!agent) {
    agent =
      agents.find((a) => a.actionType === 'implement') ??
      agents.find((a) => a.id === 'implementer');
  }

  const continuationNote = [
    'You are continuing a previous run that was stopped at the iteration limit.',
    'The partial work already done is on this branch — review what has been completed,',
    'then pick up exactly where it left off without re-doing finished work.',
    ...(userPrompt ? [`Additional guidance: ${userPrompt}`] : []),
  ].join(' ');

  implement(issue, issueRepo, {
    ..._agentConfig(agent, null),
    ...(branch ? { existingBranch: branch } : {}),
    userPrompt: continuationNote,
  });
}

/**
 * Trigger an agent run to address unresolved PR review comments.
 *
 * @param {object} issue  GitHub issue/PR object (number, title, body, html_url, …)
 * @param {Array<{isResolved:boolean, comments:Array<{body:string, path:string|null, author:{login:string}|null}>}>} reviewThreads
 */
export function triggerAddressPRComments(issue, reviewThreads, existingBranch = null) {
  const unresolved = reviewThreads.filter((t) => !t.isResolved);
  if (!unresolved.length) return;

  const commentsContext = unresolved
    .map((thread, i) => {
      const c = thread.comments[0];
      if (!c) return null;
      const loc = c.path ? `\`${c.path}\`` : 'General comment';
      const author = c.author?.login ? `@${c.author.login}: ` : '';
      return `${i + 1}. ${loc}\n   ${author}${c.body}`;
    })
    .filter(Boolean)
    .join('\n\n');

  const syntheticIssue = {
    ...issue,
    title: `Address PR #${issue.number} review comments`,
    body: [
      `Address the following unresolved reviewer comments on pull request #${issue.number}:`,
      '',
      commentsContext,
      '',
      '---',
      `Original PR: ${issue.html_url}`,
      ...(issue.body ? ['', 'Original PR description:', issue.body] : []),
    ].join('\n'),
  };

  const issueRepo = state.issueSourceRepo || state.repoFullName;
  const agents = getAgents();
  const agent =
    agents.find((a) => a.actionType === 'implement' && a.id !== 'refiner') ??
    agents.find((a) => a.actionType === 'implement') ??
    agents.find((a) => a.id === 'implementer');

  implement(syntheticIssue, issueRepo, { ..._agentConfig(agent, null), existingBranch });
}

/**
 * Trigger an agent run to resolve merge conflicts on a PR branch.
 *
 * @param {object} issue  GitHub issue/PR object
 */
export function triggerResolveConflicts(issue) {
  const syntheticIssue = {
    ...issue,
    title: `Resolve merge conflicts on PR #${issue.number}`,
    body: [
      `Pull request #${issue.number} has merge conflicts that need to be resolved.`,
      '',
      'Please:',
      '1. Fetch the latest base branch',
      '2. Merge or rebase to incorporate upstream changes',
      '3. Resolve all conflict markers in the affected files',
      '4. Commit the resolution and push to the PR branch',
      '',
      '---',
      `PR: ${issue.html_url}`,
      ...(issue.body ? ['', 'PR description:', issue.body] : []),
    ].join('\n'),
  };

  const issueRepo = state.issueSourceRepo || state.repoFullName;
  const agents = getAgents();
  const agent =
    agents.find((a) => a.actionType === 'implement' && a.id !== 'refiner') ??
    agents.find((a) => a.actionType === 'implement') ??
    agents.find((a) => a.id === 'implementer');

  implement(syntheticIssue, issueRepo, _agentConfig(agent, null));
}
