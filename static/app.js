'use strict';

// ── DOM refs ──────────────────────────────────────────────────────────────────
const fileInput      = document.getElementById('file-input');
const fileNameSpan   = document.getElementById('file-name');
const uploadBtn      = document.getElementById('upload-btn');

const pasteFilename  = document.getElementById('paste-filename');
const pasteContent   = document.getElementById('paste-content');
const pasteBtn       = document.getElementById('paste-btn');

const uploadStatus   = document.getElementById('upload-status');
const filesList      = document.getElementById('files-list');

const questionInput  = document.getElementById('question-input');
const askBtn         = document.getElementById('ask-btn');
const askStatus      = document.getElementById('ask-status');
const askModelSelect = document.getElementById('ask-model-select');

const answerSection  = document.getElementById('answer-section');
const answerText     = document.getElementById('answer-text');
const sourcesList    = document.getElementById('sources-list');

const liveSection    = document.getElementById('live-section');
const liveChunks     = document.getElementById('live-chunks');
const chunksTitle    = document.getElementById('chunks-title');
const chunksBody     = document.getElementById('chunks-body');
const chunksToggle   = document.getElementById('chunks-toggle');
const liveThinking   = document.getElementById('live-thinking');
const thinkingTitle  = document.getElementById('thinking-title');
const thinkingBody   = document.getElementById('thinking-body');
const thinkingToggle = document.getElementById('thinking-toggle');
const thinkingPulse  = document.getElementById('thinking-pulse');
const thinkingArrow  = document.getElementById('thinking-arrow');

// ── Tabs ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.remove('hidden');
    hideStatus(uploadStatus);
  });
});

// ── File picker label ─────────────────────────────────────────────────────────
fileInput.addEventListener('change', () => {
  fileNameSpan.textContent = fileInput.files[0]?.name || 'No file chosen';
});

// ── Status helpers ────────────────────────────────────────────────────────────
function showStatus(el, type, message) {
  el.className = `status ${type}`;
  if (type === 'loading') {
    el.innerHTML = `<div class="spinner"></div><span>${message}</span>`;
  } else {
    el.textContent = message;
  }
}

function hideStatus(el) {
  el.className = 'status hidden';
  el.textContent = '';
}

// ── Upload file ───────────────────────────────────────────────────────────────
uploadBtn.addEventListener('click', async () => {
  const file = fileInput.files[0];
  if (!file) {
    showStatus(uploadStatus, 'error', 'Please choose a file first.');
    return;
  }

  uploadBtn.disabled = true;
  showStatus(uploadStatus, 'loading', 'Uploading and indexing…');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) {
      showStatus(uploadStatus, 'error', `Error: ${data.detail || res.statusText}`);
    } else {
      showStatus(uploadStatus, 'success', `"${data.filename}" indexed — ${data.chunks} chunk(s).`);
      fileInput.value = '';
      fileNameSpan.textContent = 'No file chosen';
      loadFiles();
    }
  } catch (err) {
    showStatus(uploadStatus, 'error', `Network error: ${err.message}`);
  } finally {
    uploadBtn.disabled = false;
  }
});

// ── Paste text ────────────────────────────────────────────────────────────────
pasteBtn.addEventListener('click', async () => {
  const text = pasteContent.value.trim();
  if (!text) {
    showStatus(uploadStatus, 'error', 'Please paste some text first.');
    return;
  }

  let name = pasteFilename.value.trim();
  if (!name) name = `paste-${Date.now()}`;
  if (!name.endsWith('.txt')) name += '.txt';

  pasteBtn.disabled = true;
  showStatus(uploadStatus, 'loading', 'Indexing pasted text…');

  const blob = new Blob([text], { type: 'text/plain' });
  const file = new File([blob], name, { type: 'text/plain' });
  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) {
      showStatus(uploadStatus, 'error', `Error: ${data.detail || res.statusText}`);
    } else {
      showStatus(uploadStatus, 'success', `"${data.filename}" indexed — ${data.chunks} chunk(s).`);
      pasteContent.value = '';
      pasteFilename.value = '';
      loadFiles();
    }
  } catch (err) {
    showStatus(uploadStatus, 'error', `Network error: ${err.message}`);
  } finally {
    pasteBtn.disabled = false;
  }
});

