/**
 * Context menu for schedule blocks (right-click).
 * Extracted from drag_drop.js
 */
(function () {
  'use strict';

  var App = window.ScheduleApp || {};

  var showToast = App.showToast;
  var api = App.api;
  var isReadonly = App.isReadonly;
  var showConfirmModal = App.showConfirmModal;
  var openMemoModal = App.openMemoModal;

  // =====================================================================
  // Context menu
  // =====================================================================
  function initContextMenu() {
    document.addEventListener('contextmenu', function (e) {
      if (isReadonly()) return;
      var block = e.target.closest('.schedule-block[data-block-id]');
      if (!block) return;
      e.preventDefault();
      var old = document.getElementById('block-context-menu');
      if (old) old.remove();

      var blockId = block.dataset.blockId;
      var currentStatus = block.dataset.blockStatus || 'pending';
      var menu = document.createElement('div');
      menu.id = 'block-context-menu';
      menu.className = 'dropdown-menu show';
      menu.style.cssText = 'position:fixed;z-index:1200;left:' + e.clientX + 'px;top:' + e.clientY + 'px;';

      var statusItems = [
        { value: 'pending', label: '시작 전', icon: 'bi-hourglass' },
        { value: 'in_progress', label: '진행 중', icon: 'bi-play-circle' },
        { value: 'completed', label: '완료', icon: 'bi-check-circle' },
        { value: 'cancelled', label: '불가', icon: 'bi-x-circle' },
      ];
      var statusHtml = '<div class="dropdown-header" style="font-size:0.75rem;padding:4px 12px;">상태 변경</div>';
      statusItems.forEach(function (s) {
        var active = s.value === currentStatus ? ' active' : '';
        statusHtml += '<button class="dropdown-item' + active + '" data-action="status" data-status="' + s.value + '">' +
          '<i class="bi ' + s.icon + '"></i> ' + s.label + '</button>';
      });

      menu.innerHTML =
        statusHtml +
        '<div class="dropdown-divider"></div>' +
        '<button class="dropdown-item" data-action="memo"><i class="bi bi-sticky"></i> 메모</button>' +
        '<button class="dropdown-item" data-action="split"><i class="bi bi-scissors"></i> 분리</button>' +
        '<button class="dropdown-item" data-action="to-queue"><i class="bi bi-arrow-left-square"></i> 큐로 보내기</button>' +
        '<button class="dropdown-item" data-action="lock"><i class="bi bi-lock"></i> 잠금 토글</button>' +
        '<button class="dropdown-item text-danger" data-action="delete"><i class="bi bi-trash"></i> 삭제</button>';
      document.body.appendChild(menu);

      menu.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-action]');
        if (!btn) return;
        menu.remove();
        if (btn.dataset.action === 'memo') {
          openMemoModal(blockId, block.dataset.memo || '');
        } else if (btn.dataset.action === 'status') {
          api('PUT', '/schedule/api/blocks/' + blockId + '/status', { block_status: btn.dataset.status })
            .then(function () { location.reload(); })
            .catch(function (err) { showToast(err.message, 'danger'); });
        } else if (btn.dataset.action === 'to-queue') {
          api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
            .then(function () {
              showToast('큐로 되돌렸습니다.', 'success');
              location.reload();
            })
            .catch(function (err) { showToast(err.message, 'danger'); });
        } else if (btn.dataset.action === 'split') {
          var taskId = block.dataset.taskId;
          if (!taskId) { showToast('분리할 수 없는 블록입니다.', 'danger'); return; }
          api('GET', '/tasks/api/' + taskId).then(function (res) {
            var tsk = res.task;
            if (!tsk || !tsk.test_list || tsk.test_list.length < 2) {
              showToast('식별자가 2개 이상이어야 분리할 수 있습니다.', 'danger');
              return;
            }
            // Figure out which identifiers this block currently covers
            var blockIdIds = null;
            try { if (block.dataset.identifierIds) blockIdIds = JSON.parse(block.dataset.identifierIds); } catch(ex) {}
            var currentIds = blockIdIds || tsk.test_list.map(function(it) { return typeof it === 'object' ? it.id : it; });

            // Filter test_list to only this block's identifiers
            var blockTestList = tsk.test_list.filter(function(it) {
              var iid = typeof it === 'object' ? it.id : it;
              return currentIds.indexOf(iid) !== -1;
            });
            if (blockTestList.length < 2) {
              showToast('이 블록의 식별자가 2개 이상이어야 분리할 수 있습니다.', 'danger');
              return;
            }

            // Show picker: checked = keep in this block, unchecked = send to queue
            App.showSplitPicker(blockTestList, function (keepItems) {
              if (!keepItems || keepItems.length === 0 || keepItems.length === blockTestList.length) return;
              var keepIds = keepItems.map(function (s) { return typeof s === 'object' ? s.id : s; });
              api('POST', '/schedule/api/blocks/' + blockId + '/split', {
                keep_identifier_ids: keepIds
              }).then(function () {
                showToast('블록이 분리되었습니다.', 'success');
                setTimeout(function () { location.reload(); }, 300);
              }).catch(function (err) { showToast(err.message, 'danger'); });
            });
          });
        } else if (btn.dataset.action === 'lock') {
          api('PUT', '/schedule/api/blocks/' + blockId + '/lock')
            .then(function () { location.reload(); })
            .catch(function (err) { showToast(err.message, 'danger'); });
        } else if (btn.dataset.action === 'delete') {
          showConfirmModal('이 블록을 삭제하시겠습니까?', {
            title: '블록 삭제', icon: 'trash', okText: '삭제', cancelText: '취소'
          }).then(function (ok) {
            if (ok) {
              api('DELETE', '/schedule/api/blocks/' + blockId)
                .then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            }
          });
        }
      });
      setTimeout(function () {
        document.addEventListener('click', function h() {
          menu.remove(); document.removeEventListener('click', h);
        }, { once: true });
      }, 0);
    });
  }

  // =====================================================================
  // Split picker — check = keep in block, uncheck = send to queue
  // =====================================================================
  function showSplitPicker(testList, callback) {
    var old = document.getElementById('identifier-picker');
    if (old) old.remove();

    var overlay = document.createElement('div');
    overlay.id = 'identifier-picker';
    overlay.className = 'block-detail-overlay';
    var rows = '';
    testList.forEach(function (item, i) {
      var id = typeof item === 'object' ? item.id : item;
      var owners = (typeof item === 'object' && item.owners) ? item.owners : [];
      var mins = typeof item === 'object' ? Math.round((item.estimated_hours || 0) * 60) : 0;
      var ownerStr = owners.length ? ' <span class="text-muted">작성: ' + owners.join(', ') + '</span>' : '';
      rows += '<label class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem">' +
        '<input type="checkbox" class="form-check-input" value="' + i + '" checked> ' +
        '<span>' + id + '</span>' + ownerStr +
        (mins > 0 ? ' <span class="text-muted">(' + mins + '분)</span>' : '') +
        '</label>';
    });
    overlay.innerHTML =
      '<div class="bd-box" style="max-width:380px">' +
        '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">블록 분리</span></div>' +
          '<button class="bd-x" id="picker-close">&times;</button></div>' +
        '<div class="bd-divider"></div>' +
        '<div style="padding:12px">' +
          '<div class="form-text mb-2"><strong>체크 유지</strong> = 이 블록에 남김<br><strong>체크 해제</strong> = 큐로 보냄</div>' +
          '<div id="picker-list">' + rows + '</div>' +
          '<button class="btn btn-sm btn-primary w-100 mt-2" id="picker-ok">분리</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (ev) { if (ev.target === overlay) { overlay.remove(); callback(null); } });
    document.getElementById('picker-close').addEventListener('click', function () { overlay.remove(); callback(null); });
    document.getElementById('picker-ok').addEventListener('click', function () {
      var checked = [];
      overlay.querySelectorAll('#picker-list input:checked').forEach(function (cb) {
        checked.push(parseInt(cb.value));
      });
      overlay.remove();
      if (checked.length === 0) { showToast('최소 1개는 남겨야 합니다.', 'danger'); callback(null); return; }
      if (checked.length === testList.length) { showToast('전체를 남기면 분리되지 않습니다.', 'info'); callback(null); return; }
      var selected = checked.map(function (i) { return testList[i]; });
      callback(selected);
    });
  }

  // Register on App namespace
  App.initContextMenu = initContextMenu;
  App.showSplitPicker = showSplitPicker;
  window.ScheduleApp = App;
})();
