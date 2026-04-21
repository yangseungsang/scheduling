'use strict';

let _currentItem = null;
let _allItems = [];
let _sortCol = null;   // 'date' | 'location' | 'status'
let _sortDir = 'asc';
let _activeAssignees = new Set();
let _searchText = '';

const STATUS_ORDER = { pending: 0, in_progress: 1, paused: 2, completed: 3 };

// ── 유틸 ──────────────────────────────────────────────────────────────────

function formatElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

function formatMinutes(mins) {
  if (!mins) return '-';
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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
  const loc = document.getElementById('filter-location').value;
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (loc) params.set('location', loc);

  const tbody = document.getElementById('exec-tbody');
  tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">로딩 중...</td></tr>';

  try {
    _allItems = await apiFetch('/execution/api/list?' + params.toString());
    renderAssigneeBadges();
    applyAndRender();
  } catch {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger">로드 실패</td></tr>';
  }
}

// ── 담당자 뱃지 필터 ───────────────────────────────────────────────────────

function renderAssigneeBadges() {
  const container = document.getElementById('assignee-badges');
  const allAssignees = new Set();
  _allItems.forEach(item => (item.assignee_names || []).forEach(a => allAssignees.add(a)));

  if (!allAssignees.size) { container.innerHTML = ''; return; }

  container.innerHTML = [...allAssignees].sort().map(a => {
    const active = _activeAssignees.has(a);
    return `<span class="badge me-1 mb-1 ${active ? 'bg-primary' : 'bg-light text-dark border'}"
      style="cursor:pointer;font-size:.8rem" onclick="toggleAssignee(${JSON.stringify(escHtml(a))})"
      title="담당자 필터">${escHtml(a)}</span>`;
  }).join('');
}

function toggleAssignee(name) {
  // name은 escHtml 처리된 문자열이므로 원본 복원 불필요 (텍스트 비교용)
  if (_activeAssignees.has(name)) _activeAssignees.delete(name);
  else _activeAssignees.add(name);
  renderAssigneeBadges();
  applyAndRender();
}

// ── 정렬 ──────────────────────────────────────────────────────────────────

function setSort(col) {
  if (_sortCol === col) _sortDir = _sortDir === 'asc' ? 'desc' : 'asc';
  else { _sortCol = col; _sortDir = 'asc'; }
  updateSortIcons();
  applyAndRender();
}

function updateSortIcons() {
  document.querySelectorAll('th[data-sort]').forEach(th => {
    const icon = th.querySelector('i');
    if (th.dataset.sort === _sortCol) {
      icon.className = `bi ms-1 ${_sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'}`;
      icon.classList.remove('text-muted');
    } else {
      icon.className = 'bi bi-arrow-down-up ms-1 text-muted';
    }
  });
}

// ── 필터+정렬 적용 ────────────────────────────────────────────────────────

