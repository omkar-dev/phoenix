/**
 * router.js — Browser History API for the SPA.
 *
 * URL schema (search params):
 *   ?repo=owner/repo  — currently loaded repository
 *   &panel=settings|planning|agents|teams — active overlay panel
 *
 * Panel navigation pushes a history entry (back/forward supported).
 * Repo changes use replaceState (URL stays in sync, no extra history entries).
 *
 * Usage:
 *   import { pushPanel, replaceRepo, initRouter } from './router.js';
 */

let _restoring = false;

/** True while a popstate event is being processed — prevents re-entrant pushes. */
export const isRestoring = () => _restoring;

/** Read URL search params from the current location. */
export function getParams() {
  return new URLSearchParams(window.location.search);
}

/** Return the panel name from the URL, or null. */
export function getUrlPanel() {
  return getParams().get('panel');
}

/** Return the repo from the URL, or null. */
export function getUrlRepo() {
  return getParams().get('repo');
}

function _buildUrl(repo, panel) {
  const p = new URLSearchParams();
  if (repo) p.set('repo', repo);
  if (panel) p.set('panel', panel);
  const qs = p.toString();
  return qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
}

/**
 * Push a new history entry when a panel opens.
 * The current repo (from URL) is preserved in the new URL.
 */
export function pushPanel(panelName) {
  const repo = getUrlRepo();
  history.pushState({ panel: panelName, repo }, '', _buildUrl(repo, panelName));
}

/**
 * Update the URL to reflect the active repo without creating a history entry.
 * Called after every repo load so back/forward works across panel navigation.
 */
export function replaceRepo(repo) {
  const panel = getUrlPanel();
  history.replaceState({ repo, panel }, '', _buildUrl(repo, panel));
}

/**
 * Remove the panel from the current URL entry (replaceState, no new history entry).
 * Called when a panel is closed by the user so the URL stays accurate.
 */
export function clearPanelFromUrl() {
  const repo = getUrlRepo();
  history.replaceState({ repo }, '', _buildUrl(repo, null));
}

/**
 * Set up the popstate listener to restore SPA state when the user navigates
 * with the browser back/forward buttons.
 *
 * @param {object} handlers
 * @param {(panel: string) => void} handlers.openPanel   — show the named panel
 * @param {() => void}              handlers.closeAll    — hide all overlay panels
 * @param {(repo: string) => void}  handlers.loadRepo    — load a repo (no history push)
 * @param {() => void}              handlers.showEmpty   — show empty board state
 */
export function initRouter({ openPanel, closeAll, loadRepo, showEmpty }) {
  window.addEventListener('popstate', () => {
    _restoring = true;
    try {
      const p = getParams();
      const panel = p.get('panel');
      const repo = p.get('repo');

      // Always close all panels first, then selectively reopen.
      closeAll();

      if (panel) {
        openPanel(panel);
      }

      if (repo) {
        loadRepo(repo);
      } else {
        showEmpty();
      }
    } finally {
      _restoring = false;
    }
  });
}
