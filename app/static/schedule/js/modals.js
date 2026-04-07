/**
 * Modal dialogs: confirm modal & memo modal.
 * Registered on window.ScheduleApp namespace.
 */
window.ScheduleApp = window.ScheduleApp || {};
(function (App) {
  'use strict';

  var api = App.api;
  var showToast = App.showToast;

  // =====================================================================
  // Custom confirm modal (replaces browser confirm)
  // =====================================================================
  function showConfirmModal(message, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      var old = document.getElementById('confirm-modal');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'confirm-modal';
      overlay.className = 'remaining-alert-overlay';
      overlay.innerHTML =
        '<div class="remaining-alert-box">' +
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

      document.getElementById('confirm-modal-ok').addEventListener('click', function () {
        overlay.remove();
        resolve(true);
      });
      document.getElementById('confirm-modal-cancel').addEventListener('click', function () {
        overlay.remove();
        resolve(false);
      });
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) { overlay.remove(); resolve(false); }
      });
    });
  }
  App.showConfirmModal = showConfirmModal;

  // =====================================================================
  // Memo modal
  // =====================================================================
  function openMemoModal(blockId, currentMemo) {
    var existing = document.getElementById('memo-modal-backdrop');
    if (existing) existing.remove();

    var backdrop = document.createElement('div');
    backdrop.id = 'memo-modal-backdrop';
    backdrop.className = 'memo-modal-backdrop';
    backdrop.innerHTML =
      '<div class="memo-modal">' +
        '<div class="memo-modal-header">메모</div>' +
        '<textarea class="memo-modal-input" id="memo-textarea" rows="4" placeholder="메모를 입력하세요...">' +
          (currentMemo || '').replace(/</g, '&lt;') +
        '</textarea>' +
        '<div class="memo-modal-actions">' +
          '<button class="btn btn-sm btn-secondary" id="memo-cancel">취소</button>' +
          '<button class="btn btn-sm btn-primary" id="memo-save">저장</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(backdrop);

    var textarea = document.getElementById('memo-textarea');
    textarea.focus();

    document.getElementById('memo-cancel').onclick = function () { backdrop.remove(); };
    backdrop.addEventListener('click', function (ev) {
      if (ev.target === backdrop) backdrop.remove();
    });
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
