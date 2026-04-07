/**
 * 모달 다이얼로그 모듈 — 확인 모달과 메모 모달을 제공한다.
 * 브라우저 기본 confirm/prompt를 대체하는 커스텀 UI.
 * window.ScheduleApp 네임스페이스에 등록된다.
 */
window.ScheduleApp = window.ScheduleApp || {};
(function (App) {
  'use strict';

  var api = App.api;
  var showToast = App.showToast;

  // =====================================================================
  // 커스텀 확인 모달 (브라우저 confirm 대체)
  // =====================================================================
  /**
   * 확인/취소 버튼이 있는 커스텀 확인 모달을 표시한다.
   * 브라우저 기본 confirm() 대신 사용하여 일관된 UI를 제공한다.
   * @param {string} message - 모달에 표시할 메시지 (HTML 가능)
   * @param {Object} [opts={}] - 옵션
   * @param {string} [opts.title] - 모달 제목
   * @param {string|boolean} [opts.icon='question-circle-fill'] - Bootstrap 아이콘 이름 (false면 숨김)
   * @param {string} [opts.okText='확인'] - 확인 버튼 텍스트
   * @param {string} [opts.cancelText='취소'] - 취소 버튼 텍스트
   * @returns {Promise<boolean>} 확인 시 true, 취소 시 false
   */
  function showConfirmModal(message, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      // 기존 모달 제거
      var old = document.getElementById('confirm-modal');
      if (old) old.remove();

      // 오버레이 및 모달 박스 생성
      var overlay = document.createElement('div');
      overlay.id = 'confirm-modal';
      overlay.className = 'remaining-alert-overlay';
      overlay.innerHTML =
        '<div class="remaining-alert-box">' +
          // 아이콘 (opts.icon이 false가 아닐 때만 표시)
          (opts.icon !== false
            ? '<div class="remaining-alert-icon"><i class="bi bi-' + (opts.icon || 'question-circle-fill') + '"></i></div>'
            : '') +
          (opts.title ? '<div class="remaining-alert-title">' + opts.title + '</div>' : '') +
          '<div class="remaining-alert-body">' + message + '</div>' +
          '<div style="display:flex;gap:8px;justify-content:center;margin-top:12px;">' +
            '<button class="remaining-alert-btn" id="confirm-modal-cancel" style="background:#94a3b8">' + (opts.cancelText || '취소') + '</button>' +
            '<button class="remaining-alert-btn" id="confirm-modal-ok">' + (opts.okText || '확인') + '</button>' +
          '</div>' +
        '</div>';

      document.body.appendChild(overlay);

      // 확인 버튼 → true로 resolve
      document.getElementById('confirm-modal-ok').addEventListener('click', function () {
        overlay.remove();
        resolve(true);
      });
      // 취소 버튼 → false로 resolve
      document.getElementById('confirm-modal-cancel').addEventListener('click', function () {
        overlay.remove();
        resolve(false);
      });
      // 오버레이 바깥 클릭 → 취소 처리
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) { overlay.remove(); resolve(false); }
      });
    });
  }
  App.showConfirmModal = showConfirmModal;

  // =====================================================================
  // 메모 모달
  // =====================================================================
  /**
   * 블록의 메모를 편집하는 모달을 표시한다.
   * 저장 시 서버에 메모를 업데이트하고 페이지를 새로고침한다.
   * @param {string} blockId - 대상 블록 ID
   * @param {string} currentMemo - 현재 메모 내용
   */
  function openMemoModal(blockId, currentMemo) {
    // 기존 메모 모달 제거
    var existing = document.getElementById('memo-modal-backdrop');
    if (existing) existing.remove();

    // 백드롭 및 모달 생성
    var backdrop = document.createElement('div');
    backdrop.id = 'memo-modal-backdrop';
    backdrop.className = 'memo-modal-backdrop';
    backdrop.innerHTML =
      '<div class="memo-modal">' +
        '<div class="memo-modal-header">메모</div>' +
        '<textarea class="memo-modal-input" id="memo-textarea" rows="4" placeholder="메모를 입력하세요...">' +
          (currentMemo || '').replace(/</g, '&lt;') + // XSS 방지를 위한 HTML 이스케이프
        '</textarea>' +
        '<div class="memo-modal-actions">' +
          '<button class="btn btn-sm btn-secondary" id="memo-cancel">취소</button>' +
          '<button class="btn btn-sm btn-primary" id="memo-save">저장</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(backdrop);

    // 텍스트 영역에 포커스
    var textarea = document.getElementById('memo-textarea');
    textarea.focus();

    // 취소 버튼 / 백드롭 클릭 시 닫기
    document.getElementById('memo-cancel').onclick = function () { backdrop.remove(); };
    backdrop.addEventListener('click', function (ev) {
      if (ev.target === backdrop) backdrop.remove();
    });
    // 저장 버튼 — 서버에 메모 업데이트
    document.getElementById('memo-save').onclick = function () {
      var memo = textarea.value.trim();
      api('PUT', '/schedule/api/blocks/' + blockId + '/memo', { memo: memo })
        .then(function () {
          backdrop.remove();
          location.reload();
        })
        .catch(function (err) {
          showToast(err.message, 'danger');
        });
    };
  }
  App.openMemoModal = openMemoModal;

})(window.ScheduleApp);
