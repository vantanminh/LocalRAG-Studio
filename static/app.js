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

const answerSection  = document.getElementById('answer-section');
const answerText     = document.getElementById('answer-text');
const sourcesList    = document.getElementById('sources-list');

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

// ── Ask ───────────────────────────────────────────────────────────────────────
askBtn.addEventListener('click', async () => {
  const question = questionInput.value.trim();
  if (!question) {
    showStatus(askStatus, 'error', 'Please enter a question.');
    return;
  }

  askBtn.disabled = true;
  hideStatus(askStatus);
  answerSection.style.display = 'none';
  showStatus(askStatus, 'loading', 'Retrieving context and generating answer…');

  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) {
      showStatus(askStatus, 'error', `Error: ${data.detail || res.statusText}`);
    } else {
      hideStatus(askStatus);
      renderAnswer(data.answer, data.sources);
    }
  } catch (err) {
    showStatus(askStatus, 'error', `Network error: ${err.message}`);
  } finally {
    askBtn.disabled = false;
  }
});

// ── Render answer ─────────────────────────────────────────────────────────────
function renderAnswer(answer, sources) {
  answerText.textContent = answer;

  sourcesList.innerHTML = '';
  if (sources && sources.length > 0) {
    sources.forEach(({ source, chunk_index }) => {
      const li = document.createElement('li');
      li.innerHTML =
        `<span class="src-file">${escapeHtml(source)}</span>` +
        `<span class="src-chunk">chunk ${chunk_index}</span>`;
      sourcesList.appendChild(li);
    });
  } else {
    const li = document.createElement('li');
    li.textContent = 'No sources returned.';
    sourcesList.appendChild(li);
  }

  answerSection.style.display = 'block';
  answerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
