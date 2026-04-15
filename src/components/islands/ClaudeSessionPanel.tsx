/**
 * ClaudeSessionPanel — Preact island
 *
 * Slide-over panel for persistent, project-scoped Claude Code CLI sessions.
 * Each session spawns a real `claude` subprocess per turn, streams structured
 * JSON events over WebSocket, and persists the Claude session ID for --resume.
 *
 * WebSocket protocol (server → client):
 *   {type:"system",     subtype:"init", session_id:"..."}   ← CLI session ID
 *   {type:"assistant",  message:{content:[...]}}
 *   {type:"tool_use",   name:"Read",    input:{...}}
 *   {type:"tool_result",content:[...]}
 *   {type:"result",     subtype:"success", result:"...", usage:{...}}
 *   {type:"user",       content:"..."}                      ← echoed user msg
 *   {type:"error",      message:"..."}
 *   {type:"phoenix_status", status:"running"|"idle"}
 */

import { useEffect, useRef, useState } from 'preact/hooks';
import { AGENT_BASE_URL } from '../../lib/config.js';
import { claudeSessionOpenSignal } from '../../lib/signals.js';
import { getTerminalConfig } from '../../lib/agents.js';
import { TERMINAL_MODES } from '../../lib/constants.js';

// ── Constants ─────────────────────────────────────────────────────────────────

const WS_BASE = AGENT_BASE_URL.replace(/^http/, 'ws');
const LS_KEY = 'pnx_claude_sessions';
const MAX_RECONNECT = 3;

// ── Types ─────────────────────────────────────────────────────────────────────

interface SessionMeta {
  sessionId: string;
  repo: string;
  lastActivity: number;
}

interface ChatMessage {
  id: string;
  type: 'user' | 'assistant' | 'tool_use' | 'tool_result' | 'result' | 'error' | 'system';
  content: string;
  toolName?: string;
  toolInput?: unknown;
  usage?: { input_tokens?: number; output_tokens?: number };
  ts: number;
}

