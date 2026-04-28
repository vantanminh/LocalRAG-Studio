'use strict';

const projectId = window.location.pathname.split('/').pop();

const nameDisplay   = document.getElementById('name-display');
const nameRow       = document.getElementById('name-row');
const nameEditRow   = document.getElementById('name-edit-row');
const nameInput     = document.getElementById('name-input');
const renameBtn     = document.getElementById('rename-btn');
const nameSaveBtn   = document.getElementById('name-save-btn');
const nameCancelBtn = document.getElementById('name-cancel-btn');
const fileList      = document.getElementById('file-list');
const sessionList   = document.getElementById('session-list');
const newChatBtn    = document.getElementById('new-chat-btn');
const uploadZone    = document.getElementById('upload-zone');
const fileInput     = document.getElementById('file-input');
const uploadStatus  = document.getElementById('upload-status');

// ── Load project ──────────────────────────────────────────────────────────────
async function loadProject() {
  const res = await fetch(`/projects/${projectId}`);
  if (!res.ok) { document.title = 'Project not found'; return; }
  const proj = await res.json();
  document.title = `${proj.name} – RAG`;
  nameDisplay.textContent = proj.name;
  renderFiles(proj.files || []);
}

async function loadSessions() {
  try {
    const res = await fetch(`/chat/sessions?project_id=${projectId}`);
    const data = await res.json();
    renderSessions(data.sessions || []);
  } catch {}
}

// ── Render files ──────────────────────────────────────────────────────────────
function renderFiles(files) {
  if (!files.length) {
    fileList.innerHTML = '<li style="color:#888;font-size:.85rem;">Chưa có file nào.</li>';
    return;
  }
  fileList.innerHTML = '';
  files.forEach(f => {
    const li = document.createElement('li');
    li.className = 'file-item';
    li.innerHTML =
      `<span class="file-item-name" title="${esc(f.filename)}">📄 ${esc(f.filename)}</span>` +
      `<span class="file-item-chunks">${f.chunks} chunks</span>` +
      `<button class="file-item-del" title="Xóa file" data-name="${esc(f.filename)}">×</button>`;

    li.querySelector('.file-item-del').addEventListener('click', async () => {
      if (!confirm(`Xóa file "${f.filename}" khỏi project?`)) return;
      const r = await fetch(`/projects/${projectId}/files/${encodeURIComponent(f.filename)}`, { method: 'DELETE' });
      if (r.ok) loadProject();
      else alert('Không thể xóa file.');
    });

    fileList.appendChild(li);
  });
}

// ── Render sessions ───────────────────────────────────────────────────────────
function renderSessions(sessions) {
  if (!sessions.length) {
    sessionList.innerHTML = '<li style="color:#888;font-size:.85rem;">Chưa có cuộc trò chuyện nào.</li>';
    return;
  }
  sessionList.innerHTML = '';
  sessions.forEach(s => {
    const li = document.createElement('li');
    li.className = 'session-item-p';
    const date = s.created_at ? new Date(s.created_at).toLocaleDateString('vi-VN', { month: 'short', day: 'numeric' }) : '';
    li.innerHTML =
      `<span class="s-title">${esc(s.title)}</span>` +
      `<span class="s-meta">${date} · ${s.message_count} tin</span>`;
    li.addEventListener('click', () => {
      window.location.href = `/chat?project_id=${projectId}&session_id=${s.id}`;
    });
    sessionList.appendChild(li);
  });
}

// ── Rename ────────────────────────────────────────────────────────────────────
renameBtn.addEventListener('click', () => {
  nameInput.value = nameDisplay.textContent;
  nameRow.style.display = 'none';
  nameEditRow.style.display = 'flex';
  nameInput.focus();
});

nameCancelBtn.addEventListener('click', () => {
  nameEditRow.style.display = 'none';
  nameRow.style.display = 'flex';
});

async function saveRename() {
  const name = nameInput.value.trim();
  if (!name) return;
  const res = await fetch(`/projects/${projectId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (res.ok) {
    nameDisplay.textContent = name;
    document.title = `${name} – RAG`;
  }
  nameEditRow.style.display = 'none';
  nameRow.style.display = 'flex';
}

nameSaveBtn.addEventListener('click', saveRename);
nameInput.addEventListener('keydown', e => { if (e.key === 'Enter') saveRename(); if (e.key === 'Escape') nameCancelBtn.click(); });

// ── Upload ────────────────────────────────────────────────────────────────────
function setStatus(msg, type) {
  uploadStatus.textContent = msg;
  uploadStatus.className = `upload-status ${type}`;
}

async function uploadFiles(files) {
  if (!files.length) return;
  setStatus('Đang upload…', 'loading');
  let ok = 0, fail = 0;
  for (const f of files) {
    const fd = new FormData();
    fd.append('file', f);
    try {
      const res = await fetch(`/projects/${projectId}/files`, { method: 'POST', body: fd });
      if (res.ok) ok++;
      else { const d = await res.json().catch(() => ({})); fail++; console.error(d.detail); }
    } catch { fail++; }
  }
  if (fail === 0) setStatus(`✓ Đã upload ${ok} file thành công`, 'ok');
  else setStatus(`${ok} thành công, ${fail} thất bại`, fail === files.length ? 'err' : 'ok');
  await loadProject();
}

uploadZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => { uploadFiles(Array.from(fileInput.files)); fileInput.value = ''; });

uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  uploadFiles(Array.from(e.dataTransfer.files));
});

// ── New chat ──────────────────────────────────────────────────────────────────
newChatBtn.addEventListener('click', () => {
  window.location.href = `/chat?project_id=${projectId}`;
});

// ── Utils ─────────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadProject();
loadSessions();
