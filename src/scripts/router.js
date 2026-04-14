/**
 * router.js — URL ↔ app-state synchronisation.
 *
 * Panels are reflected in the `?panel=` search param so that direct URLs
 * (e.g. `/?panel=planning`) and browser back/forward navigation work
 * correctly.
 *
 * The `_restoring` flag is set to `true` during the one-time startup call to
 * `restoreFromUrl()`.  Effect blocks that write to the URL must check
 * `isRestoring()` before calling `setPanel` / `clearPanelFromUrl`, so they
 * do not interfere with the initial state-restoration pass.
 */

let _restoring = false;

/** Returns a snapshot of the current URL search params. */
export function getParams() {
  return new URLSearchParams(location.search);
}

/** Replaces the current history entry, adding/updating `?panel=<name>`. */
export function setPanel(name) {
  const p = getParams();
  p.set('panel', name);
  history.replaceState(null, '', `?${p}`);
}

/** Removes the `panel` search param from the current history entry. */
export function clearPanelFromUrl() {
  const p = getParams();
  p.delete('panel');
  const qs = p.toString();
  history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
}

/** True while `restoreFromUrl` is executing; effects should not write the URL. */
export function isRestoring() {
  return _restoring;
}

/**
 * One-time startup call: reads the current URL and drives the initial
 * app state.  Must be called *before* any `effect()` blocks are registered
 * so those blocks do not fire a stale URL-clear on their first evaluation.
 *
 * @param {object} callbacks
 * @param {(name: string) => void} callbacks.openPanel  - open a named panel
 * @param {() => void}             callbacks.closeAll   - close all panels
 * @param {(repo: string) => void} callbacks.loadRepo   - load a repository
 * @param {() => void}             callbacks.showEmpty  - show the empty state
 */
export function restoreFromUrl({ openPanel, closeAll, loadRepo, showEmpty }) {
  const p = getParams();
  const panel = p.get('panel');
  const repo = p.get('repo');
  _restoring = true;
  try {
    closeAll();
    if (panel) openPanel(panel);
    if (repo) loadRepo(repo);
    else showEmpty();
  } finally {
    _restoring = false;
  }
}

/**
 * Wires the `popstate` listener so browser back/forward navigation updates
 * app state.  Must be called once during module initialisation.
 *
 * @param {object} callbacks
 * @param {(panel: string | null) => void} callbacks.onPanel
 * @param {(repo: string) => void}         callbacks.onRepo
 */
export function initRouter({ onPanel, onRepo }) {
  window.addEventListener('popstate', () => {
    const p = getParams();
    onPanel(p.get('panel') ?? null);
    const repo = p.get('repo');
    if (repo) onRepo(repo);
  });
}
