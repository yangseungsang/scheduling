'use strict';

// 현재 열린 모달의 실행 데이터
let _currentItem = null;
// 타이머 인터벌 ID
let _timerInterval = null;
// 마지막 서버 elapsed_seconds + 로컬 시작 시각
let _localTimerBase = 0;
let _localTimerStart = null;

// ── 유틸 ──────────────────────────────────────────────────────────────────

function formatElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
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
  tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">로딩 중...</td></tr>';

  try {
    const items = await apiFetch('/execution/api/list?' + params.toString());
    renderTable(items);
  } catch {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">로드 실패</td></tr>';
  }
}

function statusBadge(item) {
  const ex = item.execution;
  if (!ex) return '<span class="badge bg-secondary">○ 대기</span>';
  switch (ex.status) {
    case 'in_progress':
      return `<span class="badge bg-primary">🔵 진행 ${formatElapsed(ex.elapsed_seconds)}</span>`;
    case 'paused':
      return `<span class="badge bg-warning text-dark">⏸ 일시정지 ${formatElapsed(ex.elapsed_seconds)}</span>`;
    case 'completed':
      return `<span class="badge bg-success">✅ 완료</span>`;
    case 'pending':
      return '<span class="badge bg-secondary">○ 대기</span>';
    default:
      return '<span class="badge bg-secondary">-</span>';
  }
}

function renderTable(items) {
  const tbody = document.getElementById('exec-tbody');
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">항목 없음</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(item => `
    <tr data-id="${item.identifier_id}" data-item='${JSON.stringify(item).replace(/'/g, "&#39;")}' style="cursor:pointer">
      <td><code>${item.identifier_id}</code></td>
      <td>${item.identifier_name}</td>
      <td class="text-muted small">${item.doc_name}</td>
      <td class="text-muted small">${item.location_name || '-'}</td>
      <td class="text-muted small">${item.scheduled_date || '-'}</td>
      <td>${statusBadge(item)}</td>
    </tr>
  `).join('');

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
  startLocalTimer(item);
}

function startLocalTimer(item) {
  stopLocalTimer();
  const ex = item.execution;
  if (!ex || ex.status !== 'in_progress') return;
  _localTimerBase = ex.elapsed_seconds;
  _localTimerStart = Date.now();
  _timerInterval = setInterval(() => {
    const elapsed = _localTimerBase + Math.floor((Date.now() - _localTimerStart) / 1000);
    const el = document.getElementById('timer-display');
    if (el) el.textContent = formatElapsed(elapsed);
  }, 1000);
}

function stopLocalTimer() {
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  _localTimerBase = 0;
  _localTimerStart = null;
}

function renderModalBody(item) {
  const ex = item.execution;
  const status = ex ? ex.status : 'pending';
  const body = document.getElementById('execModalBody');

  if (status === 'pending' || !ex) {
    body.innerHTML = `
      <div class="text-center py-3">
        <button class="btn btn-success btn-lg" onclick="doStart()">
          <i class="bi bi-play-fill"></i> 시험시작
        </button>
      </div>`;
    return;
  }

  const elapsed = ex.elapsed_seconds;
  const total = ex.total_count;
  const fail = ex.fail_count;
  const pass = ex.pass_count;

  if (status === 'completed') {
    body.innerHTML = `
      <div class="text-center mb-3">
        <span class="fs-5">✅ 완료 &nbsp; 총 ${formatElapsed(elapsed)}</span>
      </div>
      <div class="text-center mb-3">
        PASS: <strong>${pass}</strong> &nbsp;&nbsp; FAIL: <strong>${fail}</strong> &nbsp;&nbsp; (총 ${total}건)
      </div>
      <div class="d-flex justify-content-between">
        <button class="btn btn-outline-secondary btn-sm" onclick="doReset()">재시험</button>
        <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">닫기</button>
      </div>`;
    return;
  }

  // in_progress or paused
  const timerHtml = status === 'in_progress'
    ? `<span id="timer-display" class="fs-3 font-monospace">${formatElapsed(elapsed)}</span>
       <button class="btn btn-warning ms-3" onclick="doPause()"><i class="bi bi-pause-fill"></i> 일시정지</button>`
    : `<span id="timer-display" class="fs-3 font-monospace text-muted">${formatElapsed(elapsed)}</span>
       <button class="btn btn-success ms-3" onclick="doResume()"><i class="bi bi-play-fill"></i> 재시작</button>`;

  body.innerHTML = `
    <div class="d-flex align-items-center mb-3">
      ${status === 'in_progress' ? '⏱' : '⏸'} &nbsp; ${timerHtml}
    </div>
    <div class="mb-3">
      <label class="form-label">총 시험: <strong>${total}건</strong></label>
      <div class="d-flex align-items-center gap-2">
        <label class="form-label mb-0">FAIL</label>
        <input type="number" id="fail-input" class="form-control form-control-sm" style="width:80px"
               min="0" max="${total}" value="${fail}" oninput="updatePass()">
        <span class="text-muted">→ PASS:</span>
        <strong id="pass-display">${pass}</strong>
        <span class="text-muted">(자동계산)</span>
      </div>
    </div>
    <div class="d-flex justify-content-between">
      <button class="btn btn-outline-secondary btn-sm" onclick="doReset()">재시험</button>
      <button class="btn btn-primary" onclick="doComplete()">
        <i class="bi bi-check-lg"></i> 시험완료
      </button>
    </div>`;
}

function updatePass() {
  if (!_currentItem || !_currentItem.execution) return;
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
    };
    renderModalBody(_currentItem);
    startLocalTimer(_currentItem);
    await loadList();
  } catch { alert('시험시작 실패'); }
}

async function doPause() {
  try {
    const ex = await apiFetch('/execution/api/pause', 'POST', {
      execution_id: _currentItem.execution.id,
    });
    stopLocalTimer();
    _currentItem.execution = { ..._currentItem.execution, status: 'paused',
      elapsed_seconds: _computeElapsed(ex) };
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
    startLocalTimer(_currentItem);
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
    stopLocalTimer();
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
  if (!confirm('재시험하면 현재 기록이 초기화됩니다. 계속할까요?')) return;
  try {
    await apiFetch('/execution/api/reset', 'POST', {
      execution_id: _currentItem.execution.id,
    });
    stopLocalTimer();
    _currentItem.execution = null;
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('재시험 처리 실패'); }
}

// 서버 응답 ex(raw execution dict with segments)에서 elapsed_seconds 계산
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
  document.getElementById('execModal').addEventListener('hidden.bs.modal', stopLocalTimer);
  document.getElementById('filter-date').addEventListener('change', loadList);
  document.getElementById('filter-location').addEventListener('change', loadList);
  loadList();
});
