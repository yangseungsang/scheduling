'use strict';

let _item = null;
let _pendingComment = '';
let _pendingPerformer = '';

// 타이머
let _timerInterval = null;
let _timerBase = 0;
let _timerStart = null;

const STATUS_CFG = {
  pending:     { bg: '#f1f5f9', border: '#94a3b8', badge: 'bg-secondary',         label: '대기' },
  in_progress: { bg: '#dbeafe', border: '#3b82f6', badge: 'bg-primary',           label: '진행 중' },
  paused:      { bg: '#fef9c3', border: '#eab308', badge: 'bg-warning text-dark',  label: '일시정지' },
  completed:   { bg: '#dcfce7', border: '#22c55e', badge: 'bg-success',            label: '완료' },
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

// ── 전체화면 (#63) ────────────────────────────────────────────────────────

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen();
  }
}

document.addEventListener('fullscreenchange', () => {
  const icon = document.getElementById('fullscreen-icon');
  if (icon) icon.className = document.fullscreenElement ? 'bi bi-fullscreen-exit' : 'bi bi-fullscreen';
});

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

// ── 렌더링 (#62 리디자인) ─────────────────────────────────────────────────

function renderPage() {
  const item   = _item;
  const ex     = item.execution;
  const status = ex?.status ?? 'pending';
  const cfg    = STATUS_CFG[status] || STATUS_CFG.pending;

  document.getElementById('page-title').textContent =
    `${item.identifier_id} — ${item.identifier_name}`;

  // ── 왼쪽 패널: 정보 목록 ──────────────────────────────────────────────
  const assignee = (item.assignee_names || []).join(', ') || '-';
  const infoRows = [
    ['식별자',   `<code class="text-primary">${escHtml(item.identifier_id)}</code>`],
    ['문서',     escHtml(item.doc_name || '-')],
    ['시험항목', escHtml(item.identifier_name)],
    ['담당자',   escHtml(assignee)],
    ['장소',     escHtml(item.location_name || '-')],
    ['날짜',     escHtml(item.scheduled_date || '-')],
    ['예상시간', formatMinutes(item.estimated_minutes)],
    ex ? ['총 건수', `<strong>${ex.total_count}</strong>건`] : null,
  ].filter(Boolean);

  const leftPanel = `
  <div class="d-flex flex-column h-100 border-end overflow-y-auto" style="flex:0 0 38%;min-width:320px;padding:1.25rem 1.25rem">
    <div class="mb-3">
      <span class="badge ${cfg.badge} px-3 py-2 w-100 text-center" style="font-size:1rem">${cfg.label}</span>
    </div>
    <table class="table table-sm table-borderless mb-0" style="font-size:.95rem">
      <tbody>
        ${infoRows.map(([k, v]) => `
        <tr>
          <td class="text-muted pe-2 text-nowrap" style="width:72px">${k}</td>
          <td>${v}</td>
        </tr>`).join('')}
      </tbody>
    </table>
  </div>`;

  // ── 오른쪽 패널: 타이머 + 입력 ──────────────────────────────────────
  const elapsed = ex?.elapsed_seconds ?? 0;
  let actionBtn;
  if      (status === 'pending')     actionBtn = `<button class="btn btn-success btn-lg px-5" onclick="doStart()"><i class="bi bi-play-fill me-1"></i>시험시작</button>`;
  else if (status === 'in_progress') actionBtn = `<button class="btn btn-warning btn-lg px-5" onclick="doPause()"><i class="bi bi-pause-fill me-1"></i>일시정지</button>`;
  else if (status === 'paused')      actionBtn = `<button class="btn btn-primary btn-lg px-5" onclick="doResume()"><i class="bi bi-play-fill me-1"></i>재시작</button>`;
  else                               actionBtn = `<span class="fs-5 fw-semibold text-success"><i class="bi bi-check-circle-fill me-2"></i>시험 완료</span>`;

  const timerColor = status === 'pending' ? '#94a3b8' : '#0f172a';
  const timerSection = `
  <div class="text-center py-3 mb-2 rounded-3" style="background:${cfg.bg};border-left:4px solid ${cfg.border}">
    <div id="timer-display" class="font-monospace fw-bold"
         style="font-size:3.2rem;letter-spacing:.06em;color:${timerColor};line-height:1.1">
      ${formatElapsed(elapsed)}
    </div>
    <div class="text-muted mb-2" style="font-size:.75rem">경과 시간</div>
    ${actionBtn}
  </div>`;

  // ── FAIL / BLOCK / PASS ──────────────────────────────────────────────
  let failPassHtml;
  if (status === 'completed') {
    failPassHtml = `
    <div class="d-flex border rounded-3 overflow-hidden mb-2">
      <div class="text-center flex-fill py-3 bg-danger bg-opacity-10">
        <div class="fs-2 fw-bold text-danger">${ex.fail_count}</div>
        <div class="text-muted small fw-semibold">FAIL</div>
      </div>
      <div class="text-center flex-fill py-3 bg-warning bg-opacity-10 border-start border-end">
        <div class="fs-2 fw-bold text-warning">${ex.block_count ?? 0}</div>
        <div class="text-muted small fw-semibold">BLOCK</div>
      </div>
      <div class="text-center flex-fill py-3 bg-success bg-opacity-10 border-end">
        <div class="fs-2 fw-bold text-success">${ex.pass_count}</div>
        <div class="text-muted small fw-semibold">PASS</div>
      </div>
      <div class="text-center flex-fill py-3 bg-light">
        <div class="fs-2 fw-bold text-secondary">${ex.total_count}</div>
        <div class="text-muted small fw-semibold">총 건수</div>
      </div>
    </div>`;
  } else {
    const dis    = !ex ? 'disabled' : '';
    const failV  = ex ? ex.fail_count      : 0;
    const blockV = ex ? (ex.block_count ?? 0) : 0;
    const passV  = ex ? ex.pass_count      : 0;
    const total  = ex ? ex.total_count     : 0;
    const maxA   = ex ? `max="${total}"`   : '';
    failPassHtml = `
    <div class="d-flex border rounded-3 overflow-hidden mb-2">
      <div class="flex-fill text-center p-2 bg-danger bg-opacity-10 border-end">
        <label class="form-label fw-bold text-danger small mb-1 d-block">FAIL</label>
        <input type="number" id="fail-input"
               class="form-control text-center fw-bold text-danger border-danger"
               style="font-size:1.5rem;max-width:100px;margin:0 auto"
               min="0" ${maxA} value="${failV}" ${dis} oninput="updatePass()">
      </div>
      <div class="flex-fill text-center p-2 bg-warning bg-opacity-10 border-end">
        <label class="form-label fw-bold text-warning small mb-1 d-block">BLOCK</label>
        <input type="number" id="block-input"
               class="form-control text-center fw-bold text-warning border-warning"
               style="font-size:1.5rem;max-width:100px;margin:0 auto"
               min="0" ${maxA} value="${blockV}" ${dis} oninput="updatePass()">
      </div>
      <div class="flex-fill text-center p-2 bg-success bg-opacity-10 border-end">
        <div class="form-label fw-bold text-success small mb-1">PASS</div>
        <div id="pass-display" class="fw-bold text-success" style="font-size:1.5rem">${passV}</div>
      </div>
      <div class="flex-fill text-center p-2 bg-light">
        <div class="form-label fw-semibold text-muted small mb-1">총 건수</div>
        <div class="fw-bold text-secondary" style="font-size:1.5rem">${total}</div>
      </div>
    </div>`;
  }

  // ── 수행자 ───────────────────────────────────────────────────────────
  const performerValue = ex ? escHtml(ex.performer || '') : escHtml(_pendingPerformer);
  const performerHtml = `
  <div class="mb-2">
    <label class="form-label small fw-semibold mb-1"><i class="bi bi-person-fill me-1"></i>수행자</label>
    <input type="text" id="performer-input" class="form-control"
      placeholder="시험 수행자 이름…" value="${performerValue}">
  </div>`;

  // ── 코멘트 (남은 공간 채움) ──────────────────────────────────────────
  const commentValue = ex ? escHtml(ex.comment || '') : escHtml(_pendingComment);
  const commentHtml = `
  <div class="d-flex flex-column flex-fill mb-2" style="min-height:0">
    <label class="form-label small fw-semibold mb-1"><i class="bi bi-chat-left-text me-1"></i>코멘트</label>
    <textarea id="comment-input" class="form-control flex-fill" style="resize:none"
      placeholder="시험 관련 코멘트…">${commentValue}</textarea>
  </div>`;

  // ── 하단 버튼 ─────────────────────────────────────────────────────────
  let footerHtml;
  if (status === 'completed') {
    footerHtml = `
    <div class="d-flex justify-content-between gap-2">
      <button class="btn btn-outline-secondary" onclick="doReset()">
        <i class="bi bi-arrow-counterclockwise me-1"></i>재시험
      </button>
      <a href="/execution/" class="btn btn-secondary">
        <i class="bi bi-list-ul me-1"></i>목록으로
      </a>
    </div>`;
  } else {
    const dis = !ex ? 'disabled' : '';
    footerHtml = `
    <div class="d-flex justify-content-between gap-2">
      <button class="btn btn-outline-secondary" onclick="doReset()" ${dis}>
        <i class="bi bi-arrow-counterclockwise me-1"></i>재시험
      </button>
      <button class="btn btn-primary px-4" onclick="doComplete()" ${dis}>
        <i class="bi bi-check-lg me-1"></i>시험완료
      </button>
    </div>`;
  }

  const rightPanel = `
  <div class="d-flex flex-column flex-fill h-100 overflow-hidden" style="padding:1.25rem 1.25rem 1rem">
    ${timerSection}
    ${failPassHtml}
    ${performerHtml}
    ${commentHtml}
    ${footerHtml}
  </div>`;

  document.getElementById('detail-content').innerHTML = `
  <div class="d-flex h-100 overflow-hidden">
    ${leftPanel}
    ${rightPanel}
  </div>`;

  _attachHandlers();
  startLocalTimer();
}