// ── Indexed files ─────────────────────────────────────────────────────────────
async function loadFiles() {
  try {
    const res = await fetch('/files');
    const data = await res.json();
    filesList.innerHTML = '';
    if (!data.files || data.files.length === 0) {
      filesList.innerHTML = '<li class="files-empty">No files indexed yet.</li>';
      return;
    }
    data.files.forEach(name => {
      const li = document.createElement('li');
      li.innerHTML = `<span class="file-icon">📄</span><span>${escapeHtml(name)}</span>`;
      filesList.appendChild(li);
    });
  } catch {
    // silently ignore
  }
}

loadFiles();

const savedAskModel = localStorage.getItem('askModelTier');
if (savedAskModel && askModelSelect) askModelSelect.value = savedAskModel;
if (askModelSelect) {
  askModelSelect.addEventListener('change', () => {
    localStorage.setItem('askModelTier', askModelSelect.value);
  });
}

// ── Thinking toggle ───────────────────────────────────────────────────────────
thinkingToggle.addEventListener('click', () => {
  thinkingBody.classList.toggle('hidden');
  thinkingArrow.textContent = thinkingBody.classList.contains('hidden') ? '▼' : '▲';
});

// ── Chunks toggle ─────────────────────────────────────────────────────────────
chunksToggle.addEventListener('click', () => {
  chunksBody.classList.toggle('hidden');
  chunksToggle.querySelector('.toggle-arrow').textContent =
    chunksBody.classList.contains('hidden') ? '▼' : '▲';
});

// ── Ask (streaming) ───────────────────────────────────────────────────────────
askBtn.addEventListener('click', async () => {
  const question = questionInput.value.trim();
  if (!question) {
    showStatus(askStatus, 'error', 'Vui lòng nhập câu hỏi.');
    return;
  }

  const modelTier = askModelSelect?.value || 'pro';

  askBtn.disabled = true;
  hideStatus(askStatus);
  answerSection.style.display = 'none';
  answerText.textContent = '';
  sourcesList.innerHTML = '';

  resetLiveView();
  liveSection.style.display = 'block';
  liveSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await fetch('/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, model_tier: modelTier }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showStatus(askStatus, 'error', `Error: ${data.detail || res.statusText}`);
      liveSection.style.display = 'none';
      return;
    }

    answerSection.style.display = 'block';

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
        try {
          const event = JSON.parse(line.slice(6));
          handleStreamEvent(event);
        } catch {}
      }
    }
  } catch (err) {
    showStatus(askStatus, 'error', `Network error: ${err.message}`);
    liveSection.style.display = 'none';
  } finally {
    askBtn.disabled = false;
    answerText.classList.remove('streaming');
  }
});

// ── Stream event handler ──────────────────────────────────────────────────────
function handleStreamEvent(event) {
  switch (event.type) {
    case 'step':
      updateStep(event.step, event.status, event.message);
      if (event.step === 'generating' && event.status === 'active') {
        answerText.classList.add('streaming');
      }
      break;
    case 'chunks':
      renderLiveChunks(event.chunks);
      break;
    case 'thinking_start':
      liveThinking.style.display = 'block';
      thinkingBody.classList.remove('hidden');
      thinkingArrow.textContent = '▲';
      thinkingPulse.classList.add('active');
      thinkingTitle.textContent = 'Đang suy nghĩ...';
      thinkingBody.textContent = '';
      break;
    case 'thinking_token':
      thinkingBody.textContent += event.content;
      thinkingBody.scrollTop = thinkingBody.scrollHeight;
      break;
    case 'thinking_end':
      thinkingPulse.classList.remove('active');
      thinkingTitle.textContent = `Đã suy nghĩ xong (${thinkingBody.textContent.length} ký tự)`;
      thinkingBody.classList.add('hidden');
      thinkingArrow.textContent = '▼';
      break;
    case 'token':
      answerText.textContent += event.content;
      break;
    case 'done':
      answerText.classList.remove('streaming');
      renderSources(event.sources);
      answerSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      break;
    case 'error':
      showStatus(askStatus, 'error', event.message);
      break;
  }
}

