'use strict';

// ── DOM refs ──────────────────────────────────────────────────────────────────
const sessionListEl = document.getElementById('session-list');
const newChatBtn    = document.getElementById('new-chat-btn');
const messagesEl    = document.getElementById('messages');
const welcomeEl     = document.getElementById('welcome');
const chatInput     = document.getElementById('chat-input');
const sendBtn       = document.getElementById('send-btn');
const ctxBar        = document.getElementById('ctx-bar');
const ctxTokens     = document.getElementById('ctx-tokens');
const ctxLimit      = document.getElementById('ctx-limit');
const ctxPct        = document.getElementById('ctx-pct');
const ctxFill       = document.getElementById('ctx-fill');
const ctxNewBtn     = document.getElementById('ctx-new-btn');

// ── State ─────────────────────────────────────────────────────────────────────
let currentSessionId = null;
let isStreaming       = false;

const urlParams  = new URLSearchParams(window.location.search);
const projectId  = urlParams.get('project_id') || null;
const initSession = urlParams.get('session_id') || null;

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  if (projectId) showProjectBanner();
  await refreshSessionList();
  if (initSession) {
    await loadSession(initSession);
  } else if (!projectId) {
    const saved = localStorage.getItem('chatSessionId');
    if (saved) await loadSession(saved);
  }
}

function showProjectBanner() {
  const banner = document.getElementById('project-banner');
  const backLink = document.getElementById('project-back-link');
  if (!banner) return;
  banner.style.display = 'flex';
  if (backLink) {
    backLink.style.display = 'block';
    backLink.href = `/p/${projectId}`;
  }
  fetch(`/projects/${projectId}`)
    .then(r => r.ok ? r.json() : null)
    .then(proj => {
      if (proj) {
        banner.querySelector('.banner-name').textContent = proj.name;
        if (backLink) backLink.textContent = `← ${proj.name}`;
      }
    })
    .catch(() => {});
}

// ── Session list ──────────────────────────────────────────────────────────────
async function refreshSessionList() {
  try {
    const url = projectId ? `/chat/sessions?project_id=${projectId}` : '/chat/sessions';
    const res = await fetch(url);
    const data = await res.json();
    renderSessionList(data.sessions || []);
  } catch {}
}

function renderSessionList(sessions) {
  sessionListEl.innerHTML = '';
  if (!sessions.length) {
    sessionListEl.innerHTML = '<div class="session-empty">No chats yet.</div>';
    return;
  }
  sessions.forEach(s => {
    const item = document.createElement('div');
    item.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
    item.dataset.id = s.id;

    const date = new Date(s.created_at);
    const dateStr = date.toLocaleDateString('vi-VN', { month: 'short', day: 'numeric' });

    item.innerHTML =
      `<div class="session-info">` +
        `<div class="session-title">${esc(s.title)}</div>` +
        `<div class="session-meta">${dateStr} · ${s.message_count} tin</div>` +
      `</div>` +
      `<button class="session-del" title="Xóa" data-id="${s.id}">×</button>`;

    item.addEventListener('click', e => {
      if (e.target.classList.contains('session-del')) return;
      loadSession(s.id);
    });

    item.querySelector('.session-del').addEventListener('click', async e => {
      e.stopPropagation();
      if (!confirm('Xóa cuộc trò chuyện này?')) return;
      await fetch(`/chat/sessions/${s.id}`, { method: 'DELETE' });
      if (s.id === currentSessionId) startNewChat();
      await refreshSessionList();
    });

    sessionListEl.appendChild(item);
  });
}

function setActiveSession(id) {
  document.querySelectorAll('.session-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id === id);
  });
}

// ── Load session ──────────────────────────────────────────────────────────────
async function loadSession(sessionId) {
  try {
    const res = await fetch(`/chat/sessions/${sessionId}`);
    if (!res.ok) { startNewChat(); return; }
    const data = await res.json();
    currentSessionId = sessionId;
    if (!projectId) localStorage.setItem('chatSessionId', sessionId);
    renderHistory(data.messages || []);
    setActiveSession(sessionId);
    if (data.last_usage) updateCtxBar(data.last_usage, data.context_window || 131072);
  } catch {}
}

