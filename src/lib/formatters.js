export function escHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function timeAgo(dateStr) {
  const d = Math.floor((Date.now() - new Date(dateStr)) / 86400000);
  if (d === 0) return 'today';
  if (d < 30) return `${d}d ago`;
  const m = Math.floor(d / 30);
  if (m < 12) return `${m}mo ago`;
  return `${Math.floor(m / 12)}y ago`;
}

export function detectPriority(issue) {
  const labels = (issue.labels || []).map((l) => l.name.toLowerCase());
  if (labels.some((n) => n.includes('critical') || n.includes('p0'))) return 'critical';
  if (labels.some((n) => n.includes('high') || n.includes('p1') || n.includes('urgent')))
    return 'high';
  if (labels.some((n) => n.includes('medium') || n.includes('p2'))) return 'medium';
  if (labels.some((n) => n.includes('bug'))) return 'bug';
  return 'low';
}

export function priorityIcon(p) {
  const map = {
    critical: { icon: 'warning', color: 'text-error' },
    high: { icon: 'error', color: 'text-amber-500' },
    medium: { icon: 'info', color: 'text-primary' },
    bug: { icon: 'bug_report', color: 'text-error' },
    low: { icon: 'check_circle', color: 'text-emerald-600' },
  };
  return map[p] ?? map.low;
}

/**
 * Format an estimated USD cost value for display.
 * @param {number} usd
 * @returns {string} e.g. "< $0.001", "$0.0023", "$0.12", "$1.50"
export function formatCost(usd) {
  if (!usd || usd <= 0) return '';
  if (usd < 0.001) return '< $0.001';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}
