/**
 * Drag-and-drop (block move + queue-to-schedule) + block resize.
 * Uses native HTML5 drag-and-drop with 15-minute grid snap.
 */
(function () {
  'use strict';

  var GRID_MINUTES = 15;
  var SLOT_HEIGHT = 24;

  // -----------------------------------------------------------------------
  // Toast helper
  // -----------------------------------------------------------------------
  function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'position-fixed bottom-0 end-0 p-3';
      container.style.zIndex = '1100';
      document.body.appendChild(container);
    }
    var toast = document.createElement('div');
    toast.className = 'toast align-items-center text-bg-' + type + ' border-0 show';
    toast.setAttribute('role', 'alert');
    toast.innerHTML =
      '<div class="d-flex"><div class="toast-body">' + message +
      '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    container.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 4000);
  }

  // -----------------------------------------------------------------------
  // API helper
  // -----------------------------------------------------------------------
  function api(method, url, data) {
    var opts = {
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
  // Time helpers
  // -----------------------------------------------------------------------
  function snapTime(timeStr) {
    var parts = timeStr.split(':');
    var h = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    m = Math.round(m / GRID_MINUTES) * GRID_MINUTES;
    if (m >= 60) { h += 1; m = 0; }
    return pad(h) + ':' + pad(m);
  }

  function addMinutes(timeStr, mins) {
    var parts = timeStr.split(':');
    var total = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) + mins;
    var h = Math.floor(total / 60);
    var m = total % 60;
    return pad(h) + ':' + pad(m);
  }

  function timeToMinutes(timeStr) {
    var parts = timeStr.split(':');
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
  }

  function minutesToTime(mins) {
    var h = Math.floor(mins / 60);
    var m = mins % 60;
    return pad(h) + ':' + pad(m);
  }

  function pad(n) {
    return String(n).padStart(2, '0');
  }

  // -----------------------------------------------------------------------
  // Drag state
  // -----------------------------------------------------------------------
  var dragData = null;

  // -----------------------------------------------------------------------
  // 1. Existing block drag (move)
  // -----------------------------------------------------------------------
  function initBlockDrag() {
    document.querySelectorAll('.schedule-block[data-block-id]').forEach(function (el) {
      el.addEventListener('dragstart', function (e) {
        // Don't drag if resizing
        if (el.classList.contains('resizing')) {
          e.preventDefault();
          return;
        }
        var heightPx = el.offsetHeight;
        dragData = {
          type: 'block-move',
          blockId: el.dataset.blockId,
          el: el,
          durationMinutes: Math.round(heightPx / SLOT_HEIGHT) * GRID_MINUTES,
        };
        el.style.opacity = '0.5';
        // Disable pointer-events on ALL schedule blocks so time-slots
        // in other day columns can receive dragover/drop events
        document.querySelectorAll('.schedule-block').forEach(function (b) {
          b.style.pointerEvents = 'none';
        });
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', 'block:' + el.dataset.blockId);
      });
      el.addEventListener('dragend', function () {
        el.style.opacity = '1';
        // Restore pointer-events on all schedule blocks
        document.querySelectorAll('.schedule-block').forEach(function (b) {
          b.style.pointerEvents = '';
        });
        clearDragOver();
        dragData = null;
      });
    });
  }

  // -----------------------------------------------------------------------
  // 2. Queue task drag (new block creation)
  // -----------------------------------------------------------------------
  function initQueueDrag() {
    document.querySelectorAll('.queue-task-item[data-task-id]').forEach(function (el) {
      el.addEventListener('dragstart', function (e) {
        dragData = {
          type: 'queue-task',
          taskId: el.dataset.taskId,
          assigneeId: el.dataset.assigneeId || '',
          remainingHours: parseFloat(el.dataset.remainingHours) || 1,
          el: el,
        };
        el.classList.add('dragging');
        // Disable pointer-events on all schedule blocks so time-slots
        // in week view columns can receive dragover/drop events
        document.querySelectorAll('.schedule-block').forEach(function (b) {
          b.style.pointerEvents = 'none';
        });
        e.dataTransfer.effectAllowed = 'copy';
        e.dataTransfer.setData('text/plain', 'task:' + el.dataset.taskId);
      });
      el.addEventListener('dragend', function () {
        el.classList.remove('dragging');
        // Restore pointer-events on all schedule blocks
        document.querySelectorAll('.schedule-block').forEach(function (b) {
          b.style.pointerEvents = '';
        });
        clearDragOver();
        dragData = null;
      });
    });
  }

  // -----------------------------------------------------------------------
  // 3. Droppable time slots (day/week views)
  // -----------------------------------------------------------------------
  function initTimeSlotDrop() {
    document.querySelectorAll('.time-slot').forEach(function (el) {
      el.addEventListener('dragover', onDragOver);
      el.addEventListener('dragleave', onDragLeave);
      el.addEventListener('drop', onTimeSlotDrop);
    });
  }

  function onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = dragData && dragData.type === 'queue-task' ? 'copy' : 'move';
    e.currentTarget.classList.add('drag-over');
  }

  function onDragLeave(e) {
    e.currentTarget.classList.remove('drag-over');
  }

  function onTimeSlotDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');
    if (!dragData) return;

    var slot = e.currentTarget;
    var newDate = slot.dataset.date;
    var newTime = snapTime(slot.dataset.time);

    if (dragData.type === 'block-move') {
      // Move existing block
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
      });

    } else if (dragData.type === 'queue-task') {
      // Create new block sized to remaining_hours (capped at 4h to avoid overflow)
      var blockMinutes = Math.min(dragData.remainingHours * 60, 240);
      blockMinutes = Math.max(blockMinutes, GRID_MINUTES); // at least 1 slot
      // Snap to grid
      blockMinutes = Math.round(blockMinutes / GRID_MINUTES) * GRID_MINUTES;
      var newEnd = addMinutes(newTime, blockMinutes);

      api('POST', '/schedule/api/blocks', {
        task_id: dragData.taskId,
        assignee_id: dragData.assigneeId,
        date: newDate,
        start_time: newTime,
        end_time: newEnd,
        origin: 'manual',
      }).then(function () {
        location.reload();
      }).catch(function (err) {
        showToast(err.message, 'danger');
      });
    }
  }

  // -----------------------------------------------------------------------
  // 4. Droppable month day cells
  // -----------------------------------------------------------------------
  function initMonthDrop() {
    document.querySelectorAll('.month-day-cell[data-date]').forEach(function (el) {
      el.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        el.classList.add('drag-over');
      });
      el.addEventListener('dragleave', function () {
        el.classList.remove('drag-over');
      });
      el.addEventListener('drop', function (e) {
        e.preventDefault();
        el.classList.remove('drag-over');
        if (!dragData || dragData.type !== 'queue-task') return;

        // Create block at work_start (09:00) for 1 hour
        var cellDate = el.dataset.date;
        api('POST', '/schedule/api/blocks', {
          task_id: dragData.taskId,
          assignee_id: dragData.assigneeId,
          date: cellDate,
          start_time: '09:00',
          end_time: '10:00',
          origin: 'manual',
        }).then(function () {
          location.reload();
        }).catch(function (err) {
          showToast(err.message, 'danger');
        });
      });
    });
  }

  function clearDragOver() {
    document.querySelectorAll('.drag-over').forEach(function (el) {
      el.classList.remove('drag-over');
    });
  }

  // -----------------------------------------------------------------------
  // 5. Block resize (top/bottom handles)
  // -----------------------------------------------------------------------
  function initResize() {
    var resizeState = null;

    document.querySelectorAll('.resize-handle').forEach(function (handle) {
      handle.addEventListener('mousedown', function (e) {
        e.preventDefault();
        e.stopPropagation();

        var block = handle.closest('.schedule-block');
        if (!block) return;

        var isTop = handle.classList.contains('resize-handle-top');
        var startY = e.clientY;
        var origTop = parseInt(block.style.top, 10);
        var origHeight = parseInt(block.style.height, 10);

        block.classList.add('resizing');
        block.setAttribute('draggable', 'false');

        resizeState = {
          block: block,
          blockId: block.dataset.blockId,
          isTop: isTop,
          startY: startY,
          origTop: origTop,
          origHeight: origHeight,
        };

        function onMouseMove(ev) {
          if (!resizeState) return;
          var delta = ev.clientY - resizeState.startY;
          // Snap delta to slot increments
          var snappedDelta = Math.round(delta / SLOT_HEIGHT) * SLOT_HEIGHT;

          if (resizeState.isTop) {
            var newTop = resizeState.origTop + snappedDelta;
            var newHeight = resizeState.origHeight - snappedDelta;
            if (newHeight >= SLOT_HEIGHT && newTop >= 0) {
              resizeState.block.style.top = newTop + 'px';
              resizeState.block.style.height = newHeight + 'px';
            }
          } else {
            var newHeight = resizeState.origHeight + snappedDelta;
            if (newHeight >= SLOT_HEIGHT) {
              resizeState.block.style.height = newHeight + 'px';
            }
          }
        }

        function onMouseUp() {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
          if (!resizeState) return;

          var block = resizeState.block;
          block.classList.remove('resizing');
          block.setAttribute('draggable', 'true');

          var finalTop = parseInt(block.style.top, 10);
          var finalHeight = parseInt(block.style.height, 10);

          // Calculate new times from pixel positions
          // Find the work_start from the first time-gutter-label or time-slot
          var firstSlot = document.querySelector('.time-slot[data-time]');
          var workStartMinutes = firstSlot ? timeToMinutes(firstSlot.dataset.time) : 540;

          var newStartMinutes = workStartMinutes + Math.round(finalTop / SLOT_HEIGHT) * GRID_MINUTES;
          var durationMinutes = Math.round(finalHeight / SLOT_HEIGHT) * GRID_MINUTES;
          var newEndMinutes = newStartMinutes + durationMinutes;

          var newStart = minutesToTime(newStartMinutes);
          var newEnd = minutesToTime(newEndMinutes);

          // Only update if actually changed
          if (newStart !== block.dataset.startTime || newEnd !== block.dataset.endTime) {
            api('PUT', '/schedule/api/blocks/' + resizeState.blockId, {
              start_time: newStart,
              end_time: newEnd,
            }).then(function () {
              location.reload();
            }).catch(function (err) {
              showToast(err.message, 'danger');
              // Rollback
              block.style.top = resizeState.origTop + 'px';
              block.style.height = resizeState.origHeight + 'px';
            });
          }

          resizeState = null;
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    });
  }

  // -----------------------------------------------------------------------
  // 6. Block context menu (right-click: lock toggle, delete)
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
    var old = document.getElementById('block-context-menu');
    if (old) old.remove();

    var menu = document.createElement('div');
    menu.id = 'block-context-menu';
    menu.className = 'dropdown-menu show';
    menu.style.cssText = 'position:fixed;z-index:1200;left:' + e.clientX + 'px;top:' + e.clientY + 'px;';
    menu.innerHTML =
      '<button class="dropdown-item" data-action="lock"><i class="bi bi-lock"></i> 잠금 토글</button>' +
      '<button class="dropdown-item text-danger" data-action="delete"><i class="bi bi-trash"></i> 삭제</button>';
    document.body.appendChild(menu);

    menu.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-action]');
      if (!btn) return;
      var action = btn.dataset.action;
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

    setTimeout(function () {
      document.addEventListener('click', function handler() {
        menu.remove();
        document.removeEventListener('click', handler);
      }, { once: true });
    }, 0);
  }

  // -----------------------------------------------------------------------
  // 7. Draft scheduling controls
  // -----------------------------------------------------------------------
  function initDraftControls() {
    var toolbar = document.querySelector('.schedule-nav');
    if (!toolbar) return;

    var group = document.createElement('div');
    group.className = 'ms-auto d-flex gap-1';
    group.innerHTML =
      '<button class="btn btn-sm btn-outline-success" id="btn-generate">자동 스케줄링</button>' +
      '<button class="btn btn-sm btn-success" id="btn-approve" style="display:none">초안 확정</button>' +
      '<button class="btn btn-sm btn-outline-danger" id="btn-discard" style="display:none">초안 폐기</button>';
    toolbar.appendChild(group);

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
  // 8. Queue toggle
  // -----------------------------------------------------------------------
  function initQueueToggle() {
    var btn = document.getElementById('toggle-queue');
    var queue = document.getElementById('task-queue');
    if (!btn || !queue) return;

    btn.addEventListener('click', function () {
      queue.classList.toggle('collapsed');
    });
  }

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', function () {
    initBlockDrag();
    initQueueDrag();
    initTimeSlotDrop();
    initMonthDrop();
    initResize();
    initBlockActions();
    initDraftControls();
    initQueueToggle();
  });
})();
