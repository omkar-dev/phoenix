/**
 * router.js
 *
 * Hash-based SPA router built on the browser History API.
 * Enables back/forward navigation between the board and panel views.
 *
 * Views: board | settings | planning | teams | agents | rail
 *
 * Usage:
 *   navigate('settings')   // push history + open settings panel
 *   navigate('board')      // push history + close all panels
 *   initRouter()           // call once on page load
 *
 * Each panel's own close button should do:
 *   panelSignal.value = false;
 *   if (history.state?.view === '<viewName>') history.back();
 */

import {
  railOpenSignal,
  agentsPanelOpenSignal,
  teamsPanelOpenSignal,
  planningPanelOpenSignal,
} from '../lib/signals.js';

// ── View definitions ──────────────────────────────────────────────────────────

const _views = {
  settings: {
    open() {
      document.dispatchEvent(new CustomEvent('open-settings-panel'));
    },
    close() {
      const p = document.getElementById('settings-panel');
      p?.classList.add('hidden');
      p?.classList.remove('flex');
    },
  },
  planning: {
    open() { planningPanelOpenSignal.value = true; },
    close() { planningPanelOpenSignal.value = false; },
  },
  teams: {
    open() { teamsPanelOpenSignal.value = true; },
    close() { teamsPanelOpenSignal.value = false; },
  },
  agents: {
    open() { agentsPanelOpenSignal.value = true; },
    close() { agentsPanelOpenSignal.value = false; },
  },
  rail: {
    open() { railOpenSignal.value = true; },
    close() { railOpenSignal.value = false; },
  },
};

function _closeAll() {
  for (const v of Object.values(_views)) v.close();
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Navigate to a named view, pushing a history entry.
 * Closes all other panels first. Navigating to 'board' just closes everything.
 * @param {'board'|'settings'|'planning'|'teams'|'agents'|'rail'} view
 */
export function navigate(view) {
  _closeAll();
  if (view === 'board') {
    history.pushState({ view: 'board' }, '', location.pathname + location.search);
  } else if (_views[view]) {
    history.pushState({ view }, '', `#${view}`);
    _views[view].open();
  }
}

/**
 * Seed the initial history state from the current URL hash so that
 * bookmarked panel URLs open the correct panel on page load.
 * Must be called once during app startup.
 */
export function initRouter() {
  const hash = location.hash.slice(1);
  if (hash && _views[hash]) {
    history.replaceState({ view: hash }, '', `#${hash}`);
    _views[hash].open();
  } else {
    history.replaceState({ view: 'board' }, '', location.pathname + location.search);
  }
}

// ── popstate handler ──────────────────────────────────────────────────────────

window.addEventListener('popstate', (e) => {
  const view = e.state?.view ?? 'board';
  _closeAll();
  if (view !== 'board' && _views[view]) {
    _views[view].open();
  }
});