// ── 핸들러 연결 ───────────────────────────────────────────────────────────

function _attachHandlers() {
  // 코멘트
  const ta = document.getElementById('comment-input');
  if (ta) {
    const saveComment = async () => {
      if (!_item?.execution?.id) { _pendingComment = ta.value; return; }
      try {
        await apiFetch('/execution/api/comment', 'PUT', {
          execution_id: _item.execution.id, comment: ta.value,
        });
        _item.execution.comment = ta.value;
      } catch { /* 무시 */ }
    };
    ta.addEventListener('blur', saveComment);
    ta.addEventListener('change', saveComment);
  }

  // 수행자
  const pi = document.getElementById('performer-input');
  if (pi) {
    const savePerformer = async () => {
      if (!_item?.execution?.id) { _pendingPerformer = pi.value; return; }
      try {
        await apiFetch('/execution/api/performer', 'PUT', {
          execution_id: _item.execution.id, performer: pi.value,
        });
        _item.execution.performer = pi.value;
      } catch { /* 무시 */ }
    };
    pi.addEventListener('blur', savePerformer);
    pi.addEventListener('change', savePerformer);
  }
}

function updatePass() {
  if (!_item?.execution) return;
  const total = _item.execution.total_count;
  const fail  = parseInt(document.getElementById('fail-input')?.value  || 0) || 0;
  const block = parseInt(document.getElementById('block-input')?.value || 0) || 0;
  document.getElementById('pass-display').textContent = Math.max(0, total - fail - block);
}