// ── New chat ──────────────────────────────────────────────────────────────────
function startNewChat() {
  currentSessionId = null;
  if (!projectId) localStorage.removeItem('chatSessionId');
  messagesEl.innerHTML = '';
  messagesEl.appendChild(welcomeEl);
  welcomeEl.style.display = 'flex';
  setActiveSession(null);
  ctxBar.style.display = 'none';
  if (projectId) {
    const u = new URL(window.location.href);
    u.searchParams.delete('session_id');
    window.history.replaceState({}, '', u.toString());
  }
}

// ── Render history ────────────────────────────────────────────────────────────
function renderHistory(messages) {
  messagesEl.innerHTML = '';
  welcomeEl.style.display = 'none';

  messages.forEach(msg => {
    if (msg.role === 'user') {
      appendUserBubble(msg.content);
    } else if (msg.role === 'assistant') {
      const { bodyEl } = appendAssistantBubble();
      const statusEl = bodyEl.querySelector('.msg-status');
      if (statusEl) statusEl.remove();

      if (msg.thinking) {
        const thinkEl = buildThinkingEl(msg.thinking, false);
        bodyEl.insertBefore(thinkEl, bodyEl.querySelector('.msg-bubble'));
      }

      const bubbleEl = bodyEl.querySelector('.msg-bubble');
      bubbleEl.innerHTML = renderMarkdown(msg.content);
      bubbleEl.style.display = 'block';

      if (msg.sources?.length) appendSources(bodyEl, msg.sources);
    }
  });

  scrollBottom();
}

// ── Bubble builders ───────────────────────────────────────────────────────────
function appendUserBubble(text) {
  welcomeEl.style.display = 'none';
  const msg = document.createElement('div');
  msg.className = 'msg user';
  msg.innerHTML =
    `<div class="msg-avatar">U</div>` +
    `<div class="msg-body"><div class="msg-bubble">${esc(text)}</div></div>`;
  messagesEl.appendChild(msg);
  scrollBottom();
}

function appendAssistantBubble() {
  welcomeEl.style.display = 'none';
  const msg = document.createElement('div');
  msg.className = 'msg assistant';
  msg.innerHTML =
    `<div class="msg-avatar">AI</div>` +
    `<div class="msg-body">` +
      `<div class="msg-status"><div class="mini-spinner"></div><span class="status-text">Đang xử lý...</span></div>` +
      `<div class="msg-bubble" style="display:none;"></div>` +
      `<div class="msg-sources" style="display:none;"></div>` +
    `</div>`;
  messagesEl.appendChild(msg);
  scrollBottom();
  return { msgEl: msg, bodyEl: msg.querySelector('.msg-body') };
}

function buildThinkingEl(initialText, active) {
  const el = document.createElement('div');
  el.className = 'msg-thinking';
  el.innerHTML =
    `<div class="thinking-header">` +
      `<span class="thinking-dot${active ? ' active' : ''}"></span>` +
      `<span class="thinking-label">${active ? 'Đang suy nghĩ...' : `Đã suy nghĩ (${initialText.length} ký tự)`}</span>` +
      `<span class="thinking-toggle-icon">▼</span>` +
    `</div>` +
    `<div class="thinking-content${active ? '' : ' hidden'}">${esc(initialText)}</div>`;

  const header  = el.querySelector('.thinking-header');
  const content = el.querySelector('.thinking-content');
  const icon    = el.querySelector('.thinking-toggle-icon');

  header.addEventListener('click', () => {
    content.classList.toggle('hidden');
    icon.textContent = content.classList.contains('hidden') ? '▼' : '▲';
  });

  return el;
}

