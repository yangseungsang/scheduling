'use strict';

/**
 * execution-detail.js — 시험 개별 항목 실행 화면 컨트롤러
 *
 * 역할:
 *   - 단일 식별자(identifier)에 대한 시험 실행 상태를 표시·제어한다.
 *   - 상태 머신: pending → in_progress ↔ paused → completed
 *                doReset() 호출 시 execution 레코드 삭제 → pending으로 복귀
 *
 * 의존성:
 *   - Bootstrap 5 (Modal, Tooltip)
 *   - Bootstrap Icons
 *   - 전역 변수 IDENTIFIER_ID, BARCODE_PREFIX (Jinja2 템플릿이 인라인으로 주입)
 *
 * 설계 결정:
 *   - 화면 전체를 renderPage()로 재생성하는 방식 — DOM 파편 최소화, 상태 동기화 단순화
 *   - 서버는 segments[] 배열로 시험 구간을 저장하고, 클라이언트는
 *     elapsed_seconds(서버 계산값)를 _timerBase로 사용해 로컬 타이머를 돌린다.
 */

// ── 전역 상태 ────────────────────────────────────────────────────────────────

/** 서버에서 받아온 시험 항목 전체 데이터 (item + item.execution). DOMContentLoaded 후 채워진다. */
let _item = null;

/**
 * 시험이 아직 시작되지 않은(pending) 상태에서 미리 입력한 코멘트.
 * doStart() 호출 시 execution 생성 직후 /api/comment 로 전송된다.
 * localStorage('pending_comment_<IDENTIFIER_ID>')에도 백업된다.
 */
let _pendingComment = '';

/**
 * 시험이 아직 시작되지 않은(pending) 상태에서 미리 입력한 수행자 이름.
 * doStart() 호출 시 execution 생성 직후 /api/performer 로 전송된다.
 */
let _pendingPerformer = '';

/** 현재 로그인한 사용자 이름. /api/whoami 로 초기화, 사용자 모달에서 변경 가능. */
let _currentUser = '';

// ── 사용자 모달 ───────────────────────────────────────────────────────────────

/** 사용자 이름 변경 모달을 열고, 현재 이름을 input에 미리 채운다. */
function openUserModal() {
  const modal = new bootstrap.Modal(document.getElementById('userModal'));
  const input = document.getElementById('user-modal-input');
  if (input) input.value = _currentUser;
  modal.show();
  setTimeout(() => input?.focus(), 300);
}

/**
 * 모달에서 입력한 이름을 서버(/api/login)에 저장하고,
 * localStorage와 툴바 표시에 반영한다.
 * 수행자 input이 열려 있으면 그 값도 함께 갱신한다.
 */
async function applyUserFromModal() {
  const input = document.getElementById('user-modal-input');
  const name = input ? input.value.trim() : '';
  if (!name) return;

  await apiFetch('/execution/api/login', 'POST', { username: name });
  _currentUser = name;
  localStorage.setItem('execution_quick_user', name);
  _updateToolbarUser();

  // 상세 화면에 수행자 input이 이미 렌더링된 경우, 값을 동기화한다.
  const performer = document.getElementById('performer-input');
  if (performer) {
    performer.value = name;
    performer.dispatchEvent(new Event('change'));
  }

  bootstrap.Modal.getInstance(document.getElementById('userModal'))?.hide();
}

/** 툴바의 사용자 이름 표시 요소를 _currentUser로 갱신한다. */
function _updateToolbarUser() {
  const el = document.getElementById('toolbar-username');
  if (el) el.textContent = _currentUser || '(미설정)';
}

/**
 * localStorage에 저장된 이름이 있으면 수행자 input에 즉시 채운다.
 * 없으면 사용자 모달을 열어 이름을 입력받는다.
 */
function doQuickAssign() {
  const cached = localStorage.getItem('execution_quick_user') || '';
  if (!cached) { openUserModal(); return; }
  const performer = document.getElementById('performer-input');
  if (performer) {
    performer.value = cached;
    performer.dispatchEvent(new Event('change'));
  }
}

// ── 타이머 전역 변수 ──────────────────────────────────────────────────────────

