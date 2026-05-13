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

// ── 열 정의 및 가시성 ──────────────────────────────────────────────────────

const COL_DEFS = [
  { key: 'doc',        label: '문서' },
  { key: 'identifier', label: '식별자' },
  { key: 'name',       label: '시험항목' },
  { key: 'assignee',   label: '담당자' },
  { key: 'location',   label: '장소' },
  { key: 'date',       label: '날짜' },
  { key: 'estimated',  label: '예상시간' },
  { key: 'performer',  label: '수행자' },
  { key: 'result',     label: '결과' },
  { key: 'status',     label: '상태' },
];

function loadColVis() {
  try { return JSON.parse(localStorage.getItem('execColVis') || 'null') || {}; }
  catch { return {}; }
}
function saveColVis(vis) { localStorage.setItem('execColVis', JSON.stringify(vis)); }
function colVisible(key) { return loadColVis()[key] !== false; }

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


// ── 열 토글 메뉴 ──────────────────────────────────────────────────────────

function renderColMenu() {
  const menu = document.getElementById('col-toggle-menu');
  if (!menu) return;
  const vis = loadColVis();
  menu.innerHTML = COL_DEFS.map(col => {
    const checked = vis[col.key] !== false ? 'checked' : '';
    return `<li><label class="dropdown-item d-flex gap-2 align-items-center" style="cursor:pointer">
      <input type="checkbox" ${checked} onchange="toggleCol('${col.key}', this.checked)"> ${col.label}
    </label></li>`;
  }).join('');
}

function toggleCol(key, visible) {
  const vis = loadColVis();
  vis[key] = visible;
  saveColVis(vis);
  renderColMenu();
  applyAndRender();
}

// ── 테이블 헤더 렌더링 ────────────────────────────────────────────────────

function buildTableHeader() {
  const cols = [];
  if (colVisible('doc'))        cols.push('<th style="width:250px">문서</th>');
  if (colVisible('identifier')) cols.push('<th style="width:180px">식별자</th>');
  if (colVisible('name'))       cols.push('<th>시험항목</th>');
  if (colVisible('assignee'))   cols.push('<th style="width:100px">담당자</th>');
  if (colVisible('location'))   cols.push('<th class="sortable" data-sort="location" style="width:90px">장소 <i class="bi bi-arrow-down-up ms-1 text-muted"></i></th>');
  if (colVisible('date'))       cols.push('<th class="sortable" data-sort="date" style="width:95px">날짜 <i class="bi bi-arrow-down-up ms-1 text-muted"></i></th>');
  if (colVisible('estimated'))  cols.push('<th style="width:75px">예상</th>');
  if (colVisible('performer'))  cols.push('<th style="width:80px">수행자</th>');
  if (colVisible('result'))     cols.push('<th style="width:130px">결과</th>');
  if (colVisible('status'))     cols.push('<th class="sortable" data-sort="status" style="width:120px">상태 <i class="bi bi-arrow-down-up ms-1 text-muted"></i></th>');
  return cols.join('');
}

function refreshTableHeader() {
  const thead = document.querySelector('.exec-table thead tr');
  if (!thead) return;
  thead.innerHTML = buildTableHeader();
  // 정렬 아이콘 현재 상태 복원
  if (_sortCol) {
    const th = thead.querySelector(`th[data-sort="${_sortCol}"]`);
    if (th) {
      const icon = th.querySelector('i');
      if (icon) icon.className = `bi ms-1 ${_sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'}`;
    }
  }
  // 정렬 클릭 이벤트 재등록
  thead.querySelectorAll('th[data-sort]').forEach(th =>
    th.addEventListener('click', () => setSort(th.dataset.sort)));
}

// ── 리스트 ────────────────────────────────────────────────────────────────

async function loadList() {
  const date = document.getElementById('filter-date').value;
  const loc  = document.getElementById('filter-location').value;
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (loc)  params.set('location', loc);

  const visibleCount = COL_DEFS.filter(c => colVisible(c.key)).length;
  document.getElementById('exec-tbody').innerHTML =
    `<tr><td colspan="${visibleCount}" class="text-center text-muted py-5"><div class="spinner-border spinner-border-sm me-2"></div>로딩 중…</td></tr>`;

  try {
    _allItems = await apiFetch('/execution/api/list?' + params.toString());
    renderStatusSummary();
    applyAndRender();
  } catch {
    const visibleCount2 = COL_DEFS.filter(c => colVisible(c.key)).length;
    document.getElementById('exec-tbody').innerHTML =
      `<tr><td colspan="${visibleCount2}" class="text-center text-danger py-4"><i class="bi bi-exclamation-circle me-2"></i>로드 실패</td></tr>`;
  }
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
    i.identifier_id.toLowerCase().includes(q) ||
    i.identifier_name.toLowerCase().includes(q) ||
    (i.assignee_names || []).some(a => a.toLowerCase().includes(q)));
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
  refreshTableHeader();
  renderTable(items);
}

// ── 테이블 렌더링 ─────────────────────────────────────────────────────────

function statusBadge(item) {
  const s = item.execution?.status || 'pending';
  const labels = { pending: '대기', in_progress: '진행 중', paused: '일시정지', completed: '완료' };
  return `<span class="exec-badge exec-badge-${s}"><span class="exec-badge-dot"></span>${labels[s] || '-'}</span>`;
}

function renderCommentIcon(item) {
  const comment = item.execution?.comment;
  if (!comment) return '';
  const escaped = escHtml(comment).replace(/\n/g, '&#10;');
  return ` <span data-bs-toggle="tooltip" data-bs-placement="top" title="${escaped}" style="cursor:default">💬</span>`;
}

