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

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  await refreshSessionList();
  const saved = localStorage.getItem('chatSessionId');
  if (saved) await loadSession(saved);
}

// ── Session list ──────────────────────────────────────────────────────────────
async function refreshSessionList() {
  try {
    const res = await fetch('/chat/sessions');
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
    localStorage.setItem('chatSessionId', sessionId);
    renderHistory(data.messages || []);
    setActiveSession(sessionId);
    if (data.last_usage) updateCtxBar(data.last_usage, data.context_window || 131072);
  } catch {}
}

// ── New chat ──────────────────────────────────────────────────────────────────
function startNewChat() {
  currentSessionId = null;
  localStorage.removeItem('chatSessionId');
  messagesEl.innerHTML = '';
  messagesEl.appendChild(welcomeEl);
  welcomeEl.style.display = 'flex';
  setActiveSession(null);
  ctxBar.style.display = 'none';
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
      bubbleEl.textContent = msg.content;
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

function buildChunksEl(chunks) {
  const el = document.createElement('div');
  el.className = 'msg-chunks';
  el.innerHTML =
    `<div class="chunks-header">` +
      `<span>${chunks.length} đoạn văn tìm được</span>` +
      `<span class="toggle-icon">▼</span>` +
    `</div>` +
    `<div class="chunks-list hidden"></div>`;

  const list   = el.querySelector('.chunks-list');
  const header = el.querySelector('.chunks-header');
  const icon   = el.querySelector('.toggle-icon');

  chunks.forEach(c => {
    const row = document.createElement('div');
    row.className = 'chunk-row';
    row.innerHTML =
      `<div class="chunk-row-meta">` +
        `<span class="c-src">${esc(c.source)}</span>` +
        `<span class="c-idx">chunk ${c.chunk_index}</span>` +
        `<span class="c-score">${(c.score * 100).toFixed(1)}%</span>` +
      `</div>` +
      `<div class="chunk-row-preview">${esc(c.preview)}</div>`;
    list.appendChild(row);
  });

  header.addEventListener('click', () => {
    list.classList.toggle('hidden');
    icon.textContent = list.classList.contains('hidden') ? '▼' : '▲';
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

  let thinkingEl   = null;
  let thinkContent = null;
  let thinkingText = '';
  let thinkingActive = false;

  try {
    const res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, message: text }),
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

          case 'chunks':
            if (statusEl.parentNode) {
              const chunksEl = buildChunksEl(event.chunks);
              bodyEl.insertBefore(chunksEl, bubbleEl);
            }
            break;

          case 'thinking_start':
            thinkingActive = true;
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
              thinkingActive = false;
              thinkingEl.querySelector('.thinking-dot').classList.remove('active');
              thinkingEl.querySelector('.thinking-label').textContent =
                `Đã suy nghĩ (${thinkingText.length} ký tự)`;
              thinkContent.classList.add('hidden');
              thinkingEl.querySelector('.thinking-toggle-icon').textContent = '▼';
            }
            break;

          case 'token':
            if (bubbleEl.style.display === 'none') {
              if (statusEl.parentNode) statusEl.remove();
              bubbleEl.style.display = 'block';
              bubbleEl.classList.add('streaming');
            }
            bubbleEl.textContent += event.content;
            scrollBottom();
            break;

          case 'done':
            bubbleEl.classList.remove('streaming');
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