/**
 * setInterval 핸들. in_progress 상태일 때만 살아 있다.
 * stopLocalTimer()가 clearInterval 후 null로 초기화한다.
 */
let _timerInterval = null;

/**
 * 이미 경과된 초(서버의 elapsed_seconds).
 * startLocalTimer() 호출 시 ex.elapsed_seconds로 채워진다.
 * 매 tick마다 _timerBase + (Date.now() - _timerStart)/1000 으로 화면을 갱신한다.
 */
let _timerBase = 0;

/**
 * 로컬 타이머 시작 시각(밀리초). Date.now() 기준.
 * stopLocalTimer()가 null로 초기화한다.
 */
let _timerStart = null;

// ── 상태별 UI 설정 ────────────────────────────────────────────────────────────

/**
 * 상태(status) → 배경색·테두리·배지 클래스·한글 레이블 매핑.
 * renderPage()가 타이머 카드와 사이드바 상태 뱃지에 사용한다.
 */
const STATUS_CFG = {
  pending:     { bg: '#f1f5f9', border: '#94a3b8', badge: 'bg-secondary',         label: '대기' },
  in_progress: { bg: '#dbeafe', border: '#3b82f6', badge: 'bg-primary',           label: '진행 중' },
  paused:      { bg: '#fef9c3', border: '#eab308', badge: 'bg-warning text-dark',  label: '일시정지' },
  completed:   { bg: '#dcfce7', border: '#22c55e', badge: 'bg-success',            label: '완료' },
};

// ── 유틸 ──────────────────────────────────────────────────────────────────────

/** 초를 HH:MM:SS 문자열로 변환한다. 타이머 표시에 사용. */
function formatElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

/** 분(mins)을 "N분" 형태로 반환한다. 값이 없으면 '-'. */
function formatMinutes(mins) {
  if (!mins) return '-';
  return `${mins}분`;
}

/** HTML 특수문자를 엔티티로 이스케이프한다. XSS 방지용. */
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** JSON API 요청 공통 래퍼. 오류 시 Error를 throw한다. */
async function apiFetch(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}

// ── 전체화면 (#63) ────────────────────────────────────────────────────────────

/** 전체화면을 토글한다. fullscreenchange 이벤트로 아이콘도 갱신된다. */
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

// ── 타이머 ────────────────────────────────────────────────────────────────────

/**
 * 로컬 타이머를 시작한다.
 *
 * 서버의 elapsed_seconds를 _timerBase에 저장하고, 이후 매 1초마다
 * _timerBase + (현재 시각 - _timerStart) 를 계산해 #timer-display를 갱신한다.
 *
 * in_progress 상태가 아니면 아무것도 하지 않는다.
 * 이미 타이머가 돌고 있으면 먼저 중단(stopLocalTimer)한 뒤 재시작한다.
 */
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

/**
 * 로컬 타이머를 중단하고 관련 변수를 초기화한다.
 * doPause / doComplete / doReset / renderPage 전에 호출해 잔여 interval을 정리한다.
 */
function stopLocalTimer() {
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  _timerBase = 0; _timerStart = null;
}

// ── 렌더링 (#62 리디자인) ──────────────────────────────────────────────────────

/** pending이 아니면(= 한 번이라도 시작된 적 있으면) true를 반환한다. */
function _isStarted(ex) {
  return ex && ex.status !== 'pending';
}

/**
 * 상세 화면 전체를 현재 _item 상태로 다시 그린다.
 *
 * 레이아웃 구조:
 *   .exec-detail-layout
 *     └ 왼쪽 사이드바 (.exec-detail-sidebar): 식별자 정보 + 담당자·날짜·장소 요약
 *     └ 오른쪽 메인 (.exec-detail-main):
 *         - 타이머 카드 (상태별 배경색, 액션 버튼)
 *         - FAIL/BLOCK/PASS 입력 또는 완료 결과 표시
 *         - 수행자 input
 *         - 코멘트 textarea
 *         - 하단 버튼 (초기화 / 코멘트 저장 / 시험완료 or 목록으로)
 *
 * 렌더링 후 _attachHandlers()와 startLocalTimer()를 호출해 이벤트와 타이머를 재연결한다.
 */