interface SessionSummary {
  id: string;
  repo: string;
  status: string;
  updated_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function loadStoredSessions(): SessionMeta[] {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveStoredSession(meta: SessionMeta): void {
  try {
    const list = loadStoredSessions().filter(s => s.sessionId !== meta.sessionId);
    list.unshift(meta);
    localStorage.setItem(LS_KEY, JSON.stringify(list.slice(0, 20)));
  } catch {}
}

function extractText(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((c: any) => (c?.type === 'text' ? c.text : typeof c === 'string' ? c : ''))
      .join('');
  }
  return JSON.stringify(content ?? '');
}

// ── Tool card component ───────────────────────────────────────────────────────

function ToolCard({ msg }: { msg: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const isResult = msg.type === 'tool_result';
  const accent = isResult ? '#16a34a' : '#b45309';
  const bg = isResult ? '#f0fdf4' : '#fffbeb';

  return (
    <div
      style={{
        background: bg,
        border: `1px solid ${accent}30`,
        borderRadius: 8,
        margin: '4px 0',
        overflow: 'hidden',
      }}
    >
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          width: '100%',
          padding: '6px 10px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: accent,
          fontSize: 11,
          fontWeight: 600,
          textAlign: 'left',
        }}
      >
        <span class="material-symbols-outlined" style={{ fontSize: 14 }}>
          {isResult ? 'output' : 'build'}
        </span>
        {isResult ? `Result` : `Tool: ${msg.toolName}`}
        <span class="material-symbols-outlined" style={{ fontSize: 14, marginLeft: 'auto' }}>
          {open ? 'expand_less' : 'expand_more'}
        </span>
      </button>
      {open && (
        <pre
          style={{
            margin: 0,
            padding: '8px 10px',
            fontSize: 10,
            overflowX: 'auto',
            maxHeight: 200,
            overflowY: 'auto',
            borderTop: `1px solid ${accent}20`,
            color: '#374151',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}
        >
          {msg.type === 'tool_use'
            ? JSON.stringify(msg.toolInput, null, 2)
            : msg.content}
        </pre>
      )}
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: ChatMessage }) {
  if (msg.type === 'tool_use' || msg.type === 'tool_result') {
    return <ToolCard msg={msg} />;
  }

  if (msg.type === 'result') {
    return (
      <div
        style={{
          fontSize: 10,
          color: '#6b7280',
          borderTop: '1px solid #e5e7eb',
          padding: '6px 0',
          margin: '4px 0 0',
        }}
      >
        {msg.usage && (
          <span>
            Tokens: {(msg.usage.input_tokens ?? 0) + (msg.usage.output_tokens ?? 0)}
          </span>
        )}
      </div>
    );
  }

  if (msg.type === 'system') return null;

  const isUser = msg.type === 'user';
  const isError = msg.type === 'error';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: isUser ? 'flex-end' : 'flex-start',
        margin: '4px 0',
      }}
    >
      <div
        style={{
          maxWidth: '90%',
          padding: '8px 12px',
          borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
          background: isError ? '#fff1f2' : isUser ? '#1d4ed8' : '#f3f4f6',
          color: isError ? '#be123c' : isUser ? '#fff' : '#111827',
          fontSize: 13,
          lineHeight: 1.5,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {msg.content}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ClaudeSessionPanel() {
  const isOpen = claudeSessionOpenSignal.value;

  const [sessionId, setSessionId]         = useState<string | null>(null);
  const [messages, setMessages]           = useState<ChatMessage[]>([]);
  const [status, setStatus]               = useState<'idle' | 'running' | 'error'>('idle');
  const [sessions, setSessions]           = useState<SessionSummary[]>([]);
  const [input, setInput]                 = useState('');
  const [repo, setRepo]                   = useState('');
  const [terminalConfig, setTerminalConfigState] = useState(getTerminalConfig);

  const wsRef        = useRef<WebSocket | null>(null);
  const reconnectRef = useRef(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Read active repo from the board state (set by main.js).
  useEffect(() => {
    function syncRepo() {
      const select = document.getElementById('repo-switcher-select') as HTMLSelectElement | null;
      if (select?.value) setRepo(select.value);
    }
    syncRepo();
    const interval = setInterval(syncRepo, 1000);
    return () => clearInterval(interval);
  }, []);

  // Re-read terminal config whenever panel opens (user may have changed it in Settings).
  useEffect(() => {
    if (!isOpen) return;
    setTerminalConfigState(getTerminalConfig());
    fetchSessions();
  }, [isOpen, repo]);

  // Auto-scroll to bottom on new messages.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Close WebSocket on unmount.
  useEffect(() => {
    return () => wsRef.current?.close();
  }, []);

  if (!isOpen) return null;

  // ── Session management ─────────────────────────────────────────────────────

  async function fetchSessions() {
    try {
      const url = repo
        ? `${AGENT_BASE_URL}/claude-sessions?repo=${encodeURIComponent(repo)}`
        : `${AGENT_BASE_URL}/claude-sessions`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions ?? []);
      }
    } catch {}
  }

  async function startNewSession() {
    if (!repo) {
      alert('Load a repository first');
      return;
    }
    try {
      const cfg = getTerminalConfig();
      const params = new URLSearchParams({
        repo,
        project_path: `/tmp/claude-session`,
        mode: cfg.mode,
        ...(cfg.model   ? { model:   cfg.model   } : {}),
        ...(cfg.apiKey  ? { api_key: cfg.apiKey  } : {}),
      });
      const res = await fetch(`${AGENT_BASE_URL}/claude-sessions?${params}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const id = data.session_id as string;
      setMessages([]);
      await connectToSession(id);
      saveStoredSession({ sessionId: id, repo, lastActivity: Date.now() });
      await fetchSessions();
    } catch (e: any) {
      setStatus('error');
      addMessage({ type: 'error', content: `Failed to create session: ${e.message}` });
    }
  }

  async function connectToSession(id: string) {
    wsRef.current?.close();
    setSessionId(id);
    setStatus('idle');
    reconnectRef.current = 0;
    openWs(id);
  }

  function openWs(id: string) {
    const ws = new WebSocket(`${WS_BASE}/claude-sessions/${id}/ws`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const event = JSON.parse(ev.data);
        handleEvent(event);
      } catch {}
    };

    ws.onerror = () => setStatus('error');

    ws.onclose = () => {
      if (reconnectRef.current < MAX_RECONNECT) {
        reconnectRef.current++;
        setTimeout(() => openWs(id), 2000 * reconnectRef.current);
      }
    };
  }

  function handleEvent(event: any) {
    const type = event.type as string;

    if (type === 'phoenix_status') {
      setStatus(event.status === 'running' ? 'running' : 'idle');
      return;
    }

    if (type === 'user') {
      addMessage({ type: 'user', content: event.content ?? '' });
      return;
    }

    if (type === 'assistant') {
      const text = extractText(event.message?.content ?? event.content ?? '');
      if (text) addMessage({ type: 'assistant', content: text });
      return;
    }

    if (type === 'tool_use') {
      addMessage({
        type: 'tool_use',
        content: '',
        toolName: event.name,
        toolInput: event.input,
      });
      return;
    }

    if (type === 'tool_result') {
      const text = extractText(event.content ?? '');
      addMessage({ type: 'tool_result', content: text });
      return;
    }

    if (type === 'result') {
      addMessage({
        type: 'result',
        content: event.result ?? '',
        usage: event.usage,
      });
      return;
    }

    if (type === 'error') {
      addMessage({ type: 'error', content: event.message ?? 'Unknown error' });
      setStatus('error');
      return;
    }
  }

  function addMessage(partial: Omit<ChatMessage, 'id' | 'ts'>) {
    const msg: ChatMessage = {
      id: `${Date.now()}-${Math.random()}`,
      ts: Date.now(),
      ...partial,
    };
    setMessages(prev => [...prev, msg]);
  }

  // ── Input handling ─────────────────────────────────────────────────────────

  function sendMessage() {
    const content = input.trim();
    if (!content || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (status === 'running') return;
    wsRef.current.send(JSON.stringify({ type: 'message', content }));
    setInput('');
    // Resize textarea back
    const ta = document.getElementById('claude-session-input') as HTMLTextAreaElement | null;
    if (ta) ta.style.height = 'auto';
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function handleInputChange(e: Event) {
    const ta = e.target as HTMLTextAreaElement;
    setInput(ta.value);
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const isConnected = wsRef.current?.readyState === WebSocket.OPEN;
  const canSend = isConnected && status === 'idle' && input.trim().length > 0;

  return (
    <>
      {/* Overlay */}
      <div
        onClick={() => { claudeSessionOpenSignal.value = false; }}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.35)',
          zIndex: 1000,
        }}
      />

      {/* Panel */}
      <div
        style={{
          position: 'fixed', top: 0, right: 0,
          width: 480, maxWidth: '100vw', height: '100vh',
          background: '#fff',
          borderLeft: '1px solid #e5e7eb',
          boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
          zIndex: 1001,
          display: 'flex',
          flexDirection: 'column',
          fontFamily: 'inherit',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 14px',
            borderBottom: '1px solid #e5e7eb',
            background: '#f9fafb',
            flexShrink: 0,
          }}
        >
          {/* Status dot */}
          <div
            style={{
              width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
              background: status === 'running' ? '#16a34a'
                : status === 'error' ? '#ef4444'
                : isConnected ? '#3b82f6'
                : '#9ca3af',
              boxShadow: status === 'running' ? '0 0 6px #16a34a' : 'none',
            }}
          />
          <span style={{ fontWeight: 700, fontSize: 13, color: '#111827' }}>
            Claude Session
          </span>
          {repo && (
            <span
              style={{
                fontSize: 11, padding: '1px 6px', borderRadius: 4,
                background: '#dbeafe', color: '#1d4ed8', fontFamily: 'monospace',
              }}
            >
              {repo}
            </span>
          )}
          {/* Mode badge — click opens Settings → Terminal */}
          <button
            onClick={() => document.dispatchEvent(new CustomEvent('open-settings-panel', { detail: { section: 'terminal' } }))}
            title="Configure terminal agent"
            style={{
              fontSize: 10, padding: '1px 6px', borderRadius: 4,
              background: terminalConfig.mode === 'claude_code' ? '#f0fdf4' : '#fef9c3',
              color:      terminalConfig.mode === 'claude_code' ? '#16a34a' : '#854d0e',
              border: 'none', cursor: 'pointer', fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 3,
            }}
          >
            <span class="material-symbols-outlined" style={{ fontSize: 11 }}>
              {TERMINAL_MODES.find(m => m.id === terminalConfig.mode)?.icon ?? 'terminal'}
            </span>
            {TERMINAL_MODES.find(m => m.id === terminalConfig.mode)?.label ?? 'Claude Code'}
          </button>
          <div style={{ flex: 1 }} />
          <button
            onClick={() => { claudeSessionOpenSignal.value = false; }}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 28, height: 28, border: 'none', borderRadius: 6,
              background: 'transparent', cursor: 'pointer', color: '#6b7280',
            }}
            title="Close"
          >
            <span class="material-symbols-outlined" style={{ fontSize: 18 }}>close</span>
          </button>
        </div>

        {/* Controls bar */}
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 14px',
            borderBottom: '1px solid #f3f4f6',
            flexShrink: 0,
          }}
        >
          <button
            onClick={startNewSession}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              padding: '5px 10px', border: 'none', borderRadius: 6,
              background: '#1d4ed8', color: '#fff',
              fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}
          >
            <span class="material-symbols-outlined" style={{ fontSize: 14 }}>add</span>
            New Session
          </button>

          {sessions.length > 0 && (
            <select
              onChange={async (e) => {
                const id = (e.target as HTMLSelectElement).value;
                if (id) {
                  setMessages([]);
                  await connectToSession(id);
                }
              }}
              style={{
                padding: '5px 8px', borderRadius: 6,
                border: '1px solid #d1d5db', background: '#fff',
                fontSize: 12, color: '#374151', cursor: 'pointer',
              }}
            >
              <option value="">
                {sessionId
                  ? `Session …${sessionId.slice(-8)}`
                  : 'Select session…'}
              </option>
              {sessions.map(s => (
                <option key={s.id} value={s.id} selected={s.id === sessionId}>
                  {s.id.slice(0, 8)}… · {s.repo} · {s.status}
                </option>
              ))}
            </select>
          )}

          {status === 'running' && (
            <span
              style={{ fontSize: 11, color: '#16a34a', display: 'flex', alignItems: 'center', gap: 4 }}
            >
              <span
                class="material-symbols-outlined animate-spin"
                style={{ fontSize: 14 }}
              >
                autorenew
              </span>
              Running…
            </span>
          )}
        </div>

        {/* Message list */}
        <div
          style={{
            flex: 1, overflowY: 'auto', padding: '12px 14px',
            display: 'flex', flexDirection: 'column',
          }}
        >
          {messages.length === 0 && !sessionId && (
            <div
              style={{
                flex: 1, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                color: '#9ca3af', textAlign: 'center', gap: 12,
              }}
            >
              <span class="material-symbols-outlined" style={{ fontSize: 48, color: '#d1d5db' }}>
                terminal
              </span>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                  Claude Code Session
                </div>
                <div style={{ fontSize: 12, maxWidth: 300, lineHeight: 1.5 }}>
                  Start a persistent interactive session with full project context
                  and conversation history.
                </div>
              </div>
            </div>
          )}

          {messages.length === 0 && sessionId && (
            <div
              style={{
                color: '#9ca3af', fontSize: 12, textAlign: 'center',
                marginTop: 20,
              }}
            >
              Session connected. Send a message to begin.
            </div>
          )}

          {messages.map(msg => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div
          style={{
            padding: '10px 14px',
            borderTop: '1px solid #e5e7eb',
            background: '#f9fafb',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              display: 'flex', alignItems: 'flex-end', gap: 8,
              background: '#fff', border: '1px solid #d1d5db',
              borderRadius: 10, padding: '8px 10px',
              ...(isConnected ? { borderColor: '#3b82f6' } : {}),
            }}
          >
            <span style={{ color: '#3b82f6', fontFamily: 'monospace', fontSize: 14, lineHeight: '20px' }}>
              &gt;
            </span>
            <textarea
              id="claude-session-input"
              value={input}
              onInput={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={
                !sessionId
                  ? 'Start a session first…'
                  : status === 'running'
                  ? 'Claude is thinking…'
                  : 'Message Claude… (Enter to send, Shift+Enter for newline)'
              }
              disabled={!isConnected || status === 'running'}
              rows={1}
              style={{
                flex: 1, background: 'transparent', border: 'none', outline: 'none',
                fontSize: 13, lineHeight: '20px', resize: 'none',
                color: '#111827', minHeight: 20, maxHeight: 120,
                fontFamily: 'inherit',
              }}
            />
            <button
              onClick={sendMessage}
              disabled={!canSend}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 30, height: 30, border: 'none', borderRadius: 8,
                background: canSend ? '#1d4ed8' : '#e5e7eb',
                color: canSend ? '#fff' : '#9ca3af',
                cursor: canSend ? 'pointer' : 'not-allowed',
                flexShrink: 0,
                transition: 'background 0.15s',
              }}
              title="Send (Enter)"
            >
              <span class="material-symbols-outlined" style={{ fontSize: 16 }}>send</span>
            </button>
          </div>
          <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 4, paddingLeft: 2 }}>
            Shift+Enter for new line · sessions persist across page reloads
          </div>
        </div>
      </div>
    </>
  );
}
