'use strict';

let _item = null;
let _pendingComment = '';

// 타이머
let _timerInterval = null;
let _timerBase = 0;
let _timerStart = null;

const STATUS_CFG = {
  pending:     { bg: '#f8fafc', border: '#cbd5e1', badge: 'bg-secondary',         label: '대기' },
  in_progress: { bg: '#eff6ff', border: '#3b82f6', badge: 'bg-primary',           label: '진행 중' },
  paused:      { bg: '#fffbeb', border: '#f59e0b', badge: 'bg-warning text-dark',  label: '일시정지' },
  completed:   { bg: '#f0fdf4', border: '#22c55e', badge: 'bg-success',            label: '완료' },
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
  const h = Math.floor(mins / 60), m = mins % 60;
  if (h && m) return `${h}h ${m}m`;
  return h ? `${h}h` : `${m}m`;
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

// ── 타이머 ────────────────────────────────────────────────────────────────

function startLocalTimer() {
  stopLocalTimer();
  const ex = _item?.execution;
  if (!ex || ex.status !== 'in_progress') return;
  _timerBase  = ex.elapsed_seconds;
  _timerStart = Date.now();
  _timerInterval = setInterval(() => {
    const el = document.getElementById('timer-display');
    if (el) el.textContent = formatElapsed(_timerBase + Math.floor((Date.now() - _timerStart) / 1000));
  }, 1000);
}

function stopLocalTimer() {
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  _timerBase = 0; _timerStart = null;
}

// ── 렌더링 ────────────────────────────────────────────────────────────────

function renderPage() {
  const item   = _item;
  const ex     = item.execution;
  const status = ex?.status ?? 'pending';
  const cfg    = STATUS_CFG[status] || STATUS_CFG.pending;

  document.getElementById('page-title').textContent =
    `${item.identifier_id} — ${item.identifier_name}`;

  // 상태 헤더
  const elapsed = ex?.elapsed_seconds ?? 0;
  let actionBtn;
  if      (status === 'pending')     actionBtn = `<button class="btn btn-success px-4" onclick="doStart()"><i class="bi bi-play-fill me-1"></i>시험시작</button>`;
  else if (status === 'in_progress') actionBtn = `<button class="btn btn-warning px-4" onclick="doPause()"><i class="bi bi-pause-fill me-1"></i>일시정지</button>`;
  else if (status === 'paused')      actionBtn = `<button class="btn btn-primary px-4" onclick="doResume()"><i class="bi bi-play-fill me-1"></i>재시작</button>`;
  else                               actionBtn = '';

  const timerColor = status === 'pending' ? '#94a3b8' : '#1e293b';
  const statusHeader = `
  <div class="rounded-3 px-4 py-3 mb-3 d-flex align-items-center justify-content-between gap-3"
       style="background:${cfg.bg};border-left:4px solid ${cfg.border}">
    <span class="badge ${cfg.badge} px-3 py-2" style="font-size:.85rem">${cfg.label}</span>
    <div class="text-center flex-grow-1">
      <div id="timer-display" class="font-monospace fw-bold"
           style="font-size:2.4rem;letter-spacing:.05em;color:${timerColor};line-height:1">
        ${formatElapsed(elapsed)}
      </div>
      <div class="text-muted" style="font-size:.72rem;margin-top:2px">경과 시간</div>
    </div>
    <div>${actionBtn}</div>
  </div>`;

  // 정보 그리드
  const assignee = (item.assignee_names || []).join(', ') || '-';
  const infoItems = [
    ['식별자',   `<code class="text-primary">${escHtml(item.identifier_id)}</code>`],
    ['문서',     escHtml(item.doc_name || '-')],
    ['시험항목', escHtml(item.identifier_name)],
    ['담당자',   escHtml(assignee)],
    ['장소',     escHtml(item.location_name || '-')],
    ['날짜',     escHtml(item.scheduled_date || '-')],
    ['소요시간', formatMinutes(item.estimated_minutes)],
    ex ? ['총 건수', `<strong>${ex.total_count}</strong>건`] : null,
  ].filter(Boolean);

  const infoGrid = `
  <div class="row g-0 mb-3 border rounded-3 overflow-hidden small">
    ${infoItems.map(([k, v], i) => `
    <div class="col-6 px-3 py-2 ${i % 2 === 0 ? 'border-end' : ''} ${i >= 2 ? 'border-top' : ''}">
      <span class="text-muted me-2" style="min-width:54px;display:inline-block">${k}</span>${v}
    </div>`).join('')}
  </div>`;

  // FAIL / PASS
  let failPassHtml;
  if (status === 'completed') {
    failPassHtml = `
    <div class="d-flex align-items-center justify-content-center gap-4 mb-3 py-3 rounded-3 border">
      <div class="text-center">
        <div class="fs-4 fw-bold text-success">${ex.pass_count}</div>
        <div class="text-muted small">PASS</div>
      </div>
      <div class="text-muted fs-4">|</div>
      <div class="text-center">
        <div class="fs-4 fw-bold text-danger">${ex.fail_count}</div>
        <div class="text-muted small">FAIL</div>
      </div>
      <div class="text-muted small align-self-center">/ 총 ${ex.total_count}건</div>
    </div>`;
  } else {
    const dis   = !ex ? 'disabled' : '';
    const failV = ex ? ex.fail_count : 0;
    const passV = ex ? ex.pass_count : 0;
    const total = ex ? `/ 총 ${ex.total_count}건` : '';
    const maxA  = ex ? `max="${ex.total_count}"` : '';
    failPassHtml = `
    <div class="d-flex align-items-center gap-3 mb-3 px-3 py-2 border rounded-3 bg-light">
      <span class="text-muted small fw-medium">FAIL</span>
      <input type="number" id="fail-input" class="form-control form-control-sm text-center fw-bold"
             style="width:68px" min="0" ${maxA} value="${failV}" ${dis} oninput="updatePass()">
      <span class="text-muted">→</span>
      <span class="text-muted small fw-medium">PASS</span>
      <span id="pass-display" class="fs-5 fw-bold text-success">${passV}</span>
      <span class="text-muted small ms-auto">${total}</span>
    </div>`;
  }

  // 코멘트
  const commentValue = ex ? escHtml(ex.comment || '') : escHtml(_pendingComment);
  const commentHtml = `
  <div class="mb-3">
    <label class="form-label small text-muted mb-1">
      <i class="bi bi-chat-left-text me-1"></i>코멘트
    </label>
    <textarea id="comment-input" class="form-control form-control-sm" rows="3"
      placeholder="시험 관련 코멘트 입력…">${commentValue}</textarea>
  </div>`;

  // 하단 버튼
  let footerHtml;
  if (status === 'completed') {
    footerHtml = `
    <div class="d-flex justify-content-between">
      <button class="btn btn-outline-secondary btn-sm" onclick="doReset()">
        <i class="bi bi-arrow-counterclockwise me-1"></i>재시험
      </button>
      <a href="/execution/" class="btn btn-secondary btn-sm">목록으로</a>
    </div>`;
  } else {
    const dis = !ex ? 'disabled' : '';
    footerHtml = `
    <div class="d-flex justify-content-between">
      <button class="btn btn-outline-secondary btn-sm" onclick="doReset()" ${dis}>
        <i class="bi bi-arrow-counterclockwise me-1"></i>재시험
      </button>
      <button class="btn btn-primary" onclick="doComplete()" ${dis}>
        <i class="bi bi-check-lg me-1"></i>시험완료
      </button>
    </div>`;
  }

  document.getElementById('detail-content').innerHTML =
    `${statusHeader}${infoGrid}${failPassHtml}${commentHtml}${footerHtml}`;

  _attachCommentHandler();
  startLocalTimer();
}

function _attachCommentHandler() {
  const ta = document.getElementById('comment-input');
  if (!ta) return;
  const save = async () => {
    if (!_item?.execution?.id) { _pendingComment = ta.value; return; }
    try {
      await apiFetch('/execution/api/comment', 'PUT', {
        execution_id: _item.execution.id,
        comment: ta.value,
      });
      _item.execution.comment = ta.value;
    } catch { /* 무시 */ }
  };
  ta.addEventListener('blur', save);
  ta.addEventListener('change', save);
}

function updatePass() {
  if (!_item?.execution) return;
  const total = _item.execution.total_count;
  const fail  = parseInt(document.getElementById('fail-input').value) || 0;
  document.getElementById('pass-display').textContent = Math.max(0, total - fail);
}

// ── 액션 핸들러 ───────────────────────────────────────────────────────────

async function doStart() {
  const ta = document.getElementById('comment-input');
  if (ta) _pendingComment = ta.value;
  try {
    const ex = await apiFetch('/execution/api/start', 'POST', {
      identifier_id: _item.identifier_id,
      task_id: _item.task_id,
    });
    _item.execution = {
      id: ex.id, status: ex.status, elapsed_seconds: 0,
      total_count: ex.total_count, fail_count: 0, pass_count: 0, comment: _pendingComment,
    };
    if (_pendingComment) {
      await apiFetch('/execution/api/comment', 'PUT', { execution_id: ex.id, comment: _pendingComment });
      _pendingComment = '';
    }
    renderPage();
  } catch { alert('시험시작 실패'); }
}

async function doPause() {
  try {
    const ex = await apiFetch('/execution/api/pause', 'POST', { execution_id: _item.execution.id });
    stopLocalTimer();
    _item.execution = { ..._item.execution, status: 'paused', elapsed_seconds: _computeElapsed(ex) };
    renderPage();
  } catch { alert('일시정지 실패'); }
}

async function doResume() {
  try {
    const ex = await apiFetch('/execution/api/resume', 'POST', { execution_id: _item.execution.id });
    _item.execution.status = 'in_progress';
    _item.execution.elapsed_seconds = _computeElapsed(ex);
    renderPage();
  } catch { alert('재시작 실패'); }
}

async function doComplete() {
  const failInput = document.getElementById('fail-input');
  const failCount = parseInt(failInput?.value || 0) || 0;
  try {
    const ex = await apiFetch('/execution/api/complete', 'POST', {
      execution_id: _item.execution.id, fail_count: failCount,
    });
    stopLocalTimer();
    _item.execution = {
      ..._item.execution, status: 'completed',
      fail_count: ex.fail_count, pass_count: ex.pass_count, elapsed_seconds: _computeElapsed(ex),
    };
    renderPage();
  } catch { alert('완료 처리 실패'); }
}

async function doReset() {
  if (!_item?.execution?.id) return;
  if (!confirm('재시험하면 현재 기록이 초기화됩니다. 계속할까요?')) return;
  try {
    await apiFetch('/execution/api/reset', 'POST', { execution_id: _item.execution.id });
    stopLocalTimer();
    _item.execution = null;
    renderPage();
  } catch { alert('재시험 처리 실패'); }
}

function _computeElapsed(ex) {
  let total = 0;
  const now = new Date();
  for (const seg of (ex.segments || [])) {
    const start = new Date(seg.start);
    const end   = seg.end ? new Date(seg.end) : now;
    total += Math.floor((end - start) / 1000);
  }
  return Math.max(0, total);
}

// ── 초기화 ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  try {
    _item = await apiFetch(`/execution/api/item/${encodeURIComponent(IDENTIFIER_ID)}`);
    renderPage();
  } catch {
    document.getElementById('detail-content').innerHTML =
      '<div class="alert alert-danger">항목을 찾을 수 없습니다.</div>';
  }

  // 스페이스바 단축키
  document.addEventListener('keydown', e => {
    if (e.code !== 'Space') return;
    const tag = document.activeElement.tagName;
    if (tag === 'TEXTAREA' || tag === 'INPUT') return;
    e.preventDefault();
    const s = _item?.execution?.status ?? 'pending';
    if (s === 'pending') doStart();
    else if (s === 'in_progress') doPause();
    else if (s === 'paused') doResume();
  });
});