function renderPage() {
  const item   = _item;
  const ex     = item.execution;
  const status = ex?.status ?? 'pending';
  const cfg    = STATUS_CFG[status] || STATUS_CFG.pending;

  const assignee = (item.assignee_names || []).join(', ') || '-';

  const leftPanel = `
  <div class="exec-detail-sidebar">
    <div class="sidebar-top">
      <div class="sidebar-id">${escHtml(item.identifier_id)}</div>
      <div class="sidebar-name">${escHtml(item.identifier_name)}</div>
      <span class="sidebar-status sidebar-status--${status}">
        ${cfg.label}
      </span>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-field">
        <div class="sidebar-field-label">문서</div>
        <div class="sidebar-field-value">${escHtml(item.doc_name || '-')}</div>
      </div>
      <div class="sidebar-field">
        <div class="sidebar-field-label">담당자</div>
        <div class="sidebar-field-value">${escHtml(assignee)}</div>
      </div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-row">
        <div class="sidebar-field">
          <div class="sidebar-field-label">장소</div>
          <div class="sidebar-field-value">${escHtml(item.location_name || '-')}</div>
        </div>
        <div class="sidebar-field">
          <div class="sidebar-field-label">날짜</div>
          <div class="sidebar-field-value">${escHtml(item.scheduled_date || '-')}</div>
        </div>
      </div>
      <div class="sidebar-row">
        <div class="sidebar-field">
          <div class="sidebar-field-label">예상시간</div>
          <div class="sidebar-field-value">${formatMinutes(item.estimated_minutes)}</div>
        </div>
        ${ex ? `<div class="sidebar-field">
          <div class="sidebar-field-label">총 건수</div>
          <div class="sidebar-field-value">${ex.total_count}건</div>
        </div>` : ''}
      </div>
    </div>
  </div>`;

  // ── 타이머 카드 ────────────────────────────────────────────────────────────
  // 상태에 따라 액션 버튼 레이블이 달라진다:
  //   pending → doStart() "시험시작"
  //   in_progress → doPause() "일시정지"
  //   paused → doResume() "재시작"
  //   completed → 버튼 없음 (텍스트 표시만)
  const elapsed = ex?.elapsed_seconds ?? 0;
  let actionBtn;
  if      (status === 'pending')     actionBtn = `<button class="btn btn-success btn-lg px-5" onclick="doStart()"><i class="bi bi-play-fill me-2"></i>시험시작</button>`;
  else if (status === 'in_progress') actionBtn = `<button class="btn btn-warning btn-lg px-5" onclick="doPause()"><i class="bi bi-pause-fill me-2"></i>일시정지</button>`;
  else if (status === 'paused')      actionBtn = `<button class="btn btn-primary btn-lg px-5" onclick="doResume()"><i class="bi bi-play-fill me-2"></i>재시작</button>`;
  else                               actionBtn = `<span class="fs-5 fw-semibold" style="color:#15803d"><i class="bi bi-check-circle-fill me-2"></i>시험 완료</span>`;

  // pending일 때는 타이머를 회색으로 표시해 "아직 시작 안 됨"을 명시한다.
  const timerColor = status === 'pending' ? '#94a3b8' : '#0f172a';
  const timerSection = `
  <div class="exec-timer-card" style="background:${cfg.bg};border:1.5px solid ${cfg.border}">
    <div class="flex-fill text-center">
      <div id="timer-display" class="exec-timer-value" style="color:${timerColor}">${formatElapsed(elapsed)}</div>
      <div class="exec-timer-label">경과 시간</div>
    </div>
    <div>${actionBtn}</div>
  </div>`;

  // ── FAIL / BLOCK / PASS 영역 ───────────────────────────────────────────────
  // completed 상태: 읽기 전용 숫자 표시
  // 그 외: FAIL/BLOCK은 number input, PASS는 자동 계산(updatePass)
  // 아직 시작 전(pending)이면 input을 disabled 처리해 입력 불가로 만든다.
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
    const started = _isStarted(ex);
    const dis    = !started ? 'disabled' : '';
    const failV  = started ? ex.fail_count      : 0;
    const blockV = started ? (ex.block_count ?? 0) : 0;
    const passV  = started ? ex.pass_count      : 0;
    const total  = started ? ex.total_count     : 0;
    const maxA   = started ? `max="${total}"`   : '';
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

  // ── 수행자 입력 ────────────────────────────────────────────────────────────
  // 시험이 시작된 경우: execution.performer 값 사용
  // 시작 전(pending): _pendingPerformer 사용 (없으면 _currentUser로 대체)
  const rawPerformer = _isStarted(ex) ? (ex.performer || '') : _pendingPerformer;
  const performerValue = escHtml(rawPerformer || _currentUser);
  const performerHtml = `
  <div class="mb-3">
    <label class="form-label small fw-semibold text-muted mb-1">
      <i class="bi bi-person-fill me-1"></i>수행자
    </label>
    <div class="input-group">
      <input type="text" id="performer-input" class="form-control"
        placeholder="시험 수행자 이름…" value="${performerValue}">
      <button type="button" class="btn btn-outline-secondary btn-sm" onclick="doQuickAssign()" title="저장된 이름 빠른 할당">
        <i class="bi bi-lightning-fill"></i>
      </button>
      <button type="button" class="btn btn-outline-secondary btn-sm" onclick="openUserModal()" title="사용자 선택">
        <i class="bi bi-person-lines-fill"></i>
      </button>
    </div>
  </div>`;

  // ── 코멘트 입력 ────────────────────────────────────────────────────────────
  // 시험 시작 전에는 _pendingComment를 보여준다. 시작 후에는 ex.comment를 표시.
  const commentValue = escHtml(ex?.comment || _pendingComment);
  const commentHtml = `
  <div class="d-flex flex-column flex-fill mb-3" style="min-height:0">
    <label class="form-label small fw-semibold text-muted mb-1">
      <i class="bi bi-chat-left-text me-1"></i>코멘트
    </label>
    <textarea id="comment-input" class="form-control flex-fill" style="resize:none"
      placeholder="시험 관련 코멘트…">${commentValue}</textarea>
  </div>`;

  // ── 하단 버튼 ─────────────────────────────────────────────────────────────
  // completed 상태: 초기화 + 코멘트 저장 + 목록으로
  // 그 외: 초기화(started일 때만 활성) + 코멘트 저장 + 시험완료(started일 때만 활성)
  let footerHtml;
  if (status === 'completed') {
    footerHtml = `
    <div class="d-flex justify-content-between gap-2">
      <button class="btn btn-outline-secondary" onclick="doReset()">
        <i class="bi bi-arrow-counterclockwise me-1"></i>초기화
      </button>
      <div class="d-flex gap-2">
        <button id="btn-save-comment" class="btn btn-outline-success" onclick="doSaveComment()" disabled>
          <i class="bi bi-floppy me-1"></i>코멘트 저장
        </button>
        <a href="/execution/" class="btn btn-secondary px-4">
          <i class="bi bi-list-ul me-1"></i>목록으로
        </a>
      </div>
    </div>`;
  } else {
    const started = _isStarted(ex);
    const dis = !started ? 'disabled' : '';
    footerHtml = `
    <div class="d-flex justify-content-between gap-2">
      <button class="btn btn-outline-secondary" onclick="doReset()" ${dis}>
        <i class="bi bi-arrow-counterclockwise me-1"></i>초기화
      </button>
      <div class="d-flex gap-2">
        <button id="btn-save-comment" class="btn btn-outline-success" onclick="doSaveComment()" disabled>
          <i class="bi bi-floppy me-1"></i>코멘트 저장
        </button>
        <button class="btn btn-primary px-5" onclick="doComplete()" ${dis}>
          <i class="bi bi-check-lg me-1"></i>시험완료
        </button>
      </div>
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

  // 렌더링 후 이벤트 핸들러 재연결 및 타이머 재시작
  _attachHandlers();
  startLocalTimer();
}

// ── 핸들러 연결 ───────────────────────────────────────────────────────────────

/**
 * renderPage() 호출 후 DOM이 새로 생성되므로,
 * 이벤트 리스너도 매번 새로 등록해야 한다.
 *
 * - 코멘트 textarea: 변경 시 저장 버튼 활성화 + btn-save-changed 강조
 * - 수행자 input: blur/change 시 서버에 PUT (started 상태일 때만),
 *                 pending 상태면 _pendingPerformer에만 임시 보관
 */
function _attachHandlers() {
  // 코멘트 변경 감지
  const ta = document.getElementById('comment-input');
  const saveBtn = document.getElementById('btn-save-comment');
  if (ta && saveBtn) {
    ta.addEventListener('input', () => {
      // 저장된 값(서버 또는 pending)과 비교해 변경 여부를 판단한다.
      const saved = _item?.execution?.comment || _pendingComment;
      const changed = ta.value !== saved;
      saveBtn.classList.toggle('btn-save-changed', changed);
      saveBtn.disabled = !changed;
    });
  }

  // 수행자
  const pi = document.getElementById('performer-input');
  if (pi) {
    const savePerformer = async () => {
      // 시험이 시작되지 않은 경우, 서버 호출 없이 임시 변수에만 보관한다.
      if (!_isStarted(_item?.execution)) { _pendingPerformer = pi.value; return; }
      try {
        await apiFetch('/execution/api/performer', 'PUT', {
          execution_id: _item.execution.id, performer: pi.value,
        });
        _item.execution.performer = pi.value;
      } catch { /* 실패 시 무시 — 다음 저장 시 재시도 가능 */ }
    };
    pi.addEventListener('blur', savePerformer);
    pi.addEventListener('change', savePerformer);
  }
}

// ── pending 코멘트 영속화 ──────────────────────────────────────────────────────

/**
 * 식별자별 localStorage 키를 반환한다.
 * IDENTIFIER_ID가 없는 환경(테스트 등)에서도 충돌하지 않도록 빈 문자열을 허용한다.
 */
function _pendingCommentKey() {
  return `pending_comment_${typeof IDENTIFIER_ID !== 'undefined' ? IDENTIFIER_ID : ''}`;
}

/** _pendingComment를 갱신하고 localStorage에도 백업한다. */
function _savePendingComment(value) {
  _pendingComment = value;
  try { localStorage.setItem(_pendingCommentKey(), value); } catch { /* 무시 */ }
}

/** localStorage에서 pending 코멘트를 복원한다. 없으면 빈 문자열 반환. */
function _loadPendingComment() {
  try { return localStorage.getItem(_pendingCommentKey()) || ''; } catch { return ''; }
}

/** 시험 시작 후 불필요해진 pending 코멘트를 메모리와 localStorage에서 제거한다. */
function _clearPendingComment() {
  _pendingComment = '';
  try { localStorage.removeItem(_pendingCommentKey()); } catch { /* 무시 */ }
}

// ── 코멘트 저장 UI 피드백 ─────────────────────────────────────────────────────

/**
 * 저장 성공 시 버튼을 "저장됨"으로 1.5초간 표시한 뒤 원래 레이블로 복원한다.
 * 버튼은 저장 직후 disabled 처리해 중복 저장을 방지한다.
 */
function _showSaveFeedback(saveBtn) {
  saveBtn.classList.remove('btn-save-changed');
  saveBtn.disabled = true;
  const origHtml = saveBtn.innerHTML;
  saveBtn.innerHTML = '<i class="bi bi-check-lg me-1"></i>저장됨';
  saveBtn.classList.add('btn-save-done');
  setTimeout(() => {
    saveBtn.innerHTML = origHtml;
    saveBtn.classList.remove('btn-save-done');
  }, 1500);
}

/**
 * 코멘트를 저장한다.
 *
 * 두 가지 경로:
 *   1. 시험 미시작(pending): /api/pending-comment 로 전송 + localStorage 백업
 *   2. 시험 시작 후: /api/comment 로 전송
 *
 * 저장 성공 시 _showSaveFeedback()으로 시각적 피드백을 제공한다.
 */
async function doSaveComment() {
  const ta = document.getElementById('comment-input');
  const saveBtn = document.getElementById('btn-save-comment');
  if (!ta) return;

  if (!_isStarted(_item?.execution)) {
    // pending 상태: localStorage에 먼저 저장하고, 서버에도 시도한다.
    _savePendingComment(ta.value);
    try {
      await apiFetch('/execution/api/pending-comment', 'PUT', {
        identifier_id: _item.identifier_id, task_id: _item.task_id, comment: ta.value,
      });
      if (_item.execution) _item.execution.comment = ta.value;
    } catch { /* localStorage에는 이미 저장됨 — 서버 실패는 무시 */ }
    if (saveBtn) _showSaveFeedback(saveBtn);
    return;
  }
  try {
    await apiFetch('/execution/api/comment', 'PUT', {
      execution_id: _item.execution.id, comment: ta.value,
    });
    _item.execution.comment = ta.value;
    if (saveBtn) _showSaveFeedback(saveBtn);
  } catch { alert('코멘트 저장 실패'); }
}

/**
 * FAIL/BLOCK 입력 변경 시 PASS를 자동 계산해 표시한다.
 * PASS = total_count - fail - block (최솟값 0)
 */
function updatePass() {
  if (!_item?.execution) return;
  const total = _item.execution.total_count;
  const fail  = parseInt(document.getElementById('fail-input')?.value  || 0) || 0;
  const block = parseInt(document.getElementById('block-input')?.value || 0) || 0;
  document.getElementById('pass-display').textContent = Math.max(0, total - fail - block);
}

// ── 액션 핸들러 ───────────────────────────────────────────────────────────────

/**
 * 시험을 시작한다 (pending → in_progress).
 *
 * 처리 순서:
 *   1. 현재 입력된 코멘트·수행자를 pending 변수에 임시 보관
 *   2. POST /api/start 호출 (409: 이미 다른 시험 진행 중)
 *   3. 응답의 execution 객체로 _item.execution 초기화
 *   4. _pendingComment / _pendingPerformer가 있으면 각각 API로 전송
 *   5. pending 임시 데이터 정리 후 renderPage()
 *
 * doResume()과 달리 /start 엔드포인트를 사용하고,
 * execution 레코드를 새로 생성한다는 점이 다르다.
 */
async function doStart() {
  const ta = document.getElementById('comment-input');
  const pi = document.getElementById('performer-input');
  if (ta) _savePendingComment(ta.value);
  if (pi) _pendingPerformer = pi.value;

  try {
    const resp = await fetch('/execution/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier_id: _item.identifier_id, task_id: _item.task_id }),
    });
    if (resp.status === 409) {
      // 다른 시험이 진행 중인 경우 서버가 409로 응답한다.
      const err = await resp.json();
      alert(err.error || '시험을 시작할 수 없습니다.');
      return;
    }
    if (!resp.ok) throw new Error(`API error ${resp.status}`);
    const ex = await resp.json();
    // 서버 응답의 최소 필드로 로컬 execution 객체를 초기화한다.
    _item.execution = {
      id: ex.id, status: ex.status, elapsed_seconds: 0,
      total_count: ex.total_count, fail_count: 0, block_count: 0, pass_count: 0,
      comment: _pendingComment, performer: ex.performer || _pendingPerformer,
    };
    // 시작 전에 입력된 코멘트·수행자를 이제 실제 execution에 반영한다.
    if (_pendingComment)   await apiFetch('/execution/api/comment', 'PUT', { execution_id: ex.id, comment: _pendingComment });
    if (_pendingPerformer && !ex.performer) await apiFetch('/execution/api/performer', 'PUT', { execution_id: ex.id, performer: _pendingPerformer });
    _clearPendingComment();
    _pendingPerformer = '';
    renderPage();
  } catch { alert('시험시작 실패'); }
}

/**
 * 진행 중인 시험을 일시정지한다 (in_progress → paused).
 *
 * /api/pause 응답에는 업데이트된 segments 배열이 포함되어 있으며,
 * _computeElapsed()로 경과 시간을 재계산해 _item.execution에 반영한다.
 * 로컬 타이머도 즉시 중단한다.
 */
async function doPause() {
  try {
    const ex = await apiFetch('/execution/api/pause', 'POST', { execution_id: _item.execution.id });
    stopLocalTimer();
    _item.execution = { ..._item.execution, status: 'paused', elapsed_seconds: _computeElapsed(ex) };
    renderPage();
  } catch { alert('일시정지 실패'); }
}

/**
 * 일시정지된 시험을 재개한다 (paused → in_progress).
 *
 * doStart()와 달리 /resume 엔드포인트를 사용하며,
 * 기존 execution 레코드에 새 segment를 추가하는 방식으로 동작한다.
 * elapsed_seconds는 segments를 다시 합산해 갱신한다.
 */
async function doResume() {
  try {
    const ex = await apiFetch('/execution/api/resume', 'POST', { execution_id: _item.execution.id });
    _item.execution.status = 'in_progress';
    _item.execution.elapsed_seconds = _computeElapsed(ex);
    renderPage();
  } catch { alert('재시작 실패'); }
}

/**
 * 시험을 완료 처리한다 (in_progress|paused → completed).
 *
 * FAIL/BLOCK 입력값을 읽어 /api/complete 에 전송한다.
 * PASS는 서버가 계산해 응답에 포함한다.
 * 코멘트도 완료와 동시에 /api/comment 로 저장한다.
 */
async function doComplete() {
  const failCount  = parseInt(document.getElementById('fail-input')?.value  || 0) || 0;
  const blockCount = parseInt(document.getElementById('block-input')?.value || 0) || 0;
  const comment    = document.getElementById('comment-input')?.value ?? '';
  try {
    const ex = await apiFetch('/execution/api/complete', 'POST', {
      execution_id: _item.execution.id, fail_count: failCount, block_count: blockCount,
    });
    await apiFetch('/execution/api/comment', 'PUT', {
      execution_id: _item.execution.id, comment,
    });
    stopLocalTimer();
    _item.execution = {
      ..._item.execution, status: 'completed',
      fail_count: ex.fail_count, block_count: ex.block_count ?? blockCount,
      pass_count: ex.pass_count, elapsed_seconds: _computeElapsed(ex),
      comment,
    };
    renderPage();
  } catch { alert('완료 처리 실패'); }
}

/**
 * 시험 기록을 초기화한다 (completed|any → pending).
 *
 * /api/reset 으로 서버의 execution 레코드를 삭제하고,
 * _item.execution = null 로 로컬 상태도 초기화한다.
 * 확인 대화상자로 실수 방지.
 */
async function doReset() {
  if (!_item?.execution?.id) return;
  if (!confirm('초기화하면 현재 기록이 삭제됩니다. 계속할까요?')) return;
  try {
    await apiFetch('/execution/api/reset', 'POST', { execution_id: _item.execution.id });
    stopLocalTimer();
    _item.execution = null;
    _clearPendingComment(); _pendingPerformer = '';
    renderPage();
  } catch { alert('재시험 처리 실패'); }
}

/**
 * 서버 응답의 segments 배열을 합산해 총 경과 시간(초)을 반환한다.
 *
 * 각 segment는 {start: ISO문자열, end: ISO문자열|null} 형태이며,
 * end가 null이면 현재 시각까지 계산한다 (in_progress 상태의 마지막 구간).
 *
 * 서버가 elapsed_seconds를 직접 내려주기도 하지만,
 * doPause/doResume/doComplete 직후에는 segments가 가장 정확하므로
 * 클라이언트에서 재계산해 사용한다.
 */
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

// ── 바코드 스캐너 ─────────────────────────────────────────────────────────────

/**
 * 바코드 스캐너 입력을 감지하는 공통 유틸.
 *
 * 동작 원리:
 *   - 키보드 keydown 이벤트를 리스닝한다.
 *   - 대문자·숫자·하이픈(-) 문자가 80ms 이내에 연속 입력되면 buf에 누적한다.
 *   - 80ms 이상 입력이 없으면 buf를 초기화한다 (일반 키보드 입력과 구분).
 *   - Enter 키가 오면 누적된 buf를 onScan 콜백에 전달한다.
 *   - textarea/input에 포커스가 있으면 처리하지 않는다 (사용자 타이핑 방해 방지).
 *
 * 지원 바코드 형식:
 *   - `OPEN-TC-001`: 해당 식별자 페이지로 이동 (BARCODE_PREFIX 처리 후 TC-001 추출)
 *   - `TERMINATE`: 현재 진행 중인 시험을 일시정지
 */
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
    if (/^[A-Z0-9-]$/.test(e.key)) {
      buf += e.key;
      clearTimeout(timer);
      // 80ms 초과 시 버퍼를 초기화해 일반 키보드 입력을 무시한다.
      timer = setTimeout(() => { buf = ''; }, 80);
    }
  });
}

/**
 * 바코드 코드에서 식별자 ID를 추출한다.
 *
 * 예: BARCODE_PREFIX='', code='OPEN-TC-001' → 'TC-001'
 *     BARCODE_PREFIX='SW-', code='OPEN-SW-TC-001' → 'SW-TC-001'
 *
 * 첫 번째 '-' 앞의 'OPEN' 세그먼트를 제거하고,
 * BARCODE_PREFIX를 앞에 붙여 반환한다.
 */
function _barcodeToId(code) {
  const parts = code.split('-');
  return (typeof BARCODE_PREFIX !== 'undefined' ? BARCODE_PREFIX : '') + parts.slice(1).join('-');
}

/**
 * 현재 상태에 따라 자동으로 시작 또는 재개를 시도한다.
 * ?autostart=1 파라미터나 OPEN 바코드 스캔 시 사용된다.
 */
function _tryAutoStart() {
  if (!_item) return;
  const status = _item.execution?.status ?? 'pending';
  if (status === 'pending') doStart();
  else if (status === 'paused') doResume();
}

// ── 초기화 ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  // 전체화면 버튼
  document.getElementById('btn-fullscreen').addEventListener('click', toggleFullscreen);

  // 서버에서 현재 로그인 사용자를 불러온다.
  // 실패하면 localStorage의 캐시 값을 사용한다.
  try {
    const who = await apiFetch('/execution/api/whoami');
    _currentUser = who.username || localStorage.getItem('execution_quick_user') || '';
    _updateToolbarUser();
  } catch { /* 무시 */ }

  try {
    // IDENTIFIER_ID는 Jinja2 템플릿이 <script>로 주입하는 전역 변수다.
    _item = await apiFetch(`/execution/api/item/${encodeURIComponent(IDENTIFIER_ID)}`);
    if (!_isStarted(_item.execution)) {
      // pending 상태: 이전에 미리 입력해 둔 코멘트를 localStorage에서 복원한다.
      _pendingComment = _item.execution?.comment || _loadPendingComment();
    }
    renderPage();
    // ?autostart=1 파라미터로 진입 시 자동시작 (#78)
    // 바코드 스캔으로 목록 → 상세 페이지 이동 시 자동으로 시험을 시작한다.
    if (new URLSearchParams(window.location.search).get('autostart') === '1') {
      _tryAutoStart();
    }
  } catch {
    document.getElementById('detail-content').innerHTML =
      '<div class="alert alert-danger mt-3">항목을 찾을 수 없습니다.</div>';
  }

  // 스페이스바 단축키: 포커스가 입력 요소에 없을 때 상태를 토글한다.
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

  // 바코드 감지 처리 (#76 TERMINATE, #78 OPEN)
  _initBarcodeListener(code => {
    if (code === 'TERMINATE') {
      // TERMINATE 바코드: 현재 진행 중인 시험을 일시정지한다.
      if (_item?.execution?.status === 'in_progress') doPause();
    } else if (code.startsWith('OPEN-')) {
      // OPEN-<식별자> 바코드: 해당 식별자 페이지로 이동하거나 현재 항목을 자동 시작한다.
      const identifierId = _barcodeToId(code);
      if (identifierId === IDENTIFIER_ID) {
        // 같은 식별자 바코드 → 자동 시작/재개
        _tryAutoStart();
      } else {
        // 다른 식별자 바코드 → 해당 상세 페이지로 이동 (autostart 포함)
        window.location.href = `/execution/${encodeURIComponent(identifierId)}?autostart=1`;
      }
    }
  });
});
