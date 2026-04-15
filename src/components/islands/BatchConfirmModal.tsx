/**
 * BatchConfirmModal — Preact island (Phase 8)
 *
 * Shown when user selects multiple Kanban cards and clicks "Run N Agents".
 * Displays selected issues, lets user configure shared agent settings,
 * then POSTs to /runs/batch.
 */
import { useState } from 'preact/hooks';
import { batchConfirmSignal } from '../../lib/signals.js';
import { AGENT_BASE_URL } from '../../lib/config.js';

export interface BatchIssue {
  number: number;
  title: string;
  repoFullName: string;
  spec: {
    intent: string;
    acceptance_criteria: string[];
    technical_notes?: string;
  };
}

export default function BatchConfirmModal() {
  const batch = batchConfirmSignal.value;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [maxConcurrent, setMaxConcurrent] = useState(3);
  const [enablePlanner, setEnablePlanner] = useState(false);
  const [enableReviewer, setEnableReviewer] = useState(false);

  if (!batch) return null;

  const { issues } = batch as { issues: BatchIssue[] };

  async function handleConfirm() {
    setLoading(true);
    setError(null);
    try {
      const runs = issues.map((issue) => ({
        issue_number: issue.number,
        repo_full_name: issue.repoFullName,
        spec: issue.spec,
        enable_planner: enablePlanner,
        enable_reviewer: enableReviewer,
      }));

      const resp = await fetch(`${AGENT_BASE_URL}/runs/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ runs, max_concurrent: maxConcurrent }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail ?? `HTTP ${resp.status}`);
      }

      batchConfirmSignal.value = null;
      // Show a simple toast via DOM (avoids importing the toast module)
      const toast = document.createElement('div');
      toast.textContent = `${issues.length} agent run${issues.length !== 1 ? 's' : ''} started`;
      Object.assign(toast.style, {
        position: 'fixed', bottom: '24px', right: '24px', zIndex: '9999',
        background: '#1d4ed8', color: '#fff', padding: '10px 18px',
        borderRadius: '8px', fontSize: '13px', fontWeight: '600',
        boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
      });
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 3000);
    } catch (err: any) {
      setError(err.message ?? 'Failed to start batch run');
    } finally {
      setLoading(false);
    }
  }

  function handleCancel() {
    batchConfirmSignal.value = null;
  }

  const overlayStyle: Record<string, string> = {
    position: 'fixed', inset: '0', zIndex: '60',
    background: 'rgba(0,0,0,0.4)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  };

  const cardStyle: Record<string, string> = {
    background: '#fff', borderRadius: '16px',
    padding: '24px', width: '480px', maxWidth: '95vw',
    boxShadow: '0 8px 40px rgba(0,0,0,0.18)',
    maxHeight: '85vh', overflowY: 'auto',
  };

  return (
    <div style={overlayStyle} onClick={(e) => e.target === e.currentTarget && handleCancel()}>
      <div style={cardStyle}>
        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: '#1b1c20' }}>
            Run {issues.length} Agent{issues.length !== 1 ? 's' : ''}
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: '#737885' }}>
            Selected issues will each get their own agent run.
          </p>
        </div>

        {/* Issue list */}
        <div style={{ marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {issues.map((issue) => (
            <div
              key={issue.number}
              style={{
                background: '#f9f9fb', border: '1px solid #edeef0',
                borderRadius: 8, padding: '8px 12px',
                display: 'flex', alignItems: 'flex-start', gap: 10,
              }}
            >
              <span style={{ color: '#737885', fontSize: 11, flexShrink: 0, paddingTop: 2 }}>
                #{issue.number}
              </span>
              <span style={{ fontSize: 13, color: '#1b1c20', lineHeight: 1.4 }}>
                {issue.title}
              </span>
            </div>
          ))}
        </div>

        {/* Config options */}
        <div style={{ marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Max concurrent */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#1b1c20', display: 'block', marginBottom: 6 }}>
              Max concurrent agents
            </label>
            <select
              value={maxConcurrent}
              onChange={(e) => setMaxConcurrent(Number((e.target as HTMLSelectElement).value))}
              style={{
                width: '100%', padding: '8px 10px', borderRadius: 8,
                border: '1px solid #d0d3e0', fontSize: 13,
              }}
            >
              {[1, 2, 3, 5, 10].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>

          {/* Planner + Reviewer toggles */}
          <div style={{ display: 'flex', gap: 20 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input
                type="checkbox"
                checked={enablePlanner}
                onChange={(e) => setEnablePlanner((e.target as HTMLInputElement).checked)}
              />
              <span>Enable Planner</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input
                type="checkbox"
                checked={enableReviewer}
                onChange={(e) => setEnableReviewer((e.target as HTMLInputElement).checked)}
              />
              <span>Enable Reviewer</span>
            </label>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            marginBottom: 16, padding: '8px 12px',
            background: '#fff8f7', border: '1px solid rgba(186,26,26,0.2)',
            borderRadius: 8, fontSize: 12, color: '#ba1a1a',
          }}>
            {error}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={handleCancel}
            disabled={loading}
            style={{
              padding: '9px 18px', borderRadius: 8, border: '1px solid #d0d3e0',
              background: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 500,
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            style={{
              padding: '9px 18px', borderRadius: 8, border: 'none',
              background: loading ? '#93a8f0' : '#1d4ed8', color: '#fff',
              cursor: loading ? 'not-allowed' : 'pointer', fontSize: 13, fontWeight: 600,
            }}
          >
            {loading ? 'Starting…' : `Confirm — Run ${issues.length} Agent${issues.length !== 1 ? 's' : ''}`}
          </button>
        </div>
      </div>
    </div>
  );
}
