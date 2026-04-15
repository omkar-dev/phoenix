/**
 * FleetPanel — Preact island (Phase 5)
 *
 * Real-time fleet dashboard showing all active agent runs and their
 * PR lifecycle states. Opens its own EventSource to /fleet/events.
 */
import { useState, useEffect, useCallback } from 'preact/hooks';
import { fleetPanelOpenSignal } from '../../lib/signals.js';
import { AGENT_BASE_URL } from '../../lib/config.js';

// ── Types ─────────────────────────────────────────────────────────────────────

interface FleetItem {
  run_id: string;
  repo: string;
  issue_number: number;
  pr_number: number | null;
  pr_url: string | null;
  branch: string | null;
  lifecycle_state: string;
  ci_conclusion: string | null;
  review_decision: string | null;
  agent_status: 'running' | 'done' | 'idle';
  updated_at: string;
}

// ── Config ────────────────────────────────────────────────────────────────────

const STATE_CFG: Record<string, { color: string; bg: string; label: string }> = {
  working:           { color: '#1d4ed8', bg: '#eff6ff', label: 'Working' },
  pr_open:           { color: '#7c3aed', bg: '#f5f3ff', label: 'PR Open' },
  ci_checking:       { color: '#b45309', bg: '#fffbeb', label: 'CI Running' },
  ci_failed:         { color: '#ba1a1a', bg: '#fff8f7', label: 'CI Failed' },
  ci_passed:         { color: '#16a34a', bg: '#f0fdf4', label: 'CI Passed' },
  changes_requested: { color: '#c2410c', bg: '#fff7ed', label: 'Changes Requested' },
  approved:          { color: '#0891b2', bg: '#ecfeff', label: 'Approved' },
  merged:            { color: '#737885', bg: '#f9f9fb', label: 'Merged' },
};

const AGENT_DOT: Record<string, string> = {
  running: '#16a34a',
  done:    '#1d4ed8',
  idle:    '#737885',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_CFG[state] ?? { color: '#737885', bg: '#f9f9fb', label: state };
  return (
    <span style={{
      background: cfg.bg,
      color: cfg.color,
      border: `1px solid ${cfg.color}30`,
      borderRadius: 6,
      padding: '2px 8px',
      fontSize: 11,
      fontWeight: 600,
      whiteSpace: 'nowrap',
    }}>
      {cfg.label}
    </span>
  );
}

function AgentDot({ status }: { status: string }) {
  const color = AGENT_DOT[status] ?? '#737885';
  return (
    <span style={{
      display: 'inline-block',
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: color,
      marginRight: 4,
      flexShrink: 0,
    }} />
  );
}

function CIBadge({ conclusion }: { conclusion: string | null }) {
  if (!conclusion) return <span style={{ color: '#737885', fontSize: 11 }}>—</span>;
  const ok = conclusion === 'success';
  return (
    <span style={{
      color: ok ? '#16a34a' : '#ba1a1a',
      fontSize: 11,
      fontWeight: 600,
    }}>
      {ok ? '✓ passed' : '✗ failed'}
    </span>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function FleetPanel() {
  const isOpen = fleetPanelOpenSignal.value;
  const [items, setItems] = useState<FleetItem[]>([]);
  const [connected, setConnected] = useState(false);

  const patchItem = useCallback((runId: string, patch: Partial<FleetItem>) => {
    setItems(prev => prev.map(item =>
      item.run_id === runId ? { ...item, ...patch } : item
    ));
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    const es = new EventSource(`${AGENT_BASE_URL}/fleet/events`);

    es.onopen = () => setConnected(true);

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        if (event.type === 'fleet_snapshot') {
          setItems(event.items ?? []);
        } else if (event.type === 'lifecycle_updated' && event.runId) {
          patchItem(event.runId, {
            lifecycle_state: event.state,
            pr_url: event.prUrl ?? undefined,
            pr_number: event.prNumber ?? undefined,
          });
        } else if (event.type === 'run_started') {
          // Add a new row stub; fleet_snapshot already covers restores
          setItems(prev => {
            const exists = prev.some(i => i.run_id === event.runId);
            if (exists) return prev;
            return [{
              run_id: event.runId,
              repo: event.repo,
              issue_number: event.issueNumber,
              pr_number: null,
              pr_url: null,
              branch: null,
              lifecycle_state: 'working',
              ci_conclusion: null,
              review_decision: null,
              agent_status: 'running',
              updated_at: new Date().toISOString(),
            }, ...prev];
          });
        } else if (event.type === 'run_cancelled' && event.runId) {
          patchItem(event.runId, { agent_status: 'done' });
        }
      } catch { /* ignore */ }
    };

    es.onerror = () => setConnected(false);

    return () => {
      es.close();
      setConnected(false);
    };
  }, [isOpen, patchItem]);

  if (!isOpen) return null;

  const panelStyle: Record<string, string> = {
    position: 'fixed',
    inset: '0',
    zIndex: '50',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'flex-end',
    pointerEvents: 'none',
  };

  const cardStyle: Record<string, string> = {
    pointerEvents: 'all',
    width: '720px',
    maxWidth: '95vw',
    height: '100vh',
    background: '#fff',
    boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  };

  return (
    <div style={panelStyle}>
      <div style={cardStyle}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #edeef0', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span class="material-symbols-outlined" style={{ fontSize: 20, color: '#1d4ed8' }}>monitor_heart</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 15, color: '#1b1c20' }}>Fleet Dashboard</div>
            <div style={{ fontSize: 11, color: '#737885' }}>
              {connected ? `${items.length} active run${items.length !== 1 ? 's' : ''}` : 'Connecting…'}
            </div>
          </div>
          <button
            onClick={() => { fleetPanelOpenSignal.value = false; }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#737885', padding: 4, display: 'flex' }}
          >
            <span class="material-symbols-outlined" style={{ fontSize: 20 }}>close</span>
          </button>
        </div>

        {/* Table */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {items.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12, color: '#737885' }}>
              <span class="material-symbols-outlined" style={{ fontSize: 40, opacity: 0.4 }}>inbox</span>
              <p style={{ fontSize: 13 }}>No active agent runs</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#f9f9fb', borderBottom: '1px solid #edeef0' }}>
                  {['Repo / Issue', 'Lifecycle', 'CI', 'Agent', 'PR'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#737885', fontSize: 11 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.run_id} style={{ borderBottom: '1px solid #edeef0' }}>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ fontWeight: 500, color: '#1b1c20', fontSize: 12 }}>
                        {item.repo.split('/')[1] ?? item.repo}
                      </div>
                      <div style={{ color: '#737885', fontSize: 11 }}>#{item.issue_number}</div>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <StateBadge state={item.lifecycle_state} />
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <CIBadge conclusion={item.ci_conclusion} />
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <AgentDot status={item.agent_status} />
                        <span style={{ color: '#737885', fontSize: 11 }}>{item.agent_status}</span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {item.pr_url ? (
                        <a
                          href={item.pr_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: '#1d4ed8', textDecoration: 'none', fontSize: 11 }}
                        >
                          #{item.pr_number}
                        </a>
                      ) : (
                        <span style={{ color: '#737885', fontSize: 11 }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
