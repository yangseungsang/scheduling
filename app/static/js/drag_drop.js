/**
 * Calendar drag-drop & resize — mouse-event based.
 */
(function () {
  'use strict';

  var GRID_MINUTES = 15;
  var SLOT_HEIGHT = 24;

  // =====================================================================
  // Toast
  // =====================================================================
  function showToast(msg, type) {
    var c = document.getElementById('toast-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-container';
      c.className = 'position-fixed bottom-0 end-0 p-3';
      c.style.zIndex = '1100';
      document.body.appendChild(c);
    }
    var t = document.createElement('div');
    t.className = 'toast align-items-center text-bg-' + (type || 'info') + ' border-0 show';
    t.innerHTML = '<div class="d-flex"><div class="toast-body">' + msg +
      '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    c.appendChild(t);
    setTimeout(function () { t.remove(); }, 4000);
  }

  // =====================================================================
  // API
  // =====================================================================
  function api(method, url, data) {
    return fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error(j.error || '오류가 발생했습니다.');
        return j;
      });
    });
  }

  // =====================================================================
  // Time helpers
  // =====================================================================
  function pad(n) { return String(n).padStart(2, '0'); }
  function timeToMin(t) { var p = t.split(':'); return +p[0] * 60 + +p[1]; }
  function minToTime(m) { return pad(Math.floor(m / 60)) + ':' + pad(m % 60); }
  function snapMin(m) { return Math.round(m / GRID_MINUTES) * GRID_MINUTES; }

  // =====================================================================
  // Block visibility toggle — hide all blocks so elementFromPoint hits time-slots
  // =====================================================================
  function hideAllBlocks() {
    document.querySelectorAll('.schedule-block, .month-block-item').forEach(function (b) {
      b.style.pointerEvents = 'none';
    });
  }
  function showAllBlocks() {
    document.querySelectorAll('.schedule-block, .month-block-item').forEach(function (b) {
      b.style.pointerEvents = '';
    });
  }

  // =====================================================================
  // Find target under cursor
  // =====================================================================
  function findTarget(x, y) {
    var el = document.elementFromPoint(x, y);
    if (!el) return null;
    var slot = el.closest('.time-slot');
    if (slot && slot.dataset.date && slot.dataset.time) {
      return { type: 'slot', date: slot.dataset.date, time: slot.dataset.time, el: slot };
    }
    var cell = el.closest('.month-day-cell[data-date]');
    if (cell) {
      return { type: 'month', date: cell.dataset.date, el: cell };
    }
    var queue = el.closest('#task-queue');
    if (queue) {
      return { type: 'queue', el: queue };
    }
    return null;
  }

  // =====================================================================
  // Ghost element
  // =====================================================================
  function createGhost(text, color, w) {
    var g = document.createElement('div');
    g.textContent = text;
    g.style.cssText =
      'position:fixed;z-index:9999;pointer-events:none;opacity:0.85;' +
      'padding:4px 8px;border-radius:4px;font-size:0.75rem;color:#fff;' +
      'white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.3);' +
      'background:' + (color || '#0d6efd') + ';width:' + (w || 120) + 'px;';
    document.body.appendChild(g);
    return g;
  }

  // =====================================================================
  // Highlight
  // =====================================================================
  var highlighted = null;
  function setHighlight(target) {
    clearHighlight();
    if (target && target.el) {
      target.el.classList.add('drag-over');
      highlighted = target.el;
    }
  }
  function clearHighlight() {
    if (highlighted) highlighted.classList.remove('drag-over');
    highlighted = null;
  }

  // =====================================================================
  // Generic drag helper
  // =====================================================================
  function startDrag(e, opts) {
    if (e.button !== 0) return;
    if (isReadonly()) return;
    e.preventDefault();

    var startX = e.clientX, startY = e.clientY;
    var dragging = false;
    var ghost = null;

    function onMove(ev) {
      ev.preventDefault();
      var dx = ev.clientX - startX, dy = ev.clientY - startY;
      if (!dragging && Math.abs(dx) + Math.abs(dy) < 5) return;

      if (!dragging) {
        dragging = true;
        ghost = createGhost(opts.ghostText, opts.ghostColor, opts.ghostWidth);
        hideAllBlocks();
        if (opts.sourceEl) opts.sourceEl.style.opacity = '0.3';
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'grabbing';
      }

      ghost.style.left = ev.clientX + 12 + 'px';
      ghost.style.top = ev.clientY + 12 + 'px';

      var target = findTarget(ev.clientX, ev.clientY);
      setHighlight(target);
    }

    function onUp(ev) {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);

      var target = null;
      if (dragging) {
        target = findTarget(ev.clientX, ev.clientY);
      }

      clearHighlight();
      showAllBlocks();
      if (ghost) ghost.remove();
      if (opts.sourceEl) opts.sourceEl.style.opacity = '';
      document.body.style.userSelect = '';
      document.body.style.cursor = '';

      if (!dragging) return;

      if (target) opts.onDrop(target);
    }

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  // =====================================================================
  // 1. Block move
  // =====================================================================
  function initBlockMove() {
    document.querySelectorAll('.schedule-block[data-block-id]').forEach(function (block) {
      block.addEventListener('mousedown', function (e) {
        if (e.target.closest('.resize-handle')) return;

        var blockId = block.dataset.blockId;
        var title = (block.querySelector('.block-title') || {}).textContent || '';
        var color = block.style.backgroundColor || '#0d6efd';
        var startTime = block.dataset.startTime;
        var endTime = block.dataset.endTime;
        var durationMin = timeToMin(endTime) - timeToMin(startTime);

        startDrag(e, {
          sourceEl: block,
          ghostText: title,
          ghostColor: color,
          ghostWidth: block.offsetWidth,
          onDrop: function (target) {
            if (target.type === 'queue') {
              api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
                .then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            } else if (target.type === 'slot') {
              var t = snapMin(timeToMin(target.time));
              api('PUT', '/schedule/api/blocks/' + blockId, {
                date: target.date,
                start_time: minToTime(t),
                end_time: minToTime(t + durationMin),
              }).then(function () {
                location.reload();
              }).catch(function (err) {
                showToast(err.message, 'danger');
              });
            } else if (target.type === 'month') {
              api('PUT', '/schedule/api/blocks/' + blockId, {
                date: target.date,
              }).then(function () {
                location.reload();
              }).catch(function (err) {
                showToast(err.message, 'danger');
              });
            }
          },
        });
      });
    });
  }

  // =====================================================================
  // 2. Queue drag
  // =====================================================================
  function initQueueDrag() {
    document.querySelectorAll('.queue-task-item[data-task-id]').forEach(function (item) {
      item.addEventListener('mousedown', function (e) {
        var taskId = item.dataset.taskId;
        var assigneeId = item.dataset.assigneeId || '';
        var remaining = parseFloat(item.dataset.remainingHours) || 1;
        var title = (item.querySelector('.queue-task-title') || {}).textContent || '';

        startDrag(e, {
          sourceEl: item,
          ghostText: title,
          ghostColor: '#0d6efd',
          ghostWidth: 150,
          onDrop: function (target) {
            var blockMin = Math.min(remaining * 60, 240);
            blockMin = Math.max(blockMin, GRID_MINUTES);
            blockMin = Math.round(blockMin / GRID_MINUTES) * GRID_MINUTES;

            if (target.type === 'slot') {
              var t = snapMin(timeToMin(target.time));
              api('POST', '/schedule/api/blocks', {
                task_id: taskId, assignee_id: assigneeId,
                date: target.date,
                start_time: minToTime(t),
                end_time: minToTime(t + blockMin),
                origin: 'manual',
              }).then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });

            } else if (target.type === 'month') {
              api('POST', '/schedule/api/blocks', {
                task_id: taskId, assignee_id: assigneeId,
                date: target.date,
                start_time: '09:00',
                end_time: minToTime(snapMin(blockMin) + 540),
                origin: 'manual',
              }).then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            }
          },
        });
      });
    });
  }

  // =====================================================================
  // 2b. Month block move
  // =====================================================================
  function initMonthBlockMove() {
    document.querySelectorAll('.month-block-item[data-block-id]').forEach(function (item) {
      item.addEventListener('mousedown', function (e) {
        var blockId = item.dataset.blockId;
        var title = item.textContent.trim();
        var color = item.style.backgroundColor || '#0d6efd';

        startDrag(e, {
          sourceEl: item,
          ghostText: title,
          ghostColor: color,
          ghostWidth: 120,
          onDrop: function (target) {
            if (target.type === 'queue') {
              api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
                .then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            } else if (target.type === 'month') {
              api('PUT', '/schedule/api/blocks/' + blockId, {
                date: target.date,
              }).then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            }
          },
        });
      });
    });
  }

  // =====================================================================
  // 3. Block resize
  // =====================================================================
  function initResize() {
    document.querySelectorAll('.resize-handle').forEach(function (handle) {
      handle.addEventListener('mousedown', function (e) {
        if (isReadonly()) return;
        e.preventDefault();
        e.stopPropagation();

        var block = handle.closest('.schedule-block');
        if (!block) return;

        var isTop = handle.classList.contains('resize-handle-top');
        var blockId = block.dataset.blockId;
        var origTop = parseInt(block.style.top, 10);
        var origHeight = parseInt(block.style.height, 10);
        var startY = e.clientY;

        block.classList.add('resizing');

        function onMove(ev) {
          ev.preventDefault();
          var delta = ev.clientY - startY;
          var snapped = Math.round(delta / SLOT_HEIGHT) * SLOT_HEIGHT;

          if (isTop) {
            var newTop = origTop + snapped;
            var newH = origHeight - snapped;
            if (newH >= SLOT_HEIGHT && newTop >= 0) {
              block.style.top = newTop + 'px';
              block.style.height = newH + 'px';
            }
          } else {
            var newH2 = origHeight + snapped;
            if (newH2 >= SLOT_HEIGHT) {
              block.style.height = newH2 + 'px';
            }
          }
        }

        function onUp() {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          block.classList.remove('resizing');

          var finalTop = parseInt(block.style.top, 10);
          var finalH = parseInt(block.style.height, 10);

          var firstSlot = document.querySelector('.time-slot[data-time]');
          var wsMin = firstSlot ? timeToMin(firstSlot.dataset.time) : 540;
          var newStartMin = wsMin + Math.round(finalTop / SLOT_HEIGHT) * GRID_MINUTES;
          var durMin = Math.round(finalH / SLOT_HEIGHT) * GRID_MINUTES;

          var newStart = minToTime(newStartMin);
          var newEnd = minToTime(newStartMin + durMin);

          if (newStart !== block.dataset.startTime || newEnd !== block.dataset.endTime) {
            api('PUT', '/schedule/api/blocks/' + blockId, {
              start_time: newStart,
              end_time: newEnd,
              resize: true,
            }).then(function () { location.reload(); })
              .catch(function (err) {
                showToast(err.message, 'danger');
                block.style.top = origTop + 'px';
                block.style.height = origHeight + 'px';
              });
          }
        }

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });
    });
  }

  // =====================================================================
  // 4. Context menu
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
      var menu = document.createElement('div');
      menu.id = 'block-context-menu';
      menu.className = 'dropdown-menu show';
      menu.style.cssText = 'position:fixed;z-index:1200;left:' + e.clientX + 'px;top:' + e.clientY + 'px;';
      menu.innerHTML =
        '<button class="dropdown-item" data-action="to-queue"><i class="bi bi-arrow-left-square"></i> 큐로 보내기</button>' +
        '<button class="dropdown-item" data-action="lock"><i class="bi bi-lock"></i> 잠금 토글</button>' +
        '<button class="dropdown-item text-danger" data-action="delete"><i class="bi bi-trash"></i> 삭제</button>';
      document.body.appendChild(menu);

      menu.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-action]');
        if (!btn) return;
        menu.remove();
        if (btn.dataset.action === 'to-queue') {
          api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
            .then(function () {
              showToast('큐로 되돌렸습니다.', 'success');
              location.reload();
            })
            .catch(function (err) { showToast(err.message, 'danger'); });
        } else if (btn.dataset.action === 'lock') {
          api('PUT', '/schedule/api/blocks/' + blockId + '/lock')
            .then(function () { location.reload(); })
            .catch(function (err) { showToast(err.message, 'danger'); });
        } else if (btn.dataset.action === 'delete') {
          if (confirm('이 블록을 삭제하시겠습니까?')) {
            api('DELETE', '/schedule/api/blocks/' + blockId)
              .then(function () { location.reload(); })
              .catch(function (err) { showToast(err.message, 'danger'); });
          }
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
  // 5. Draft controls
  // =====================================================================
  function initDraftControls() {
    var toolbar = document.querySelector('.schedule-nav');
    if (!toolbar) return;
    var g = document.createElement('div');
    g.className = 'ms-auto d-flex gap-1';
    g.innerHTML =
      '<button class="btn btn-sm btn-outline-success" id="btn-generate">자동 스케줄링</button>' +
      '<button class="btn btn-sm btn-success" id="btn-approve" style="display:none">초안 확정</button>' +
      '<button class="btn btn-sm btn-outline-danger" id="btn-discard" style="display:none">초안 폐기</button>';
    toolbar.appendChild(g);
    if (document.querySelector('.schedule-block.draft')) {
      document.getElementById('btn-approve').style.display = '';
      document.getElementById('btn-discard').style.display = '';
    }
    document.getElementById('btn-generate').onclick = function () {
      api('POST', '/schedule/api/draft/generate').then(function (r) {
        var msg = r.placed_count + '개 블록 배치';
        if (r.unplaced && r.unplaced.length) msg += ' (미배치 ' + r.unplaced.length + '개)';
        showToast(msg, 'success');
        setTimeout(function () { location.reload(); }, 500);
      }).catch(function (err) { showToast(err.message, 'danger'); });
    };
    document.getElementById('btn-approve').onclick = function () {
      api('POST', '/schedule/api/draft/approve').then(function () {
        showToast('초안 확정', 'success');
        setTimeout(function () { location.reload(); }, 500);
      }).catch(function (err) { showToast(err.message, 'danger'); });
    };
    document.getElementById('btn-discard').onclick = function () {
      if (!confirm('초안을 모두 폐기하시겠습니까?')) return;
      api('POST', '/schedule/api/draft/discard').then(function () {
        showToast('초안 폐기', 'info');
        setTimeout(function () { location.reload(); }, 500);
      }).catch(function (err) { showToast(err.message, 'danger'); });
    };
  }

  // =====================================================================
  // 6. Return-to-queue buttons
  // =====================================================================
  function initReturnToQueue() {
    document.querySelectorAll('.btn-to-queue[data-block-id]').forEach(function (btn) {
      btn.addEventListener('mousedown', function (e) {
        e.stopPropagation();
      });
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        e.preventDefault();
        if (isReadonly()) return;
        var blockId = btn.dataset.blockId;
        api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
          .then(function () {
            showToast('큐로 되돌렸습니다.', 'success');
            location.reload();
          })
          .catch(function (err) { showToast(err.message, 'danger'); });
      });
    });
  }

  // =====================================================================
  // 7. Queue sort
  // =====================================================================
  function initQueueSort() {
    var body = document.getElementById('task-queue-body');
    if (!body) return;
    var priorityOrder = { high: 0, medium: 1, low: 2 };
    var currentSort = 'deadline';
    var ascending = true;

    document.querySelectorAll('.queue-sort-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sortKey = btn.dataset.sort;
        if (sortKey === currentSort) {
          ascending = !ascending;
        } else {
          currentSort = sortKey;
          ascending = true;
        }

        document.querySelectorAll('.queue-sort-btn').forEach(function (b) {
          b.classList.remove('active', 'desc');
        });
        btn.classList.add('active');
        if (!ascending) btn.classList.add('desc');

        var items = Array.from(body.querySelectorAll('.queue-task-item'));
        items.sort(function (a, b) {
          var result;
          if (sortKey === 'name') {
            result = (a.dataset.title || '').localeCompare(b.dataset.title || '');
          } else if (sortKey === 'hours') {
            result = parseFloat(a.dataset.remainingHours) - parseFloat(b.dataset.remainingHours);
          } else if (sortKey === 'priority') {
            result = (priorityOrder[a.dataset.priority] || 2) - (priorityOrder[b.dataset.priority] || 2);
          } else {
            result = (a.dataset.deadline || '').localeCompare(b.dataset.deadline || '');
          }
          return ascending ? result : -result;
        });
        items.forEach(function (item) { body.appendChild(item); });
      });
    });
  }

  // =====================================================================
  // 8. Queue toggle
  // =====================================================================
  function initQueueToggle() {
    var btn = document.getElementById('toggle-queue');
    var q = document.getElementById('task-queue');
    if (btn && q) btn.onclick = function () { q.classList.toggle('collapsed'); };
  }

  // =====================================================================
  // 9. Same-task hover highlight
  // =====================================================================
  function initTaskHoverLink() {
    var allItems = document.querySelectorAll('[data-task-id]');
    if (!allItems.length) return;

    allItems.forEach(function (el) {
      el.addEventListener('mouseenter', function () {
        var taskId = el.dataset.taskId;
        if (!taskId) return;
        document.querySelectorAll('[data-task-id="' + taskId + '"]').forEach(function (item) {
          item.classList.add('task-linked-hover');
        });
      });
      el.addEventListener('mouseleave', function () {
        document.querySelectorAll('.task-linked-hover').forEach(function (item) {
          item.classList.remove('task-linked-hover');
        });
      });
    });
  }

  // =====================================================================
  // Init
  // =====================================================================
  function isReadonly() {
    return document.body.classList.contains('readonly-mode');
  }

  document.addEventListener('DOMContentLoaded', function () {
    initBlockMove();
    initMonthBlockMove();
    initQueueDrag();
    initResize();
    initContextMenu();
    initReturnToQueue();
    initDraftControls();
    initQueueSort();
    initQueueToggle();
    initTaskHoverLink();
  });
})();
