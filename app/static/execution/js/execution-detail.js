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

  // ── 왼쪽 패널: 정보 목록 (#71 순서: 문서 → 식별자 → ...) ───────────────
  const assignee = (item.assignee_names || []).join(', ') || '-';
  const infoRows = [
    ['문서',     escHtml(item.doc_name || '-')],
    ['식별자',   `<code style="color:#6366f1;font-weight:600">${escHtml(item.identifier_id)}</code>`],
    ['시험항목', escHtml(item.identifier_name)],
    ['담당자',   escHtml(assignee)],
    ['장소',     escHtml(item.location_name || '-')],
    ['날짜',     escHtml(item.scheduled_date || '-')],
    ['예상시간', formatMinutes(item.estimated_minutes)],
    ex ? ['총 건수', `<strong>${ex.total_count}</strong>건`] : null,
  ].filter(Boolean);

  const leftPanel = `
  <div class="exec-detail-sidebar">
    <div class="exec-sidebar-header">
      <div class="exec-sidebar-label">상태</div>
      <span class="exec-status-chip exec-badge-${status}" style="background:${cfg.bg};color:${cfg.border};border:1.5px solid ${cfg.border}">
        <span style="width:8px;height:8px;border-radius:50%;background:${cfg.border};display:inline-block"></span>
        ${cfg.label}
      </span>
    </div>
    <div class="exec-info-table">
      <div class="exec-sidebar-label mb-2">시험 정보</div>
      ${infoRows.map(([k, v]) => `
      <div class="exec-info-row">
        <span class="exec-info-key">${k}</span>
        <span class="exec-info-val">${v}</span>
      </div>`).join('')}
    </div>
  </div>`;

  // ── 오른쪽 패널 ─────────────────────────────────────────────────────
  const elapsed = ex?.elapsed_seconds ?? 0;
  let actionBtn;
  if      (status === 'pending')     actionBtn = `<button class="btn btn-success btn-lg px-5" onclick="doStart()"><i class="bi bi-play-fill me-2"></i>시험시작</button>`;
  else if (status === 'in_progress') actionBtn = `<button class="btn btn-warning btn-lg px-5" onclick="doPause()"><i class="bi bi-pause-fill me-2"></i>일시정지</button>`;
  else if (status === 'paused')      actionBtn = `<button class="btn btn-primary btn-lg px-5" onclick="doResume()"><i class="bi bi-play-fill me-2"></i>재시작</button>`;
  else                               actionBtn = `<span class="fs-5 fw-semibold" style="color:#15803d"><i class="bi bi-check-circle-fill me-2"></i>시험 완료</span>`;

  const timerColor = status === 'pending' ? '#94a3b8' : '#0f172a';
  const timerSection = `
  <div class="exec-timer-card" style="background:${cfg.bg};border:1.5px solid ${cfg.border}">
    <div class="flex-fill text-center">
      <div id="timer-display" class="exec-timer-value" style="color:${timerColor}">${formatElapsed(elapsed)}</div>
      <div class="exec-timer-label">경과 시간</div>
    </div>
    <div>${actionBtn}</div>
  </div>`;

  // ── FAIL / BLOCK / PASS ─────────────────────────────────────────────
  let failPassHtml;
  if (status === 'completed') {
    failPassHtml = `
    <div class="exec-counts-bar mb-3">
      <div class="exec-count-cell" style="background:#fef2f2">
        <div class="exec-count-label text-danger">FAIL</div>
        <div class="exec-count-value text-danger">${ex.fail_count}</div>
      </div>
      <div class="exec-count-cell" style="background:#fffbeb">
        <div class="exec-count-label text-warning">BLOCK</div>
        <div class="exec-count-value text-warning">${ex.block_count ?? 0}</div>
      </div>
      <div class="exec-count-cell" style="background:#f0fdf4">
        <div class="exec-count-label text-success">PASS</div>
        <div class="exec-count-value text-success">${ex.pass_count}</div>
      </div>
      <div class="exec-count-cell" style="background:#f8fafc">
        <div class="exec-count-label text-muted">총 건수</div>
        <div class="exec-count-value text-secondary">${ex.total_count}</div>
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
    <div class="exec-counts-bar mb-3">
      <div class="exec-count-cell" style="background:#fef2f2">
        <div class="exec-count-label text-danger">FAIL</div>
        <input type="number" id="fail-input" class="exec-count-input form-control text-danger border-danger"
               min="0" ${maxA} value="${failV}" ${dis} oninput="updatePass()">
      </div>
      <div class="exec-count-cell" style="background:#fffbeb">
        <div class="exec-count-label text-warning">BLOCK</div>
        <input type="number" id="block-input" class="exec-count-input form-control text-warning border-warning"
               min="0" ${maxA} value="${blockV}" ${dis} oninput="updatePass()">
      </div>
      <div class="exec-count-cell" style="background:#f0fdf4">
        <div class="exec-count-label text-success">PASS</div>
        <div id="pass-display" class="exec-count-value text-success">${passV}</div>
      </div>
      <div class="exec-count-cell" style="background:#f8fafc">
        <div class="exec-count-label text-muted">총 건수</div>
        <div class="exec-count-value text-secondary">${total}</div>
      </div>
    </div>`;
  }

  // ── 수행자 ───────────────────────────────────────────────────────────
  const performerValue = ex ? escHtml(ex.performer || '') : escHtml(_pendingPerformer);
  const performerHtml = `
  <div class="mb-3">
    <label class="form-label small fw-semibold text-muted mb-1">
      <i class="bi bi-person-fill me-1"></i>수행자
    </label>
    <input type="text" id="performer-input" class="form-control"
      placeholder="시험 수행자 이름…" value="${performerValue}">
  </div>`;

  // ── 코멘트 ───────────────────────────────────────────────────────────
  const commentValue = ex ? escHtml(ex.comment || '') : escHtml(_pendingComment);
  const commentHtml = `
  <div class="d-flex flex-column flex-fill mb-3" style="min-height:0">
    <label class="form-label small fw-semibold text-muted mb-1">
      <i class="bi bi-chat-left-text me-1"></i>코멘트
    </label>
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
      <a href="/execution/" class="btn btn-secondary px-4">
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
      <button class="btn btn-primary px-5" onclick="doComplete()" ${dis}>
        <i class="bi bi-check-lg me-1"></i>시험완료
      </button>
    </div>`;
  }

  document.getElementById('detail-content').innerHTML = `
  <div class="exec-detail-layout">
    ${leftPanel}
    <div class="exec-detail-main">
      ${timerSection}
      ${failPassHtml}
      ${performerHtml}
      ${commentHtml}
      ${footerHtml}
    </div>
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

// ── 바코드 감지 공통 유틸 ─────────────────────────────────────────────────

function _initBarcodeListener(onScan) {
  let buf = '', timer = null;
  document.addEventListener('keydown', e => {
    const tag = document.activeElement.tagName;
    if (tag === 'TEXTAREA' || tag === 'INPUT') return;
    if (e.key === 'Enter') {
      const code = buf.trim();
      buf = '';
      clearTimeout(timer);
      if (code) onScan(code);
      return;
    }
    if (/^[A-Z0-9_]$/.test(e.key)) {
      buf += e.key;
      clearTimeout(timer);
      timer = setTimeout(() => { buf = ''; }, 80);
    }
  });
}

function _tryAutoStart() {
  if (!_item) return;
  const status = _item.execution?.status ?? 'pending';
  if (status === 'pending') doStart();
  else if (status === 'paused') doResume();
}

// ── 초기화 ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  // 전체화면 버튼
  document.getElementById('btn-fullscreen').addEventListener('click', toggleFullscreen);


  try {
    _item = await apiFetch(`/execution/api/item/${encodeURIComponent(IDENTIFIER_ID)}`);
    renderPage();
    // ?autostart=1 파라미터로 진입 시 자동시작 (#78)
    if (new URLSearchParams(window.location.search).get('autostart') === '1') {
      _tryAutoStart();
    }
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

  // 바코드 감지 (#76 TERMINATE, #78 OPEN)
  _initBarcodeListener(code => {
    if (code === 'TERMINATE') {
      if (_item?.execution?.status === 'in_progress') doPause();
    } else if (code.startsWith('OPEN_')) {
      const identifierId = code.slice(5).replace(/_/g, '-');
      if (identifierId === IDENTIFIER_ID) {
        _tryAutoStart();
      } else {
        window.location.href = `/execution/${encodeURIComponent(identifierId)}?autostart=1`;
      }
    }
  });
});