// ── Live view helpers ─────────────────────────────────────────────────────────
function resetLiveView() {
  ['embedding', 'retrieval', 'generating'].forEach(step => {
    const el = document.getElementById(`step-${step}`);
    if (!el) return;
    el.querySelector('.step-icon').className = 'step-icon step-pending';
    document.getElementById(`msg-${step}`).textContent = '';
  });
  liveThinking.style.display = 'none';
  thinkingBody.textContent = '';
  thinkingBody.classList.add('hidden');
  thinkingPulse.classList.remove('active');
  liveChunks.style.display = 'none';
  chunksBody.innerHTML = '';
  chunksBody.classList.add('hidden');
  chunksToggle.querySelector('.toggle-arrow').textContent = '▼';
}

function updateStep(step, status, message) {
  const el = document.getElementById(`step-${step}`);
  if (!el) return;
  el.querySelector('.step-icon').className = `step-icon step-${status}`;
  document.getElementById(`msg-${step}`).textContent = message;
}

function renderLiveChunks(chunks) {
  liveChunks.style.display = 'block';
  chunksTitle.textContent = `${chunks.length} đoạn văn được tìm thấy`;
  chunksBody.innerHTML = '';
  chunks.forEach(c => {
    const div = document.createElement('div');
    div.className = 'chunk-card';
    div.innerHTML =
      `<div class="chunk-meta">` +
        `<span class="chunk-source">${escapeHtml(c.source)}</span>` +
        `<span class="chunk-idx">chunk ${c.chunk_index}</span>` +
        `<span class="chunk-score">${(c.score * 100).toFixed(1)}% khớp</span>` +
      `</div>` +
      `<div class="chunk-preview">${escapeHtml(c.preview)}</div>`;
    chunksBody.appendChild(div);
  });
}

function renderSources(sources) {
  sourcesList.innerHTML = '';
  if (sources && sources.length > 0) {
    groupSources(sources).forEach(({ source, chunks }) => {
      const li = document.createElement('li');
      li.title = source;
      li.innerHTML =
        `<span class="src-file">${escapeHtml(compactFileName(source))}</span>` +
        `<span class="src-chunks">${chunks.map(chunk => `<span class="src-chunk">#${chunk}</span>`).join('')}</span>`;
      sourcesList.appendChild(li);
    });
  } else {
    const li = document.createElement('li');
    li.textContent = 'No sources returned.';
    sourcesList.appendChild(li);
  }
}

function groupSources(sources = []) {
  const groups = new Map();

  sources.forEach(({ source, chunk_index }) => {
    const name = source || 'Unknown source';
    if (!groups.has(name)) groups.set(name, new Set());
    groups.get(name).add(chunk_index);
  });

  return Array.from(groups, ([source, chunkSet]) => ({
    source,
    chunks: Array.from(chunkSet).sort((a, b) => Number(a) - Number(b)),
  }));
}

function compactFileName(name, max = 62) {
  const text = String(name || 'Unknown source');
  if (text.length <= max) return text;

  const dot = text.lastIndexOf('.');
  const ext = dot > 0 && text.length - dot <= 8 ? text.slice(dot) : '';
  const base = ext ? text.slice(0, dot) : text;
  const head = Math.max(22, Math.floor((max - ext.length - 3) * 0.62));
  const tail = Math.max(12, max - ext.length - 3 - head);

  return `${base.slice(0, head)}...${base.slice(-tail)}${ext}`;
}

function escapeHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