function appendSources(bodyEl, sources) {
  const sourcesEl = bodyEl.querySelector('.msg-sources');
  sourcesEl.style.display = 'flex';
  sources.forEach(({ source, chunk_index }) => {
    const chip = document.createElement('span');
    chip.className = 'source-chip';
    chip.innerHTML = `${esc(source)} <span class="src-idx">#${chunk_index}</span>`;
    sourcesEl.appendChild(chip);
  });
}

// ── Markdown renderer ─────────────────────────────────────────────────────────
function renderMarkdown(text) {
  if (typeof marked === 'undefined') return esc(text);
  return marked.parse(text);
}

// ── Send ──────────────────────────────────────────────────────────────────────
async function sendMessage() {
  if (isStreaming) return;
  const text = chatInput.value.trim();
  if (!text) return;

  chatInput.value = '';
  chatInput.style.height = 'auto';
  isStreaming = true;
  sendBtn.disabled = true;

  appendUserBubble(text);
  const { bodyEl } = appendAssistantBubble();

  const statusEl   = bodyEl.querySelector('.msg-status');
  const statusText = bodyEl.querySelector('.status-text');
  const bubbleEl   = bodyEl.querySelector('.msg-bubble');

  // thinking state
  let thinkingEl   = null;
  let thinkContent = null;
  let thinkingText = '';

  // search trace state
  let traceEl         = null;
  let traceStatusEl   = null;
  let traceDetailEl   = null;
  let traceQueryCount = 0;
  let traceChunkCount = 0;
  let lastQueryRowEl  = null;

  // response accumulator for markdown rendering
  let responseText = '';

  function ensureTrace() {
    if (traceEl) return;
    traceEl = document.createElement('div');
    traceEl.className = 'msg-search-trace active';
    traceEl.innerHTML =
      `<div class="trace-header">` +
        `<span class="trace-dot"></span>` +
        `<span class="trace-status">Đang tra cứu...</span>` +
        `<span class="trace-toggle">▼</span>` +
      `</div>` +
      `<div class="trace-detail hidden"></div>`;
    traceStatusEl = traceEl.querySelector('.trace-status');
    traceDetailEl = traceEl.querySelector('.trace-detail');
    const hdr  = traceEl.querySelector('.trace-header');
    const icon = traceEl.querySelector('.trace-toggle');
    hdr.addEventListener('click', () => {
      traceDetailEl.classList.toggle('hidden');
      icon.textContent = traceDetailEl.classList.contains('hidden') ? '▼' : '▲';
    });
    bodyEl.insertBefore(traceEl, bubbleEl);
  }

  function finalizeTrace() {
    if (!traceEl) return;
    traceEl.classList.remove('active');
    if (traceQueryCount > 0) {
      traceStatusEl.textContent =
        `${traceQueryCount} truy vấn · ${traceChunkCount} đoạn tìm được`;
    }
    traceDetailEl.classList.add('hidden');
    traceEl.querySelector('.trace-toggle').textContent = '▼';
  }

  try {
    const res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, message: text, project_id: projectId }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      statusEl.remove();
      bubbleEl.style.display = 'block';
      bubbleEl.textContent = `Lỗi: ${data.detail || res.statusText}`;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let event;
        try { event = JSON.parse(line.slice(6)); } catch { continue; }

        switch (event.type) {

          case 'session':
            currentSessionId = event.session_id;
            localStorage.setItem('chatSessionId', currentSessionId);
            break;

          case 'step':
            if (statusEl.parentNode) statusText.textContent = event.message;
            break;

          case 'activity':
            ensureTrace();
            traceStatusEl.textContent = event.message;
            if (statusEl.parentNode) statusText.textContent = event.message;
            scrollBottom();
            break;

          case 'tool_call': {
            ensureTrace();
            traceQueryCount++;
            traceDetailEl.classList.remove('hidden');
            traceEl.querySelector('.trace-toggle').textContent = '▲';
            const qRow = document.createElement('div');
            qRow.className = 'trace-query-row';
            qRow.innerHTML =
              `<span class="trace-q-icon">🔍</span>` +
              `<span class="trace-q-text">${esc(event.query)}</span>` +
              `<span class="trace-q-count"></span>`;
            traceDetailEl.appendChild(qRow);
            lastQueryRowEl = qRow;
            if (statusEl.parentNode) statusText.textContent = `Đang tìm kiếm...`;
            scrollBottom();
            break;
          }

          case 'chunks':
            if (lastQueryRowEl) {
              traceChunkCount += event.chunks.length;
              lastQueryRowEl.querySelector('.trace-q-count').textContent =
                `${event.chunks.length} đoạn`;
            }
            scrollBottom();
            break;

          case 'thinking_start':
            thinkingEl = buildThinkingEl('', true);
            thinkContent = thinkingEl.querySelector('.thinking-content');
            bodyEl.insertBefore(thinkingEl, bubbleEl);
            scrollBottom();
            break;

          case 'thinking_token':
            if (thinkContent) {
              thinkingText += event.content;
              thinkContent.textContent = thinkingText;
              thinkContent.scrollTop = thinkContent.scrollHeight;
              scrollBottom();
            }
            break;

          case 'thinking_end':
            if (thinkingEl) {
              thinkingEl.querySelector('.thinking-dot').classList.remove('active');
              thinkingEl.querySelector('.thinking-label').textContent =
                `Đã suy nghĩ (${thinkingText.length} ký tự)`;
              thinkingEl.querySelector('.thinking-content').classList.add('hidden');
              thinkingEl.querySelector('.thinking-toggle-icon').textContent = '▼';
            }
            break;

          case 'token':
            if (bubbleEl.style.display === 'none') {
              if (statusEl.parentNode) statusEl.remove();
              bubbleEl.style.display = 'block';
              bubbleEl.classList.add('streaming');
            }
            responseText += event.content;
            bubbleEl.innerHTML = renderMarkdown(responseText);
            scrollBottom();
            break;

          case 'done':
            bubbleEl.classList.remove('streaming');
            finalizeTrace();
            if (responseText) bubbleEl.innerHTML = renderMarkdown(responseText);
            if (event.sources?.length) appendSources(bodyEl, event.sources);
            if (event.usage) updateCtxBar(event.usage, event.context_window || 131072);
            await refreshSessionList();
            setActiveSession(currentSessionId);
            break;

          case 'error':
            if (statusEl.parentNode) statusEl.remove();
            bubbleEl.style.display = 'block';
            bubbleEl.textContent = `Lỗi: ${event.message}`;
            break;
        }
      }
    }
  } catch (err) {
    if (statusEl.parentNode) statusEl.remove();
    bubbleEl.style.display = 'block';
    bubbleEl.textContent = `Network error: ${err.message}`;
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    bubbleEl.classList.remove('streaming');
  }
}