function applyAndRender() {
  let items = [..._allItems];

  // 검색 필터
  const q = _searchText.toLowerCase();
  if (q) {
    items = items.filter(item =>
      item.identifier_id.toLowerCase().includes(q) ||
      item.identifier_name.toLowerCase().includes(q)
    );
  }

  // 담당자 필터
  if (_activeAssignees.size > 0) {
    items = items.filter(item =>
      (item.assignee_names || []).some(a => _activeAssignees.has(escHtml(a)))
    );
  }

  // 정렬
  if (_sortCol) {
    items.sort((a, b) => {
      let va, vb;
      if (_sortCol === 'date') {
        va = a.scheduled_date || '';
        vb = b.scheduled_date || '';
      } else if (_sortCol === 'location') {
        va = a.location_name || '';
        vb = b.location_name || '';
      } else if (_sortCol === 'status') {
        va = STATUS_ORDER[a.execution?.status ?? 'pending'] ?? 0;
        vb = STATUS_ORDER[b.execution?.status ?? 'pending'] ?? 0;
      }
      if (va < vb) return _sortDir === 'asc' ? -1 : 1;
      if (va > vb) return _sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }

  renderTable(items);
}

// ── 테이블 렌더링 ─────────────────────────────────────────────────────────

function statusBadge(item) {
  const ex = item.execution;
  if (!ex) return '<span class="badge bg-secondary">○ 대기</span>';
  switch (ex.status) {
    case 'in_progress': return '<span class="badge bg-primary">🔵 진행 중</span>';
    case 'paused':      return '<span class="badge bg-warning text-dark">⏸ 일시정지</span>';
    case 'completed':   return '<span class="badge bg-success">✅ 완료</span>';
    case 'pending':     return '<span class="badge bg-secondary">○ 대기</span>';
    default:            return '<span class="badge bg-secondary">-</span>';
  }
}

function renderTable(items) {
  const tbody = document.getElementById('exec-tbody');
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">항목 없음</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(item => {
    const assignee = (item.assignee_names || []).join(', ') || '-';
    return `
    <tr data-id="${item.identifier_id}" data-item='${JSON.stringify(item).replace(/'/g, "&#39;")}' style="cursor:pointer">
      <td class="text-muted small">${escHtml(item.doc_name || '-')}</td>
      <td><code>${escHtml(item.identifier_id)}</code></td>
      <td>${escHtml(item.identifier_name)}</td>
      <td class="text-muted small">${escHtml(assignee)}</td>
      <td class="text-muted small">${item.location_name || '-'}</td>
      <td class="text-muted small">${item.scheduled_date || '-'}</td>
      <td class="text-muted small">${formatMinutes(item.estimated_minutes)}</td>
      <td>${statusBadge(item)}</td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('dblclick', () => {
      const item = JSON.parse(tr.dataset.item);
      openModal(item);
    });
  });
}

// ── 모달 ──────────────────────────────────────────────────────────────────

function openModal(item) {
  _currentItem = item;
  document.getElementById('execModalTitle').textContent =
    `${item.identifier_id} — ${item.identifier_name}`;
  renderModalBody(item);
  new bootstrap.Modal(document.getElementById('execModal')).show();
}

function _infoHtml(item) {
  const ex = item.execution;
  const assignee = (item.assignee_names || []).join(', ') || '-';
  const rows = [
    ['식별자', escHtml(item.identifier_id)],
    ['시험항목', escHtml(item.identifier_name)],
    ['문서', escHtml(item.doc_name || '-')],
    ['담당자', escHtml(assignee)],
    ['장소', escHtml(item.location_name || '-')],
    ['예정일', escHtml(item.scheduled_date || '-')],
    ['소요시간', formatMinutes(item.estimated_minutes)],
    ex ? ['총 건수', `${ex.total_count}건`] : null,
  ].filter(Boolean);
  return `<div class="bg-light rounded p-2 mb-3 small">
    <div class="row g-1">${rows.map(([k, v]) =>
      `<div class="col-4 text-muted">${k}</div><div class="col-8">${v}</div>`
    ).join('')}</div>
  </div>`;
}

function _attachCommentHandler() {
  const ta = document.getElementById('comment-input');
  if (!ta) return;
  const save = async () => {
    if (!_currentItem?.execution?.id) return;
    try {
      await apiFetch('/execution/api/comment', 'PUT', {
        execution_id: _currentItem.execution.id,
        comment: ta.value,
      });
      _currentItem.execution.comment = ta.value;
    } catch { /* 저장 실패 시 무시 */ }
  };
  ta.addEventListener('blur', save);
  ta.addEventListener('change', save);
}

function renderModalBody(item) {
  const ex = item.execution;
  const status = ex ? ex.status : 'pending';
  const body = document.getElementById('execModalBody');

  // 상태별 주요 액션 버튼
  let actionHtml;
  if (status === 'pending') {
    actionHtml = `<button class="btn btn-success btn-lg" onclick="doStart()">
      <i class="bi bi-play-fill"></i> 시험시작
    </button>`;
  } else if (status === 'in_progress') {
    actionHtml = `<button class="btn btn-warning" onclick="doPause()">
      <i class="bi bi-pause-fill"></i> 일시정지
    </button>`;
  } else if (status === 'paused') {
    actionHtml = `<button class="btn btn-success" onclick="doResume()">
      <i class="bi bi-play-fill"></i> 재시작
    </button>`;
  } else {
    actionHtml = `<span class="fs-5">✅ 완료 &nbsp; 총 ${formatElapsed(ex.elapsed_seconds)}</span>`;
  }

  // FAIL/PASS 입력 — 항상 표시, pending/completed는 비활성
  let failPassHtml;
  if (status === 'completed') {
    failPassHtml = `
    <div class="mb-2 text-center small text-muted">
      PASS: <strong>${ex.pass_count}</strong> &nbsp;&nbsp;
      FAIL: <strong>${ex.fail_count}</strong> &nbsp;&nbsp;
      (총 ${ex.total_count}건)
    </div>`;
  } else {
    const failVal = ex ? ex.fail_count : 0;
    const passVal = ex ? ex.pass_count : 0;
    const totalLabel = ex ? `/ ${ex.total_count}건` : '';
    const maxAttr = ex ? `max="${ex.total_count}"` : '';
    const disabledAttr = !ex ? 'disabled' : '';
    failPassHtml = `
    <div class="mb-3">
      <div class="d-flex align-items-center gap-2">
        <label class="form-label mb-0">FAIL</label>
        <input type="number" id="fail-input" class="form-control form-control-sm" style="width:80px"
               min="0" ${maxAttr} value="${failVal}" ${disabledAttr} oninput="updatePass()">
        <span class="text-muted">→ PASS:</span>
        <strong id="pass-display">${passVal}</strong>
        <span class="text-muted">${totalLabel}</span>
      </div>
    </div>`;
  }

  // 코멘트 — 항상 표시, pending은 비활성
  const commentDisabled = !ex ? 'disabled' : '';
  const commentValue = ex ? escHtml(ex.comment || '') : '';
  const commentHtml = `
  <div class="mb-3">
    <label class="form-label small text-muted mb-1">코멘트</label>
    <textarea id="comment-input" class="form-control form-control-sm" rows="2"
      ${commentDisabled} placeholder="시험 관련 코멘트 입력...">${commentValue}</textarea>
  </div>`;

  // 하단 버튼 — 항상 표시, pending은 비활성
  let footerHtml;
  if (status === 'completed') {
    footerHtml = `
    <div class="d-flex justify-content-between mt-3">
      <button class="btn btn-outline-secondary btn-sm" onclick="doReset()">재시험</button>
      <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">닫기</button>
    </div>`;
  } else {
    const disabledAttr = !ex ? 'disabled' : '';
    footerHtml = `
    <div class="d-flex justify-content-between mt-3">
      <button class="btn btn-outline-secondary btn-sm" onclick="doReset()" ${disabledAttr}>재시험</button>
      <button class="btn btn-primary" onclick="doComplete()" ${disabledAttr}>
        <i class="bi bi-check-lg"></i> 시험완료
      </button>
    </div>`;
  }

  body.innerHTML = `
    ${_infoHtml(item)}
    <div class="text-center mb-3">${actionHtml}</div>
    ${failPassHtml}
    ${commentHtml}
    ${footerHtml}`;

  _attachCommentHandler();
}

function updatePass() {
  if (!_currentItem?.execution) return;
  const total = _currentItem.execution.total_count;
  const fail = parseInt(document.getElementById('fail-input').value) || 0;
  document.getElementById('pass-display').textContent = Math.max(0, total - fail);
}

// ── 액션 핸들러 ───────────────────────────────────────────────────────────

async function doStart() {
  try {
    const ex = await apiFetch('/execution/api/start', 'POST', {
      identifier_id: _currentItem.identifier_id,
      task_id: _currentItem.task_id,
    });
    _currentItem.execution = {
      id: ex.id,
      status: ex.status,
      elapsed_seconds: 0,
      total_count: ex.total_count,
      fail_count: 0,
      pass_count: 0,
      comment: '',
    };
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('시험시작 실패'); }
}

async function doPause() {
  try {
    const ex = await apiFetch('/execution/api/pause', 'POST', {
      execution_id: _currentItem.execution.id,
    });
    _currentItem.execution = {
      ..._currentItem.execution,
      status: 'paused',
      elapsed_seconds: _computeElapsed(ex),
    };
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('일시정지 실패'); }
}

async function doResume() {
  try {
    const ex = await apiFetch('/execution/api/resume', 'POST', {
      execution_id: _currentItem.execution.id,
    });
    _currentItem.execution.status = 'in_progress';
    _currentItem.execution.elapsed_seconds = _computeElapsed(ex);
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('재시작 실패'); }
}

async function doComplete() {
  const failInput = document.getElementById('fail-input');
  const failCount = parseInt(failInput ? failInput.value : 0) || 0;
  try {
    const ex = await apiFetch('/execution/api/complete', 'POST', {
      execution_id: _currentItem.execution.id,
      fail_count: failCount,
    });
    _currentItem.execution = {
      ..._currentItem.execution,
      status: 'completed',
      fail_count: ex.fail_count,
      pass_count: ex.pass_count,
      elapsed_seconds: _computeElapsed(ex),
    };
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('완료 처리 실패'); }
}

async function doReset() {
  if (!_currentItem?.execution?.id) return;
  if (!confirm('재시험하면 현재 기록이 초기화됩니다. 계속할까요?')) return;
  try {
    await apiFetch('/execution/api/reset', 'POST', {
      execution_id: _currentItem.execution.id,
    });
    _currentItem.execution = null;
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('재시험 처리 실패'); }
}

function _computeElapsed(ex) {
  let total = 0;
  const now = new Date();
  for (const seg of (ex.segments || [])) {
    const start = new Date(seg.start);
    const end = seg.end ? new Date(seg.end) : now;
    total += Math.floor((end - start) / 1000);
  }
  return Math.max(0, total);
}

// ── 초기화 ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('filter-date').addEventListener('change', loadList);
  document.getElementById('filter-location').addEventListener('change', loadList);

  document.getElementById('search-input').addEventListener('input', e => {
    _searchText = e.target.value.trim();
    applyAndRender();
  });

  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.addEventListener('click', () => setSort(th.dataset.sort));
  });

  loadList();

  // 스페이스바 단축키: 시험시작 / 일시정지 / 재시작
  document.addEventListener('keydown', (e) => {
    if (e.code !== 'Space') return;
    const tag = document.activeElement.tagName;
    if (tag === 'TEXTAREA' || tag === 'INPUT') return;
    const modal = document.getElementById('execModal');
    if (!modal.classList.contains('show')) return;
    e.preventDefault();
    if (!_currentItem) return;
    const status = _currentItem.execution ? _currentItem.execution.status : 'pending';
    if (status === 'pending') doStart();
    else if (status === 'in_progress') doPause();
    else if (status === 'paused') doResume();
  });
});
