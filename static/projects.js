'use strict';

const gridEl      = document.getElementById('project-grid');
const nameInput   = document.getElementById('project-name-input');
const createBtn   = document.getElementById('create-btn');

async function loadProjects() {
  try {
    const res = await fetch('/projects');
    const data = await res.json();
    render(data.projects || []);
  } catch {
    gridEl.innerHTML = '<div class="empty-state">Không thể tải danh sách projects.</div>';
  }
}

function render(projects) {
  if (!projects.length) {
    gridEl.innerHTML = '<div class="empty-state">Chưa có project nào. Tạo project đầu tiên của bạn!</div>';
    return;
  }
  gridEl.innerHTML = '';
  projects.forEach(p => {
    const card = document.createElement('div');
    card.className = 'project-card';
    const date = p.created_at ? new Date(p.created_at).toLocaleDateString('vi-VN', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
    card.innerHTML =
      `<div class="project-card-icon">📂</div>` +
      `<div class="project-card-name">${esc(p.name)}</div>` +
      `<div class="project-card-meta">${p.file_count} file · ${date}</div>` +
      `<button class="project-card-del" title="Xóa project" data-id="${p.id}">×</button>`;

    card.addEventListener('click', e => {
      if (e.target.classList.contains('project-card-del')) return;
      window.location.href = `/p/${p.id}`;
    });

    card.querySelector('.project-card-del').addEventListener('click', async e => {
      e.stopPropagation();
      if (!confirm(`Xóa project "${p.name}"?\nTất cả file và chat trong project sẽ bị xóa.`)) return;
      await fetch(`/projects/${p.id}`, { method: 'DELETE' });
      await loadProjects();
    });

    gridEl.appendChild(card);
  });
}

async function createProject() {
  const name = nameInput.value.trim();
  if (!name) { nameInput.focus(); return; }
  createBtn.disabled = true;
  try {
    const res = await fetch('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error();
    nameInput.value = '';
    await loadProjects();
  } catch {
    alert('Không thể tạo project.');
  } finally {
    createBtn.disabled = false;
  }
}

createBtn.addEventListener('click', createProject);
nameInput.addEventListener('keydown', e => { if (e.key === 'Enter') createProject(); });

function esc(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

loadProjects();
