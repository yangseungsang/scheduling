/**
 * Drag-and-drop + scheduling controls for the calendar views.
 * Uses native HTML5 drag-and-drop with 15-minute grid snap.
 */
(function () {
  'use strict';

  const GRID_MINUTES = 15;
  const SLOT_HEIGHT = 48; // px per grid interval — must match CSS

  // -----------------------------------------------------------------------
  // Toast helper
  // -----------------------------------------------------------------------
  function showToast(message, type) {
    type = type || 'info';
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'position-fixed bottom-0 end-0 p-3';
      container.style.zIndex = '1100';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'toast align-items-center text-bg-' + type + ' border-0 show';
    toast.setAttribute('role', 'alert');
    toast.innerHTML =
      '<div class="d-flex"><div class="toast-body">' + message +
      '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    container.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 4000);
  }

  // -----------------------------------------------------------------------
  // API helpers
  // -----------------------------------------------------------------------
  function api(method, url, data) {
    const opts = {
      method: method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (data) opts.body = JSON.stringify(data);
    return fetch(url, opts).then(function (res) {
      return res.json().then(function (json) {
        if (!res.ok) throw new Error(json.error || '오류가 발생했습니다.');
        return json;
      });
    });
  }

  // -----------------------------------------------------------------------
  // Snap helper — round minutes to nearest grid interval
  // -----------------------------------------------------------------------
  function snapTime(timeStr) {
    var parts = timeStr.split(':');
    var h = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    m = Math.round(m / GRID_MINUTES) * GRID_MINUTES;
    if (m >= 60) { h += 1; m = 0; }
    return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
  }

  // -----------------------------------------------------------------------
  // Calculate end time from start time + duration in minutes
  // -----------------------------------------------------------------------
  function addMinutes(timeStr, mins) {
    var parts = timeStr.split(':');
    var total = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) + mins;
    var h = Math.floor(total / 60);
    var m = total % 60;
    return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
  }

  function timeDiffMinutes(start, end) {
    var s = start.split(':'), e = end.split(':');
    return (parseInt(e[0], 10) * 60 + parseInt(e[1], 10)) -
           (parseInt(s[0], 10) * 60 + parseInt(s[1], 10));
  }

  // -----------------------------------------------------------------------
  // Drag and Drop
  // -----------------------------------------------------------------------
  var dragData = null;

  function initDragDrop() {
    // Make blocks draggable
    document.querySelectorAll('.schedule-block[data-block-id]').forEach(function (el) {
      el.addEventListener('dragstart', onDragStart);
      el.addEventListener('dragend', onDragEnd);
    });

    // Make time slots droppable
    document.querySelectorAll('.time-slot').forEach(function (el) {
      el.addEventListener('dragover', onDragOver);
      el.addEventListener('dragleave', onDragLeave);
      el.addEventListener('drop', onDrop);
    });
  }

  function onDragStart(e) {
    var el = e.target.closest('.schedule-block');
    if (!el) return;
    dragData = {
      blockId: el.dataset.blockId,
      el: el,
      startTime: el.dataset.startTime || '',
      endTime: el.dataset.endTime || '',
    };
    // Calculate duration from pixel height
    var heightPx = el.offsetHeight;
    dragData.durationMinutes = Math.round(heightPx / SLOT_HEIGHT) * GRID_MINUTES;

    el.style.opacity = '0.5';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', el.dataset.blockId);
  }

  function onDragEnd(e) {
    if (dragData && dragData.el) {
      dragData.el.style.opacity = '1';
    }
    document.querySelectorAll('.time-slot.drag-over').forEach(function (el) {
      el.classList.remove('drag-over');
    });
    dragData = null;
  }

  function onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    e.currentTarget.classList.add('drag-over');
  }

  function onDragLeave(e) {
    e.currentTarget.classList.remove('drag-over');
  }

  function onDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');
    if (!dragData) return;

    var slot = e.currentTarget;
    var newDate = slot.dataset.date;
    var newTime = snapTime(slot.dataset.time);
    var duration = dragData.durationMinutes || GRID_MINUTES;
    var newEnd = addMinutes(newTime, duration);

    api('PUT', '/schedule/api/blocks/' + dragData.blockId, {
      date: newDate,
      start_time: newTime,
      end_time: newEnd,
    }).then(function () {
      location.reload();
    }).catch(function (err) {
      showToast(err.message, 'danger');
      // Rollback — just reload
      location.reload();
    });
  }

  // -----------------------------------------------------------------------
  // Block context actions (lock toggle, delete)
  // -----------------------------------------------------------------------
  function initBlockActions() {
    document.addEventListener('contextmenu', function (e) {
      var block = e.target.closest('.schedule-block[data-block-id]');
      if (!block) return;
      e.preventDefault();
      showBlockMenu(e, block.dataset.blockId);
    });
  }

  function showBlockMenu(e, blockId) {
    // Remove any existing menu
    var old = document.getElementById('block-context-menu');
    if (old) old.remove();

    var menu = document.createElement('div');
    menu.id = 'block-context-menu';
    menu.className = 'dropdown-menu show';
    menu.style.cssText = 'position:fixed;z-index:1200;left:' + e.clientX + 'px;top:' + e.clientY + 'px;';
    menu.innerHTML =
      '<button class="dropdown-item" data-action="lock">잠금 토글</button>' +
      '<button class="dropdown-item text-danger" data-action="delete">삭제</button>';
    document.body.appendChild(menu);

    menu.addEventListener('click', function (ev) {
      var action = ev.target.dataset.action;
      menu.remove();
      if (action === 'lock') {
        api('PUT', '/schedule/api/blocks/' + blockId + '/lock').then(function () {
          location.reload();
        }).catch(function (err) { showToast(err.message, 'danger'); });
      } else if (action === 'delete') {
        if (confirm('이 블록을 삭제하시겠습니까?')) {
          api('DELETE', '/schedule/api/blocks/' + blockId).then(function () {
            location.reload();
          }).catch(function (err) { showToast(err.message, 'danger'); });
        }
      }
    });

    // Close on click outside
    setTimeout(function () {
      document.addEventListener('click', function handler() {
        menu.remove();
        document.removeEventListener('click', handler);
      }, { once: true });
    }, 0);
  }

  // -----------------------------------------------------------------------
  // Draft scheduling controls
  // -----------------------------------------------------------------------
  function initDraftControls() {
    var toolbar = document.querySelector('.day-nav, .week-nav');
    if (!toolbar) return;

    var group = document.createElement('div');
    group.className = 'ms-auto d-flex gap-1';
    group.innerHTML =
      '<button class="btn btn-sm btn-outline-success" id="btn-generate">자동 스케줄링</button>' +
      '<button class="btn btn-sm btn-success" id="btn-approve" style="display:none">초안 확정</button>' +
      '<button class="btn btn-sm btn-outline-danger" id="btn-discard" style="display:none">초안 폐기</button>';
    toolbar.appendChild(group);

    // Show approve/discard if drafts exist
    if (document.querySelector('.schedule-block.draft')) {
      document.getElementById('btn-approve').style.display = '';
      document.getElementById('btn-discard').style.display = '';
    }

    document.getElementById('btn-generate').addEventListener('click', function () {
      api('POST', '/schedule/api/draft/generate').then(function (res) {
        var msg = res.placed_count + '개 블록이 배치되었습니다.';
        if (res.unplaced && res.unplaced.length > 0) {
          msg += ' (미배치 ' + res.unplaced.length + '개)';
        }
        showToast(msg, 'success');
        setTimeout(function () { location.reload(); }, 500);
      }).catch(function (err) { showToast(err.message, 'danger'); });
    });

    document.getElementById('btn-approve').addEventListener('click', function () {
      api('POST', '/schedule/api/draft/approve').then(function () {
        showToast('초안이 확정되었습니다.', 'success');
        setTimeout(function () { location.reload(); }, 500);
      }).catch(function (err) { showToast(err.message, 'danger'); });
    });

    document.getElementById('btn-discard').addEventListener('click', function () {
      if (!confirm('초안을 모두 폐기하시겠습니까?')) return;
      api('POST', '/schedule/api/draft/discard').then(function () {
        showToast('초안이 폐기되었습니다.', 'info');
        setTimeout(function () { location.reload(); }, 500);
      }).catch(function (err) { showToast(err.message, 'danger'); });
    });
  }

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', function () {
    initDragDrop();
    initBlockActions();
    initDraftControls();
  });
})();
