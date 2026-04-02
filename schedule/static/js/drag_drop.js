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
  // Remaining-hours check after placing a block
  // =====================================================================
  function getTaskRemaining(taskId) {
    return api('GET', '/tasks/api/' + taskId).then(function (res) {
      return res.task ? res.task.remaining_hours : 0;
    }).catch(function () { return 0; });
  }

  function checkRemainingAfterPlace(taskId, procedureId, prevRemaining) {
    return api('GET', '/tasks/api/' + taskId).then(function (res) {
      var task = res.task;
      if (!task) return false;
      var remaining = task.remaining_hours;
      // Only alert when remaining hours INCREASED (time was cut)
      if (remaining > 0 && remaining > (prevRemaining || 0)) {
        return showRemainingAlert(procedureId || task.procedure_id, remaining);
      }
      return false;
    }).catch(function () { return false; });
  }

  function showRemainingAlert(procedureId, remaining) {
    return new Promise(function (resolve) {
      var old = document.getElementById('remaining-alert');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'remaining-alert';
      overlay.className = 'remaining-alert-overlay';
      overlay.innerHTML =
        '<div class="remaining-alert-box">' +
          '<div class="remaining-alert-icon"><i class="bi bi-exclamation-triangle-fill"></i></div>' +
          '<div class="remaining-alert-title">시험이 당일에 완료되지 않습니다</div>' +
          '<div class="remaining-alert-body">' +
            '<strong>' + procedureId + '</strong> 항목의 잔여 시간 <strong>' + Math.round(remaining * 60) + '분</strong>이 ' +
            '시험 큐에 남아있습니다.<br>추가 일정 배치가 필요합니다.' +
          '</div>' +
          '<button class="remaining-alert-btn" id="remaining-alert-close">확인</button>' +
        '</div>';

      document.body.appendChild(overlay);

      function close() {
        overlay.remove();
        resolve(true);
      }
      document.getElementById('remaining-alert-close').addEventListener('click', close);
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) close();
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

  /** Calculate work minutes between start and end, excluding break periods. */
  function workMinutes(startMin, endMin) {
    var breaks = window.SCHEDULE_BREAKS || [];
    var breakMin = 0;
    for (var i = 0; i < breaks.length; i++) {
      var bs = timeToMin(breaks[i].start);
      var be = timeToMin(breaks[i].end);
      var ovStart = Math.max(startMin, bs);
      var ovEnd = Math.min(endMin, be);
      if (ovStart < ovEnd) breakMin += ovEnd - ovStart;
    }
    return Math.max(0, endMin - startMin - breakMin);
  }

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
  // Week location guides — show location zones during drag
  // =====================================================================
  function getLocations() {
    var locs = [];
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (b.dataset.locId) locs.push({ id: b.dataset.locId, name: b.textContent.trim(), color: '' });
    });
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (!b.dataset.locId) return;
      var dot = b.querySelector('.loc-filter-dot');
      for (var i = 0; i < locs.length; i++) {
        if (locs[i].id === b.dataset.locId && dot) {
          locs[i].color = dot.style.background || dot.style.backgroundColor || '#94a3b8';
          break;
        }
      }
    });
    return locs;
  }

  var weekGuideEl = null;
  var weekGuideLocs = null;
  function showWeekLocationGuides() { /* no-op: guides are now shown per-column on hover */ }
  function hideWeekLocationGuides() {
    if (weekGuideEl) { weekGuideEl.remove(); weekGuideEl = null; }
  }

  function getWeekGuideLocs() {
    if (weekGuideLocs) return weekGuideLocs;
    var locs = getLocations();
    if (locs.length === 0) return locs;
    var activeBtn = document.querySelector('.loc-filter-btn.active');
    if (activeBtn && activeBtn.dataset.locId) {
      locs = locs.filter(function (l) { return l.id === activeBtn.dataset.locId; });
    }
    weekGuideLocs = locs;
    return locs;
  }

  function ensureWeekGuide(slotsEl) {
    // Already showing on this column
    if (weekGuideEl && weekGuideEl.parentNode === slotsEl) return weekGuideEl;
    // Remove from previous column
    if (weekGuideEl) { weekGuideEl.remove(); weekGuideEl = null; }

    var locs = getWeekGuideLocs();
    if (locs.length <= 1) return null;

    var overlay = document.createElement('div');
    overlay.className = 'week-loc-guide-overlay';
    overlay.style.cssText = 'position:absolute;top:0;left:0;right:0;bottom:0;z-index:8;pointer-events:none;display:flex;';
    for (var i = 0; i < locs.length; i++) {
      var zone = document.createElement('div');
      zone.className = 'week-loc-guide-zone';
      zone.dataset.locationId = locs[i].id;
      zone.style.cssText = 'flex:1;border-right:1px dashed ' + locs[i].color + ';position:relative;';
      if (i === locs.length - 1) zone.style.borderRight = 'none';
      var label = document.createElement('div');
      label.className = 'week-loc-guide-label';
      label.textContent = locs[i].name;
      label.style.cssText = 'position:sticky;top:0;font-size:0.6rem;font-weight:600;color:' + locs[i].color +
        ';text-align:center;padding:2px 0;background:rgba(255,255,255,0.85);border-bottom:2px solid ' + locs[i].color + ';white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
      zone.appendChild(label);
      overlay.appendChild(zone);
    }
    slotsEl.appendChild(overlay);
    weekGuideEl = overlay;
    return overlay;
  }

  function resolveWeekLocation(x, slot) {
    if (slot.dataset.locationId) return slot.dataset.locationId;
    var slotsEl = slot.closest('.week-day-slots');
    if (!slotsEl) return '';
    var overlay = ensureWeekGuide(slotsEl);
    if (!overlay) return '';
    var zones = overlay.querySelectorAll('.week-loc-guide-zone');
    if (zones.length === 0) return '';
    var rect = slotsEl.getBoundingClientRect();
    var relX = x - rect.left;
    var zoneWidth = rect.width / zones.length;
    var idx = Math.max(0, Math.min(zones.length - 1, Math.floor(relX / zoneWidth)));
    return zones[idx].dataset.locationId || '';
  }

  // =====================================================================
  // Find target under cursor
  // =====================================================================
  function findTarget(x, y) {
    var el = document.elementFromPoint(x, y);
    if (!el) return null;
    var slot = el.closest('.time-slot');
    if (slot && slot.dataset.date && slot.dataset.time) {
      var locId = slot.dataset.locationId || resolveWeekLocation(x, slot);
      return { type: 'slot', date: slot.dataset.date, time: slot.dataset.time, locationId: locId, el: slot };
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
  function createGhost(text, color, w, h) {
    var g = document.createElement('div');
    g.textContent = text;
    g.style.cssText =
      'position:fixed;z-index:9999;pointer-events:none;opacity:0.8;' +
      'padding:4px 8px;border-radius:4px;font-size:0.75rem;color:#fff;' +
      'overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.3);' +
      'background:' + (color || '#0d6efd') + ';' +
      'width:' + (w || 120) + 'px;' +
      (h ? 'height:' + h + 'px;' : '');
    document.body.appendChild(g);
    return g;
  }

  // =====================================================================
  // Highlight
  // =====================================================================
  var highlighted = null;
  var highlightedZone = null;
  function setHighlight(target, x) {
    clearHighlight();
    if (!target || !target.el) {
      // Cursor left the grid — remove guide
      hideWeekLocationGuides();
      return;
    }
    // For weekly view with location guides, highlight the zone instead of the full slot
    if (target.type === 'slot' && target.locationId && !target.el.dataset.locationId) {
      var slotsEl = target.el.closest('.week-day-slots');
      if (slotsEl) {
        var overlay = slotsEl.querySelector('.week-loc-guide-overlay');
        if (overlay) {
          var zones = overlay.querySelectorAll('.week-loc-guide-zone');
          for (var i = 0; i < zones.length; i++) {
            if (zones[i].dataset.locationId === target.locationId) {
              zones[i].classList.add('week-loc-guide-active');
              highlightedZone = zones[i];
              break;
            }
          }
        }
      }
    } else {
      // Not on a weekly slot — remove guide from previous column
      hideWeekLocationGuides();
    }
    target.el.classList.add('drag-over');
    highlighted = target.el;
  }
  function clearHighlight() {
    if (highlighted) highlighted.classList.remove('drag-over');
    highlighted = null;
    if (highlightedZone) highlightedZone.classList.remove('week-loc-guide-active');
    highlightedZone = null;
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
        ghost = createGhost(opts.ghostText, opts.ghostColor, opts.ghostWidth, opts.ghostHeight);
        hideAllBlocks();
        showWeekLocationGuides();
        if (opts.sourceEl) opts.sourceEl.style.opacity = '0.3';
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'grabbing';
      }

      ghost.style.left = ev.clientX - (ghost.offsetWidth / 2) + 'px';
      ghost.style.top = ev.clientY - 10 + 'px';

      var target = findTarget(ev.clientX, ev.clientY);
      setHighlight(target, ev.clientX);
    }

    function onUp(ev) {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);

      var target = null;
      if (dragging) {
        target = findTarget(ev.clientX, ev.clientY);
      }

      clearHighlight();
      hideWeekLocationGuides();
      weekGuideLocs = null;
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
        var taskId = block.dataset.taskId;
        var title = (block.querySelector('.block-title') || {}).textContent || '';
        var color = block.style.backgroundColor || '#0d6efd';
        var startTime = block.dataset.startTime;
        var endTime = block.dataset.endTime;
        var durationMin = workMinutes(timeToMin(startTime), timeToMin(endTime));
        var ghostH = (durationMin / GRID_MINUTES) * SLOT_HEIGHT;

        startDrag(e, {
          sourceEl: block,
          ghostText: title,
          ghostColor: color,
          ghostWidth: block.offsetWidth,
          ghostHeight: ghostH,
          onDrop: function (target) {
            if (target.type === 'queue') {
              api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
                .then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            } else if (target.type === 'slot') {
              var t = snapMin(timeToMin(target.time));
              var moveUpdate = {
                date: target.date,
                start_time: minToTime(t),
                end_time: minToTime(t + durationMin),
              };
              if (target.locationId) moveUpdate.location_id = target.locationId;
              var prevRem;
              (taskId ? getTaskRemaining(taskId) : Promise.resolve(0)).then(function (r) {
                prevRem = r;
                return api('PUT', '/schedule/api/blocks/' + blockId, moveUpdate);
              }).then(function () {
                if (taskId) return checkRemainingAfterPlace(taskId, title.trim(), prevRem);
              }).then(function () {
                location.reload();
              }).catch(function (err) {
                showToast(err.message, 'danger');
              });
            } else if (target.type === 'month') {
              var prevRem2;
              (taskId ? getTaskRemaining(taskId) : Promise.resolve(0)).then(function (r) {
                prevRem2 = r;
                return api('PUT', '/schedule/api/blocks/' + blockId, {
                  date: target.date,
                });
              }).then(function () {
                if (taskId) return checkRemainingAfterPlace(taskId, title.trim(), prevRem2);
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
        var assigneeIds = item.dataset.assigneeIds ? item.dataset.assigneeIds.split(',').filter(Boolean) : [];
        var locationId = item.dataset.locationId || '';
        var versionId = item.dataset.versionId || '';
        var remaining = parseFloat(item.dataset.remainingHours) || 1;
        var procedureId = (item.querySelector('.queue-card-id') || item.querySelector('.queue-task-title') || {}).textContent || '';
        var title = procedureId;

        // Calculate expected block height: remaining hours * 60 / grid * slot_height
        var blockMin = Math.round(remaining * 60);
        blockMin = Math.max(blockMin, GRID_MINUTES);
        blockMin = Math.round(blockMin / GRID_MINUTES) * GRID_MINUTES;
        var expectedHeight = (blockMin / GRID_MINUTES) * SLOT_HEIGHT;

        startDrag(e, {
          sourceEl: item,
          ghostText: title,
          ghostColor: '#0d6efd',
          ghostWidth: 150,
          ghostHeight: expectedHeight,
          onDrop: function (target) {
            if (target.type === 'slot') {
              var t = snapMin(timeToMin(target.time));
              var dropLocationId = target.locationId || locationId;
              var prevRem;
              getTaskRemaining(taskId).then(function (r) {
                prevRem = r;
                return api('POST', '/schedule/api/blocks', {
                  task_id: taskId, assignee_ids: assigneeIds,
                  location_id: dropLocationId, version_id: versionId,
                  date: target.date,
                  start_time: minToTime(t),
                  end_time: minToTime(t + blockMin),
                  origin: 'manual',
                });
              }).then(function () {
                return checkRemainingAfterPlace(taskId, procedureId, prevRem);
              }).then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });

            } else if (target.type === 'month') {
              var prevRem2;
              getTaskRemaining(taskId).then(function (r) {
                prevRem2 = r;
                return api('POST', '/schedule/api/blocks', {
                  task_id: taskId, assignee_ids: assigneeIds,
                  location_id: locationId, version_id: versionId,
                  date: target.date,
                  start_time: '08:30',
                  end_time: minToTime(510 + blockMin),
                  origin: 'manual',
                });
              }).then(function () {
                return checkRemainingAfterPlace(taskId, procedureId, prevRem2);
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
        var taskId = item.dataset.taskId;
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
              var prevRem;
              (taskId ? getTaskRemaining(taskId) : Promise.resolve(0)).then(function (r) {
                prevRem = r;
                return api('PUT', '/schedule/api/blocks/' + blockId, {
                  date: target.date,
                });
              }).then(function () {
                if (taskId) return checkRemainingAfterPlace(taskId, title, prevRem);
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
            var taskId = block.dataset.taskId;
            var blockTitle = (block.querySelector('.block-title') || {}).textContent || '';
            var prevRem;
            (taskId ? getTaskRemaining(taskId) : Promise.resolve(0)).then(function (r) {
              prevRem = r;
              return api('PUT', '/schedule/api/blocks/' + blockId, {
                start_time: newStart,
                end_time: newEnd,
                resize: true,
              });
            }).then(function () {
              if (taskId) return checkRemainingAfterPlace(taskId, blockTitle.trim(), prevRem);
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
  // 4. Memo modal
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

  // =====================================================================
  // 5. Context menu
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

    var hasDrafts = !!document.querySelector('.schedule-block.draft, .month-block-item.draft');

    var g = document.createElement('div');
    g.className = 'ms-auto d-flex gap-1';
    g.innerHTML =
      '<button class="btn btn-sm btn-outline-success" id="btn-generate">자동 스케줄링</button>' +
      '<button class="btn btn-sm btn-success" id="btn-approve"' + (hasDrafts ? '' : ' style="display:none"') + '>초안 확정</button>' +
      '<button class="btn btn-sm btn-outline-danger" id="btn-discard"' + (hasDrafts ? '' : ' style="display:none"') + '>초안 폐기</button>';
    toolbar.appendChild(g);

    // Generate button → show settings popup
    document.getElementById('btn-generate').onclick = function () {
      var old = document.getElementById('schedule-config-popup');
      if (old) old.remove();

      var today = new Date();
      var mon = new Date(today);
      mon.setDate(today.getDate() - (today.getDay() || 7) + 1);
      var fri = new Date(mon);
      fri.setDate(mon.getDate() + 4);
      var defStart = mon.toISOString().slice(0, 10);
      var defEnd = fri.toISOString().slice(0, 10);

      var overlay = document.createElement('div');
      overlay.id = 'schedule-config-popup';
      overlay.className = 'block-detail-overlay';
      overlay.innerHTML =
        '<div class="sched-cfg">' +
          '<div class="sched-cfg-title">자동 스케줄링 설정</div>' +
          '<div class="sched-cfg-desc">' +
            '등록된 시험 항목들을 절차서 번호 순서대로, ' +
            '시작일부터 가장 빠른 빈 시간에 자동 배치합니다.<br>' +
            '<ul>' +
              '<li>장소가 지정되지 않은 항목은 가장 여유 있는 장소에 자동 배정됩니다.</li>' +
              '<li>같은 장소·같은 시간에 시험이 겹치지 않도록 배치합니다.</li>' +
              '<li>점심시간과 휴식시간은 자동으로 건너뜁니다.</li>' +
              '<li>결과는 <strong>초안</strong>으로 생성되며, 확인 후 확정하거나 폐기할 수 있습니다.</li>' +
            '</ul>' +
          '</div>' +
          '<div class="sched-cfg-body">' +
            '<label class="sched-cfg-label">시작일</label>' +
            '<input type="date" class="form-control form-control-sm" id="sched-start" value="' + defStart + '">' +
            '<label class="sched-cfg-label">종료일</label>' +
            '<input type="date" class="form-control form-control-sm" id="sched-end" value="' + defEnd + '">' +
            '<div class="sched-cfg-note">주말은 자동으로 제외됩니다.</div>' +
            '<label class="sched-cfg-check">' +
              '<input type="checkbox" id="sched-include-existing"> 기존 배치 항목도 재정렬 <span class="sched-cfg-hint">(잠금 제외)</span>' +
            '</label>' +
          '</div>' +
          '<div class="sched-cfg-actions">' +
            '<button class="sched-cfg-btn-cancel" id="sched-cancel">취소</button>' +
            '<button class="sched-cfg-btn-ok" id="sched-ok">스케줄링 실행</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function (ev) { if (ev.target === overlay) overlay.remove(); });
      document.getElementById('sched-cancel').onclick = function () { overlay.remove(); };
      document.getElementById('sched-ok').onclick = function () {
        var startDate = document.getElementById('sched-start').value;
        var endDate = document.getElementById('sched-end').value;
        var includeExisting = document.getElementById('sched-include-existing').checked;
        if (!startDate || !endDate) { showToast('날짜를 입력하세요.', 'danger'); return; }
        if (startDate > endDate) { showToast('시작일이 종료일보다 큽니다.', 'danger'); return; }
        overlay.remove();
        api('POST', '/schedule/api/draft/generate', {
          start_date: startDate,
          end_date: endDate,
          include_existing: includeExisting,
        }).then(function (r) {
          var msg = r.placed_count + '개 블록 배치 (' + r.workdays + '일)';
          if (r.unplaced && r.unplaced.length) msg += ' / 미배치 ' + r.unplaced.length + '개';
          showToast(msg, 'success');
          setTimeout(function () { location.reload(); }, 500);
        }).catch(function (err) { showToast(err.message, 'danger'); });
      };
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
  // 7. Queue search + alphabetical sort
  // =====================================================================
  function initQueueSearch() {
    var body = document.getElementById('task-queue-body');
    var input = document.getElementById('queue-search');
    if (!body || !input) return;

    // Initial sort: alphabetical by procedure_id
    function sortItems() {
      var items = Array.from(body.querySelectorAll('.queue-task-item'));
      items.sort(function (a, b) {
        return (a.dataset.title || '').localeCompare(b.dataset.title || '');
      });
      items.forEach(function (item) { body.appendChild(item); });
    }
    sortItems();

    // Search filter
    input.addEventListener('input', function () {
      var query = input.value.trim().toLowerCase();
      body.querySelectorAll('.queue-task-item').forEach(function (item) {
        var id = (item.dataset.title || '').toLowerCase();
        var section = (item.querySelector('.queue-card-section') || {}).textContent || '';
        section = section.toLowerCase();
        var match = !query || id.indexOf(query) !== -1 || section.indexOf(query) !== -1;
        item.style.display = match ? '' : 'none';
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
  // 10. Block detail popup (double-click)
  // =====================================================================
  function hrsToMin(h) { return Math.round(h * 60); }

  function showTaskDetailPopup(taskId, opts) {
    opts = opts || {};
    var blockId = opts.blockId || null;
    api('GET', '/tasks/api/' + taskId).then(function (res) {
      var task = res.task;
      if (!task) return;

      var startTime = opts.startTime || '';
      var endTime = opts.endTime || '';
      var locationName = task.location_name || opts.locationName || '';
      var assigneeName = (task.assignee_names && task.assignee_names.length)
        ? task.assignee_names.join(', ')
        : (opts.assigneeName || '-');
      var memo = task.memo || opts.memo || '';
      var status = opts.blockStatus || 'pending';
      var statusLabel = { pending: '대기', in_progress: '진행', completed: '완료', cancelled: '불가' }[status] || status;
      var blockColor = opts.color || '#64748b';
      var isQueued = opts.isQueued || false;

      var testListStr = (task.test_list && task.test_list.length) ? task.test_list.join(', ') : '-';

      var old = document.getElementById('block-detail-popup');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'block-detail-popup';
      overlay.className = 'block-detail-overlay';

      var statusBadge = isQueued
        ? '<span class="bd-badge bd-badge-queued">미배치</span>'
        : '<span class="bd-badge bd-badge-' + status + '">' + statusLabel + '</span>';

      var escapedMemo = memo.replace(/"/g, '&quot;').replace(/</g, '&lt;');

      var taskStatus = task.status || 'waiting';
      var taskStatusLabel = { waiting: '대기', in_progress: '진행 중', completed: '완료' }[taskStatus] || taskStatus;

      var html =
        '<div class="bd-box">' +
          '<div class="bd-header">' +
            '<div class="bd-header-left">' +
              '<span class="bd-id">' + (task.procedure_id || '') + '</span>' +
              statusBadge +
            '</div>' +
            '<button class="bd-x" id="block-detail-close">&times;</button>' +
          '</div>' +
          (task.section_name ? '<div class="bd-subtitle">' + task.section_name + '</div>' : '') +
          '<div class="bd-divider"></div>' +
          '<table class="bd-tbl">' +
            '<tr><td class="bd-k">장소</td><td class="bd-v">' + (locationName || '-') + '</td></tr>' +
            (startTime ? '<tr><td class="bd-k">시간</td><td class="bd-v">' + startTime + ' – ' + endTime + '</td></tr>' : '') +
            '<tr><td class="bd-k">소요</td><td class="bd-v bd-v-edit">' +
              '<input type="number" class="bd-input" id="bd-est-min" value="' + hrsToMin(task.estimated_hours) + '" min="0" step="15">분' +
              ' <span class="bd-sub">(잔여 ' + hrsToMin(task.remaining_hours) + '분)</span>' +
            '</td></tr>' +
            '<tr><td class="bd-k">시험 담당</td><td class="bd-v">' + (assigneeName || '-') + '</td></tr>' +
            '<tr><td class="bd-k">절차서 담당</td><td class="bd-v">' + (task.procedure_owner || '-') + '</td></tr>' +
            '<tr><td class="bd-k">버전</td><td class="bd-v">' + (task.version_name || '-') + '</td></tr>' +
            '<tr><td class="bd-k">상태</td><td class="bd-v">' + taskStatusLabel + '</td></tr>' +
            '<tr><td class="bd-k">시험목록</td><td class="bd-v">' + testListStr + '</td></tr>' +
            '<tr><td class="bd-k">생성일</td><td class="bd-v">' + (task.created_at || '-') + '</td></tr>' +
            '<tr><td class="bd-k">메모</td><td class="bd-v">' +
              '<textarea class="bd-textarea" id="bd-memo" rows="2" placeholder="메모 입력...">' + escapedMemo + '</textarea>' +
            '</td></tr>' +
          '</table>' +
          '<div class="bd-foot">' +
            '<a href="/tasks/' + taskId + '/edit">수정 페이지 &rarr;</a>' +
            '<button class="bd-save" id="bd-save">저장</button>' +
          '</div>' +
        '</div>';

      overlay.innerHTML = html;
      document.body.appendChild(overlay);

      document.getElementById('block-detail-close').addEventListener('click', function () {
        overlay.remove();
      });
      overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay) overlay.remove();
      });

      document.getElementById('bd-save').addEventListener('click', function () {
        var newMemo = document.getElementById('bd-memo').value;
        var newEstMin = parseInt(document.getElementById('bd-est-min').value, 10) || 0;
        var newEstHours = newEstMin / 60.0;
        var updates = { memo: newMemo };
        var durationChanged = newEstHours !== task.estimated_hours;
        if (durationChanged) {
          updates.estimated_hours = newEstHours;
          updates.remaining_hours = Math.max(0, newEstHours - (task.estimated_hours - task.remaining_hours));
        }
        // Update task
        api('PUT', '/tasks/api/' + taskId + '/update', Object.assign({}, task, updates))
          .then(function () {
            // If duration changed and block exists, update block end_time
            if (durationChanged && blockId) {
              return api('PUT', '/schedule/api/blocks/' + blockId, {
                duration_minutes: newEstMin,
              });
            }
          })
          .then(function () {
            showToast('저장되었습니다.', 'success');
            overlay.remove();
            setTimeout(function () { location.reload(); }, 300);
          })
          .catch(function (err) { showToast(err.message, 'danger'); });
      });
    });
  }

  function initBlockDetail() {
    // Schedule blocks + month blocks
    document.querySelectorAll('.schedule-block[data-block-id], .month-block-item[data-block-id]').forEach(function (block) {
      block.addEventListener('dblclick', function (e) {
        e.preventDefault();
        e.stopPropagation();

        var taskId = block.dataset.taskId;
        if (!taskId) return;
        showTaskDetailPopup(taskId, {
          blockId: block.dataset.blockId || null,
          startTime: block.dataset.startTime || '',
          endTime: block.dataset.endTime || '',
          locationName: block.dataset.locationName || '',
          assigneeName: block.dataset.assigneeName || '',
          memo: block.dataset.memo || '',
          blockStatus: block.dataset.blockStatus || 'pending',
          color: block.style.backgroundColor || '#64748b',
        });
      });
    });

    // Queue items
    document.querySelectorAll('.queue-task-item[data-task-id]').forEach(function (item) {
      item.addEventListener('dblclick', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var taskId = item.dataset.taskId;
        if (!taskId) return;
        showTaskDetailPopup(taskId, {
          locationName: item.dataset.locationName || '',
          assigneeName: item.dataset.assigneeName || '',
          color: item.dataset.queueColor || '#64748b',
          isQueued: true,
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
    initQueueSearch();
    initQueueToggle();
    initTaskHoverLink();
    initBlockDetail();
  });
})();
