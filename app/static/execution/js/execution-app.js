'use strict';

let _allItems = [];
let _sortCol = null;
let _sortDir = 'asc';
let _searchText = '';

const STATUS_ORDER = { pending: 0, in_progress: 1, paused: 2, completed: 3 };

const STATUS_CFG = {
  pending:     { bg: '#f8fafc', border: '#cbd5e1', badge: 'bg-secondary',        label: '대기' },
  in_progress: { bg: '#eff6ff', border: '#3b82f6', badge: 'bg-primary',          label: '진행 중' },
  paused:      { bg: '#fffbeb', border: '#f59e0b', badge: 'bg-warning text-dark', label: '일시정지' },
  completed:   { bg: '#f0fdf4', border: '#22c55e', badge: 'bg-success',           label: '완료' },
};

// ── 유틸 ──────────────────────────────────────────────────────────────────

function formatElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

function formatMinutes(mins) {
  if (!mins) return '-';
  return `${mins}분`;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function apiFetch(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}


// ── 리스트 ────────────────────────────────────────────────────────────────

async function loadList() {
  const date = document.getElementById('filter-date').value;
  const loc  = document.getElementById('filter-location').value;
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (loc)  params.set('location', loc);

  document.getElementById('exec-tbody').innerHTML =
    '<tr><td colspan="8" class="text-center text-muted py-5"><div class="spinner-border spinner-border-sm me-2"></div>로딩 중…</td></tr>';

  try {
    _allItems = await apiFetch('/execution/api/list?' + params.toString());
    renderAssigneeDropdown();
    applyAndRender();
  } catch {
    document.getElementById('exec-tbody').innerHTML =
      '<tr><td colspan="8" class="text-center text-danger py-4"><i class="bi bi-exclamation-circle me-2"></i>로드 실패</td></tr>';
  }
}

// ── 담당자 드롭다운 필터 (#73) ────────────────────────────────────────────

function renderAssigneeDropdown() {
  const sel = document.getElementById('filter-assignee');
  if (!sel) return;
  const all = new Set();
  _allItems.forEach(item => (item.assignee_names || []).forEach(a => all.add(a)));
  const current = sel.value;
  sel.innerHTML = '<option value="">전체 담당자</option>' +
    [...all].sort().map(a => {
      const esc = escHtml(a);
      return `<option value="${esc}" ${current === esc ? 'selected' : ''}>${esc}</option>`;
    }).join('');
}

// ── 정렬 ──────────────────────────────────────────────────────────────────

function setSort(col) {
  _sortDir = _sortCol === col ? (_sortDir === 'asc' ? 'desc' : 'asc') : 'asc';
  _sortCol = col;
  document.querySelectorAll('th[data-sort]').forEach(th => {
    const icon = th.querySelector('i');
    icon.className = th.dataset.sort === _sortCol
      ? `bi ms-1 ${_sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'}`
      : 'bi bi-arrow-down-up ms-1 text-muted';
  });
  applyAndRender();
}

// ── 필터 + 정렬 ───────────────────────────────────────────────────────────

function applyAndRender() {
  let items = [..._allItems];
  const q = _searchText.toLowerCase();
  if (q) items = items.filter(i =>
    i.identifier_id.toLowerCase().includes(q) || i.identifier_name.toLowerCase().includes(q));
  const assigneeFilter = document.getElementById('filter-assignee')?.value || '';
  if (assigneeFilter)
    items = items.filter(i => (i.assignee_names || []).some(a => escHtml(a) === assigneeFilter));
  if (_sortCol) {
    items.sort((a, b) => {
      let va, vb;
      if (_sortCol === 'date')     { va = a.scheduled_date || ''; vb = b.scheduled_date || ''; }
      else if (_sortCol === 'location') { va = a.location_name || ''; vb = b.location_name || ''; }
      else if (_sortCol === 'status')   {
        va = STATUS_ORDER[a.execution?.status ?? 'pending'] ?? 0;
        vb = STATUS_ORDER[b.execution?.status ?? 'pending'] ?? 0;
      }
      return (va < vb ? -1 : va > vb ? 1 : 0) * (_sortDir === 'asc' ? 1 : -1);
    });
  }
  renderTable(items);
}

// ── 테이블 렌더링 ─────────────────────────────────────────────────────────

function statusBadge(item) {
  const s = item.execution?.status || 'pending';
  const labels = { pending: '대기', in_progress: '진행 중', paused: '일시정지', completed: '완료' };
  return `<span class="exec-badge exec-badge-${s}"><span class="exec-badge-dot"></span>${labels[s] || '-'}</span>`;
}

function renderTable(items) {
  const tbody = document.getElementById('exec-tbody');
  const countEl = document.getElementById('item-count');
  if (countEl) countEl.textContent = items.length ? `${items.length}건` : '';

  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-5">항목 없음</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(item => {
    const assignee = (item.assignee_names || []).join(', ') || '-';
    const status = item.execution?.status || 'pending';
    return `
    <tr data-id="${item.identifier_id}" data-status="${status}"
        data-item='${JSON.stringify(item).replace(/'/g,"&#39;")}'>
      <td class="td-doc">${escHtml(item.doc_name || '-')}</td>
      <td class="td-id">${escHtml(item.identifier_id)}</td>
      <td class="td-name">${escHtml(item.identifier_name)}</td>
      <td class="td-meta">${escHtml(assignee)}</td>
      <td class="td-meta">${item.location_name || '-'}</td>
      <td class="td-meta">${item.scheduled_date || '-'}</td>
      <td class="td-meta">${formatMinutes(item.estimated_minutes)}</td>
      <td>${statusBadge(item)}</td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('tr').forEach(tr =>
    tr.addEventListener('click', () => {
      const item = JSON.parse(tr.dataset.item);
      window.location.href = `/execution/${encodeURIComponent(item.identifier_id)}`;
    }));
}

// ── 초기화 ────────────────────────────────────────────────────────────────

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
    document.getElementById('fullscreen-icon').className = 'bi bi-fullscreen-exit';
  } else {
    document.exitFullscreen();
    document.getElementById('fullscreen-icon').className = 'bi bi-fullscreen';
  }
}

document.addEventListener('fullscreenchange', () => {
  const icon = document.getElementById('fullscreen-icon');
  if (icon) icon.className = document.fullscreenElement ? 'bi bi-fullscreen-exit' : 'bi bi-fullscreen';
});

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-fullscreen').addEventListener('click', toggleFullscreen);
  document.getElementById('filter-date').addEventListener('change', loadList);
  document.getElementById('filter-location').addEventListener('change', loadList);
  document.getElementById('filter-assignee').addEventListener('change', applyAndRender);
  document.getElementById('search-input').addEventListener('input', e => {
    _searchText = e.target.value.trim();
    applyAndRender();
  });
  document.querySelectorAll('th[data-sort]').forEach(th =>
    th.addEventListener('click', () => setSort(th.dataset.sort)));
  loadList();
});