function renderResultCell(item) {
  const ex = item.execution;
  if (!ex || ex.status === 'pending') return '<td>-</td>';
  const f = ex.fail_count ?? 0;
  const b = ex.block_count ?? 0;
  const p = ex.pass_count ?? 0;
  const t = ex.total_count ?? 0;
  return `<td><span class="text-danger">F:${f}</span> <span class="text-warning">B:${b}</span> <span class="text-success">P:${p}</span> <span class="text-muted">/ ${t}</span></td>`;
}

function renderStatusSummary() {
  const el = document.getElementById('status-summary');
  if (!el) return;
  const counts = { pending: 0, in_progress: 0, paused: 0, completed: 0 };
  _allItems.forEach(item => {
    const s = item.execution?.status || 'pending';
    if (counts.hasOwnProperty(s)) counts[s]++;
  });
  const total = _allItems.length;
  el.innerHTML = `
    <span class="exec-summary-item">전체 <strong>${total}</strong></span>
    <span class="exec-summary-item summary-pending">대기 <strong>${counts.pending}</strong></span>
    <span class="exec-summary-item summary-in_progress">진행 중 <strong>${counts.in_progress}</strong></span>
    <span class="exec-summary-item summary-paused">일시정지 <strong>${counts.paused}</strong></span>
    <span class="exec-summary-item summary-completed">완료 <strong>${counts.completed}</strong></span>`;
}

function buildRow(item) {
  const assignee = (item.assignee_names || []).join(', ') || '-';
  const status = item.execution?.status || 'pending';
  const cells = [];
  if (colVisible('doc'))        cells.push(`<td class="td-doc">${escHtml(item.doc_name || '-')}</td>`);
  if (colVisible('identifier')) cells.push(`<td class="td-id">${escHtml(item.identifier_id)}</td>`);
  if (colVisible('name'))       cells.push(`<td class="td-name">${escHtml(item.identifier_name)}${renderCommentIcon(item)}</td>`);
  if (colVisible('assignee'))   cells.push(`<td class="td-meta">${escHtml(assignee)}</td>`);
  if (colVisible('location'))   cells.push(`<td class="td-meta">${escHtml(item.location_name || '-')}</td>`);
  if (colVisible('date'))       cells.push(`<td class="td-meta">${escHtml(item.scheduled_date || '-')}</td>`);
  if (colVisible('estimated'))  cells.push(`<td class="td-meta">${formatMinutes(item.estimated_minutes)}</td>`);
  if (colVisible('performer'))  cells.push(`<td>${escHtml(item.execution?.performer || '-')}</td>`);
  if (colVisible('result'))     cells.push(renderResultCell(item));
  if (colVisible('status'))     cells.push(`<td>${statusBadge(item)}</td>`);
  return `<tr data-id="${escHtml(item.identifier_id)}" data-status="${escHtml(status)}"
      data-item='${escHtml(JSON.stringify(item))}'>${cells.join('')}</tr>`;
}

function renderTable(items) {
  const tbody = document.getElementById('exec-tbody');
  const countEl = document.getElementById('item-count');
  if (countEl) countEl.textContent = items.length ? `${items.length}건` : '';

  const visibleCount = COL_DEFS.filter(c => colVisible(c.key)).length;

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="${visibleCount}" class="text-center text-muted py-5">항목 없음</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map(buildRow).join('');

  tbody.querySelectorAll('tr').forEach(tr =>
    tr.addEventListener('click', () => {
      const item = JSON.parse(tr.dataset.item);
      window.location.href = `/execution/${encodeURIComponent(item.identifier_id)}`;
    }));

  tbody.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    bootstrap.Tooltip.getOrCreateInstance(el);
  });
}

// ── 바코드 감지 공통 유틸 ─────────────────────────────────────────────────
// 80ms 이내 연속 대문자·숫자·_ 입력 후 Enter → 바코드로 판단

function _initBarcodeListener(onScan) {
  let buf = '', timer = null;
  document.addEventListener('keydown', e => {
    const tag = document.activeElement.tagName;
    if (tag === 'TEXTAREA' || tag === 'INPUT') {
      console.log('[barcode] skipped — active element:', tag, document.activeElement.id);
      return;
    }
    if (e.key === 'Enter') {
      const code = buf.trim();
      buf = '';
      clearTimeout(timer);
      console.log('[barcode] Enter → code:', JSON.stringify(code));
      if (code) onScan(code);
      return;
    }
    if (/^[A-Z0-9-]$/.test(e.key)) {
      buf += e.key;
      clearTimeout(timer);
      timer = setTimeout(() => { buf = ''; }, 80);
    }
  });
}

// 바코드 코드에서 식별자 추출: OPEN-TC-001 → TC-001
function _barcodeToId(code) {
  const parts = code.split('-');
  return (typeof BARCODE_PREFIX !== 'undefined' ? BARCODE_PREFIX : '') + parts.slice(1).join('-');
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
  renderColMenu();
  const fsBtn = document.getElementById('btn-fullscreen');
  if (fsBtn) fsBtn.addEventListener('click', toggleFullscreen);
  document.getElementById('filter-date').addEventListener('change', loadList);
  document.getElementById('filter-location').addEventListener('change', loadList);
  document.getElementById('search-input').addEventListener('input', e => {
    _searchText = e.target.value.trim();
    applyAndRender();
  });
  loadList();

  // 바코드 OPEN 명령 감지 (#78)
  _initBarcodeListener(code => {
    console.log('[barcode] onScan:', JSON.stringify(code), 'startsWith OPEN-:', code.startsWith('OPEN-'));
    if (code.startsWith('OPEN-')) {
      const identifierId = _barcodeToId(code);
      console.log('[barcode] navigating to:', identifierId);
      window.location.href = `/execution/${encodeURIComponent(identifierId)}?autostart=1`;
    }
  });
});