// ── Input events ──────────────────────────────────────────────────────────────
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + 'px';
});

sendBtn.addEventListener('click', sendMessage);
newChatBtn.addEventListener('click', startNewChat);

// ── Context bar ───────────────────────────────────────────────────────────────
function updateCtxBar(usage, contextWindow) {
  if (!usage) return;
  const used = usage.total_tokens;
  const pct  = used / contextWindow * 100;
  const tier = pct >= 80 ? 'red' : pct >= 60 ? 'yellow' : 'green';
  const remaining = 100 - pct;

  ctxBar.style.display = 'block';
  ctxTokens.textContent = used.toLocaleString('vi-VN');
  ctxLimit.textContent  = Math.round(contextWindow / 1024) + 'K';

  ctxPct.className = `ctx-pct ${tier}`;
  ctxPct.textContent = `còn ${remaining.toFixed(0)}%`;

  ctxFill.className = `ctx-fill ${tier}`;
  ctxFill.style.width = Math.min(pct, 100).toFixed(1) + '%';

  ctxNewBtn.style.display = pct >= 80 ? 'inline-block' : 'none';
}

ctxNewBtn.addEventListener('click', startNewChat);

// ── Utils ─────────────────────────────────────────────────────────────────────
function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Start ─────────────────────────────────────────────────────────────────────
init();