// ── 액션 핸들러 ───────────────────────────────────────────────────────────

async function doStart() {
  const ta = document.getElementById('comment-input');
  const pi = document.getElementById('performer-input');
  if (ta) _pendingComment   = ta.value;
  if (pi) _pendingPerformer = pi.value;

  try {
    const ex = await apiFetch('/execution/api/start', 'POST', {
      identifier_id: _item.identifier_id, task_id: _item.task_id,
    });
    _item.execution = {
      id: ex.id, status: ex.status, elapsed_seconds: 0,
      total_count: ex.total_count, fail_count: 0, block_count: 0, pass_count: 0,
      comment: _pendingComment, performer: _pendingPerformer,
    };
    const saves = [];
    if (_pendingComment)   saves.push(apiFetch('/execution/api/comment', 'PUT', { execution_id: ex.id, comment: _pendingComment }));
    if (_pendingPerformer) saves.push(apiFetch('/execution/api/performer', 'PUT', { execution_id: ex.id, performer: _pendingPerformer }));
    await Promise.all(saves);
    _pendingComment = ''; _pendingPerformer = '';
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
  const failCount  = parseInt(document.getElementById('fail-input')?.value  || 0) || 0;
  const blockCount = parseInt(document.getElementById('block-input')?.value || 0) || 0;
  try {
    const ex = await apiFetch('/execution/api/complete', 'POST', {
      execution_id: _item.execution.id, fail_count: failCount, block_count: blockCount,
    });
    stopLocalTimer();
    _item.execution = {
      ..._item.execution, status: 'completed',
      fail_count: ex.fail_count, block_count: ex.block_count ?? blockCount,
      pass_count: ex.pass_count, elapsed_seconds: _computeElapsed(ex),
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
    _pendingComment = ''; _pendingPerformer = '';
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
  // 전체화면 버튼 (#63)
  document.getElementById('btn-fullscreen').addEventListener('click', toggleFullscreen);

  try {
    _item = await apiFetch(`/execution/api/item/${encodeURIComponent(IDENTIFIER_ID)}`);
    renderPage();
  } catch {
    document.getElementById('detail-content').innerHTML =
      '<div class="alert alert-danger mt-3">항목을 찾을 수 없습니다.</div>';
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
