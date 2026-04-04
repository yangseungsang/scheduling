/**
 * Calendar drag-drop & resize — mouse-event based.
 */
(function () {
  'use strict';

  var App = window.ScheduleApp || {};

  // Aliases from utils.js
  var GRID_MINUTES = App.GRID_MINUTES;
  var SLOT_HEIGHT = App.SLOT_HEIGHT;
  var showToast = App.showToast;
  var api = App.api;
  var getTaskRemaining = App.getTaskRemaining;
  var checkRemainingAfterPlace = App.checkRemainingAfterPlace;
  var showRemainingAlert = App.showRemainingAlert;
  var pad = App.pad;
  var timeToMin = App.timeToMin;
  var minToTime = App.minToTime;
  var snapMin = App.snapMin;
  var workMinutes = App.workMinutes;
  var isReadonly = App.isReadonly;

  // Aliases from modals.js
  var showConfirmModal = App.showConfirmModal;
  var openMemoModal = App.openMemoModal;

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
    // Check if "전체" is active
    var allBtn = document.querySelector('.loc-filter-btn.active[data-loc-id=""]');
    if (!allBtn) {
      // Filter to only active locations
      var activeIds = {};
      document.querySelectorAll('.loc-filter-btn.active[data-loc-id]').forEach(function (b) {
        if (b.dataset.locId) activeIds[b.dataset.locId] = true;
      });
      if (Object.keys(activeIds).length > 0) {
        locs = locs.filter(function (l) { return activeIds[l.id]; });
      }
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
        var title = (item.querySelector('.queue-card-section-title') || item.querySelector('.queue-card-id') || {}).textContent || '';

        var testListRaw = item.dataset.testList || '[]';
        var testList = [];
        try { testList = JSON.parse(testListRaw); } catch(e2) {}

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
            if (target.type === 'queue') return; // dropped back into queue — do nothing
            function createBlock(selectedIds, overrideMin) {
              var bMin = overrideMin || blockMin;
              var identifierIds = selectedIds || null;
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
                    end_time: minToTime(t + bMin),
                    origin: 'manual',
                    identifier_ids: identifierIds,
                  });
                }).then(function () {
                  return checkRemainingAfterPlace(taskId, title.trim(), prevRem);
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
                    end_time: minToTime(510 + bMin),
                    origin: 'manual',
                    identifier_ids: identifierIds,
                  });
                }).then(function () {
                  return checkRemainingAfterPlace(taskId, title.trim(), prevRem2);
                }).then(function () { location.reload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              }
            }

            // If multiple identifiers, show picker with scheduled status
            if (testList.length > 1) {
              // Fetch existing blocks for this task to find already-placed identifiers
              api('GET', '/schedule/api/blocks/by-task/' + taskId).then(function (res) {
                var existingBlocks = (res && res.blocks) || [];
                var scheduledIds = [];
                existingBlocks.forEach(function (b) {
                  var ids = b.identifier_ids;
                  if (ids && ids.length) {
                    // Only explicitly assigned identifiers count as scheduled
                    ids.forEach(function (id) { scheduledIds.push(id); });
                  }
                  // identifier_ids=null means not split — don't mark all as scheduled
                });

                showIdentifierPicker(testList, { scheduledIds: scheduledIds }, function (selected) {
                  if (!selected) return;
                  var allIds = testList.map(function (s) { return typeof s === 'object' ? s.id : s; });
                  var selectedIds = selected.map(function (s) { return typeof s === 'object' ? s.id : s; });
                  var isAll = selectedIds.length === allIds.length;
                  if (isAll) {
                    createBlock(null, null);
                  } else {
                    var totalMin = 0;
                    selected.forEach(function (s) { totalMin += typeof s === 'object' ? Math.round((s.estimated_hours || 0) * 60) : 0; });
                    totalMin = Math.max(totalMin, GRID_MINUTES);
                    totalMin = Math.round(totalMin / GRID_MINUTES) * GRID_MINUTES;
                    createBlock(selectedIds, totalMin);
                  }
                });
              }).catch(function () {
                // Fallback: show picker without scheduled info
                showIdentifierPicker(testList, function (selected) {
                  if (!selected) return;
                  createBlock(null, null);
                });
              });
            } else {
              createBlock(null, null);
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
          var slotFromTop = Math.round(finalTop / SLOT_HEIGHT);
          var slotCount = Math.round(finalH / SLOT_HEIGHT);
          var newStartMin = wsMin + slotFromTop * GRID_MINUTES;
          var durMin = slotCount * GRID_MINUTES;

          var newStart = minToTime(newStartMin);
          var newEnd = minToTime(newStartMin + durMin);

          if (newStart !== block.dataset.startTime || newEnd !== block.dataset.endTime) {
            var taskId = block.dataset.taskId;
            var blockTitle = (block.querySelector('.block-title') || {}).textContent || '';
            var origStartMin = timeToMin(block.dataset.startTime);
            var origEndMin = timeToMin(block.dataset.endTime);
            var prevWorkMin = workMinutes(origStartMin, origEndMin);
            var newWorkMin = workMinutes(newStartMin, newStartMin + durMin);

            function doResize() {
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

            // Warn if shrinking from current size
            if (newWorkMin < prevWorkMin) {
              showConfirmModal(
                '현재 시간(<strong>' + prevWorkMin + '분</strong>)에서 <strong>' + newWorkMin + '분</strong>으로 줄입니다.<br>계속하시겠습니까?',
                { title: '시간 축소 경고', icon: 'exclamation-triangle-fill', okText: '줄이기', cancelText: '취소' }
              ).then(function (ok) {
                if (ok) {
                  doResize();
                } else {
                  block.style.top = origTop + 'px';
                  block.style.height = origHeight + 'px';
                }
              });
              return;
            }
            doResize();
          }
        }

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });
    });
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
            showSplitPicker(blockTestList, function (keepItems) {
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
    Promise.all([
      api('GET', '/tasks/api/' + taskId),
      api('GET', '/schedule/api/blocks/by-task/' + taskId),
    ]).then(function (results) {
      var task = results[0].task;
      var allBlocks = (results[1] && results[1].blocks) || [];
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

      var blockIdentifierIds = opts.identifierIds || null;
      var displayTestList = task.test_list || [];
      if (blockIdentifierIds && blockIdentifierIds.length && displayTestList.length) {
        displayTestList = displayTestList.filter(function(item) {
          var itemId = (typeof item === 'object') ? item.id : item;
          return blockIdentifierIds.indexOf(itemId) !== -1;
        });
      }

      // Build identifier → schedule mapping from allBlocks
      var allTaskIds = (task.test_list || []).map(function(it) { return typeof it === 'object' ? it.id : it; });
      var idScheduleMap = {};
      allBlocks.sort(function(a,b) { return (a.date + a.start_time).localeCompare(b.date + b.start_time); });
      allBlocks.forEach(function(blk) {
        var bids = blk.identifier_ids || allTaskIds;
        bids.forEach(function(iid) {
          if (!idScheduleMap[iid]) {
            idScheduleMap[iid] = blk.date + ' ' + blk.start_time + '–' + blk.end_time;
          }
        });
      });

      var testListHtml = '-';
      if (displayTestList.length) {
        var idTotalMin = 0;
        testListHtml = '<table style="width:100%;font-size:0.78rem;border-collapse:collapse;border-spacing:0">' +
          '<colgroup><col style="width:20%"><col style="width:12%"><col style="width:33%"><col style="width:35%"></colgroup>' +
          '<tr style="color:#9ca3af;font-size:0.68rem;border-bottom:1px solid #f3f4f6">' +
            '<td style="padding:3px 4px">식별자</td><td style="padding:3px 4px">시간</td>' +
            '<td style="padding:3px 4px">작성자</td><td style="padding:3px 4px">배치</td></tr>' +
          displayTestList.map(function(item) {
            if (typeof item === 'object' && item.id) {
              var mins = Math.round((item.estimated_hours || 0) * 60);
              idTotalMin += mins;
              var ow = (item.owners || []).join(', ') || '-';
              var sched = idScheduleMap[item.id];
              var schedHtml = sched
                ? '<a href="/schedule/?date=' + sched.split(' ')[0] + '" style="color:#2563eb;text-decoration:none;font-size:0.72rem;white-space:nowrap">' + sched + '</a>'
                : '<span style="color:#adb5bd">미배치</span>';
              return '<tr style="border-bottom:1px solid #f9fafb">' +
                '<td style="padding:3px 4px;font-weight:600;white-space:nowrap">' + item.id + '</td>' +
                '<td style="padding:3px 4px;white-space:nowrap">' + mins + '분</td>' +
                '<td style="padding:3px 4px;color:#6c757d">' + ow + '</td>' +
                '<td style="padding:3px 4px">' + schedHtml + '</td></tr>';
            }
            return '<tr><td colspan="4" style="padding:3px 4px">' + item + '</td></tr>';
          }).join('') +
          '<tr style="border-top:1px solid #e5e7eb">' +
            '<td style="padding:4px;font-weight:700">합계</td>' +
            '<td style="padding:4px;font-weight:700">' + idTotalMin + '분</td>' +
            '<td colspan="2"></td></tr>' +
          '</table>';
      }
      var splitInfo = '';
      var totalIdCount = (task.test_list || []).length;
      if (blockIdentifierIds && blockIdentifierIds.length < totalIdCount) {
        splitInfo = ' <span style="font-size:0.75rem;color:#6c757d">(분할 ' + displayTestList.length + '/' + totalIdCount + ')</span>';
      }

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
              '<span class="bd-id">' + (task.section_name || '') + '</span>' +
              statusBadge +
            '</div>' +
            '<button class="bd-x" id="block-detail-close">&times;</button>' +
          '</div>' +
          '<div class="bd-divider"></div>' +
          '<table class="bd-tbl">' +
            '<tr><td class="bd-k">시험 식별자' + splitInfo + '</td><td class="bd-v">' + testListHtml + '</td></tr>' +
            '<tr><td class="bd-k">예상 시간</td><td class="bd-v bd-v-edit">' +
              '<input type="number" class="bd-input" id="bd-est-min" value="' + hrsToMin(task.estimated_hours) + '" min="0" step="15">분' +
              ' <span class="bd-sub">(기준 ' + idTotalMin + '분 / 잔여 ' + hrsToMin(task.remaining_hours) + '분)</span>' +
            '</td></tr>' +
            '<tr><td class="bd-k">시험장소</td><td class="bd-v">' + (locationName || '-') + '</td></tr>' +
            (startTime ? '<tr><td class="bd-k">배치 시간</td><td class="bd-v">' + startTime + ' – ' + endTime + '</td></tr>' : '') +
            '<tr><td class="bd-k">시험 담당자</td><td class="bd-v">' + (assigneeName || '-') + '</td></tr>' +
            '<tr><td class="bd-k">버전</td><td class="bd-v">' + (task.version_name || '-') + '</td></tr>' +
            '<tr><td class="bd-k">상태</td><td class="bd-v">' + taskStatusLabel + '</td></tr>' +
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
        // Update task only — block position/size is unchanged
        api('PUT', '/tasks/api/' + taskId + '/update', Object.assign({}, task, updates))
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
        var idIds = null;
        try { if (block.dataset.identifierIds) idIds = JSON.parse(block.dataset.identifierIds); } catch(ex) {}
        showTaskDetailPopup(taskId, {
          blockId: block.dataset.blockId || null,
          startTime: block.dataset.startTime || '',
          endTime: block.dataset.endTime || '',
          locationName: block.dataset.locationName || '',
          assigneeName: block.dataset.assigneeName || '',
          memo: block.dataset.memo || '',
          blockStatus: block.dataset.blockStatus || 'pending',
          color: block.style.backgroundColor || '#64748b',
          identifierIds: idIds,
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
  // 11. Weekend toggle
  // =====================================================================
  function initWeekendToggle() {
    var btn = document.getElementById('btn-toggle-weekends');
    if (!btn) return;
    var hidden = localStorage.getItem('hideWeekends') === '1';
    function applyWeekendVisibility() {
      // Week view
      document.querySelectorAll('.week-day-col[data-weekday="5"], .week-day-col[data-weekday="6"]').forEach(function (col) {
        col.style.display = hidden ? 'none' : '';
      });
      // Month view
      document.querySelectorAll('th[data-weekday="5"], th[data-weekday="6"]').forEach(function (th) {
        th.style.display = hidden ? 'none' : '';
      });
      document.querySelectorAll('.month-table tbody tr').forEach(function (row) {
        var cells = row.querySelectorAll('td');
        if (cells.length >= 7) {
          cells[5].style.display = hidden ? 'none' : '';
          cells[6].style.display = hidden ? 'none' : '';
        }
      });
      btn.classList.toggle('active', hidden);
    }
    applyWeekendVisibility();
    btn.addEventListener('click', function () {
      hidden = !hidden;
      localStorage.setItem('hideWeekends', hidden ? '1' : '0');
      applyWeekendVisibility();
    });
  }

  // =====================================================================
  // 12. Schedule shift (bulk date move)
  // =====================================================================
  function initShiftSchedule() {
    var btn = document.getElementById('btn-shift-schedule');
    if (!btn) return;
    btn.addEventListener('click', function () {
      if (isReadonly()) return;
      var old = document.getElementById('shift-schedule-popup');
      if (old) old.remove();

      var today = new Date().toISOString().slice(0, 10);
      var overlay = document.createElement('div');
      overlay.id = 'shift-schedule-popup';
      overlay.className = 'block-detail-overlay';
      overlay.innerHTML =
        '<div class="bd-box" style="max-width:360px">' +
          '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">일정 이동</span></div>' +
            '<button class="bd-x" id="shift-close">&times;</button></div>' +
          '<div class="bd-divider"></div>' +
          '<div style="padding:12px">' +
            '<label class="form-label">기준 날짜 (이 날짜 이후 전체 이동)</label>' +
            '<input type="date" class="form-control form-control-sm mb-2" id="shift-from-date" value="' + today + '">' +
            '<label class="form-label">방향</label>' +
            '<select class="form-select form-select-sm mb-2" id="shift-direction">' +
              '<option value="1">+1일 (뒤로 밀기)</option>' +
              '<option value="-1">-1일 (앞으로 당기기)</option>' +
            '</select>' +
            '<div class="form-text mb-2">주말은 자동으로 건너뜁니다.</div>' +
            '<button class="btn btn-sm btn-primary w-100" id="shift-ok">이동 실행</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function (ev) { if (ev.target === overlay) overlay.remove(); });
      document.getElementById('shift-close').addEventListener('click', function () { overlay.remove(); });
      document.getElementById('shift-ok').addEventListener('click', function () {
        var fromDate = document.getElementById('shift-from-date').value;
        var direction = parseInt(document.getElementById('shift-direction').value);
        if (!fromDate) { showToast('날짜를 입력하세요.', 'danger'); return; }
        var params = new URLSearchParams(window.location.search);
        var versionId = params.get('version') || '';
        overlay.remove();
        api('POST', '/schedule/api/blocks/shift', {
          from_date: fromDate, direction: direction, version_id: versionId
        }).then(function (r) {
          showToast(r.shifted_count + '개 블록 이동 완료', 'success');
          setTimeout(function () { location.reload(); }, 500);
        }).catch(function (err) { showToast(err.message, 'danger'); });
      });
    });
  }

  // =====================================================================
  // =====================================================================
  // 14b. Split picker — check = keep in block, uncheck = send to queue
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

  // =====================================================================
  // 13. Add task / Add simple block
  // =====================================================================
  function initAddButtons() {
    var taskBtn = document.getElementById('btn-add-task');
    if (taskBtn) {
      taskBtn.addEventListener('click', function () {
        window.location.href = '/tasks/new';
      });
    }

    var blockBtn = document.getElementById('btn-add-simple-block');
    if (!blockBtn) return;
    blockBtn.addEventListener('click', function () {
      if (isReadonly()) return;
      var old = document.getElementById('simple-block-popup');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'simple-block-popup';
      overlay.className = 'block-detail-overlay';
      overlay.innerHTML =
        '<div class="bd-box" style="max-width:340px">' +
          '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">블록 추가</span></div>' +
            '<button class="bd-x" id="simple-close">&times;</button></div>' +
          '<div class="bd-divider"></div>' +
          '<div style="padding:12px">' +
            '<label class="form-label">제목</label>' +
            '<input type="text" class="form-control form-control-sm mb-2" id="simple-title" placeholder="예: 시험 준비, 장비 점검">' +
            '<label class="form-label">예상 시간 (분)</label>' +
            '<input type="number" class="form-control form-control-sm mb-2" id="simple-minutes" value="60" min="10" step="10">' +
            '<div class="form-text mb-2">큐에 추가 후 드래그하여 배치하세요.</div>' +
            '<button class="btn btn-sm btn-primary w-100" id="simple-ok">큐에 추가</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function (ev) { if (ev.target === overlay) overlay.remove(); });
      document.getElementById('simple-close').addEventListener('click', function () { overlay.remove(); });
      document.getElementById('simple-ok').addEventListener('click', function () {
        var title = document.getElementById('simple-title').value.trim();
        var minutes = parseInt(document.getElementById('simple-minutes').value) || 60;
        if (!title) { showToast('제목을 입력하세요.', 'danger'); return; }
        overlay.remove();
        var params = new URLSearchParams(window.location.search);
        var versionId = params.get('version') || '';
        api('POST', '/schedule/api/simple-blocks', {
          title: title, estimated_minutes: minutes, version_id: versionId,
        }).then(function () {
          showToast('큐에 추가되었습니다.', 'success');
          setTimeout(function () { location.reload(); }, 300);
        }).catch(function (err) { showToast(err.message, 'danger'); });
      });
    });
  }

  // =====================================================================
  // 14. Identifier selection on queue drag (section split)
  // =====================================================================
  /**
   * @param {Array} testList - all identifiers from the task
   * @param {Object} opts - { scheduledIds: Set or Array of already-placed identifier IDs }
   * @param {Function} callback - called with selected items array, or null if cancelled
   */
  function showIdentifierPicker(testList, opts, callback) {
    // Support old 2-arg call: showIdentifierPicker(list, cb)
    if (typeof opts === 'function') { callback = opts; opts = {}; }
    opts = opts || {};
    var scheduledSet = {};
    (opts.scheduledIds || []).forEach(function (id) { scheduledSet[id] = true; });

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
      var isScheduled = !!scheduledSet[id];
      var checked = isScheduled ? '' : ' checked';
      var badge = isScheduled
        ? ' <span class="badge bg-secondary" style="font-size:0.65rem;vertical-align:middle">배치됨</span>'
        : '';
      var ownerStr = owners.length ? ' <span class="text-muted">작성: ' + owners.join(', ') + '</span>' : '';
      rows += '<label class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem' + (isScheduled ? ';opacity:0.55' : '') + '">' +
        '<input type="checkbox" class="form-check-input" value="' + i + '"' + checked + '> ' +
        '<span>' + id + '</span>' + ownerStr +
        (mins > 0 ? ' <span class="text-muted">(' + mins + '분)</span>' : '') +
        badge +
        '</label>';
    });
    overlay.innerHTML =
      '<div class="bd-box" style="max-width:340px">' +
        '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">식별자 선택</span></div>' +
          '<button class="bd-x" id="picker-close">&times;</button></div>' +
        '<div class="bd-divider"></div>' +
        '<div style="padding:12px">' +
          '<div class="form-text mb-2">배치할 식별자를 선택하세요</div>' +
          '<div id="picker-list">' + rows + '</div>' +
          '<button class="btn btn-sm btn-primary w-100 mt-2" id="picker-ok">확인</button>' +
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
      if (checked.length === 0) { callback(null); return; }
      var selected = checked.map(function (i) { return testList[i]; });
      callback(selected);
    });
  }

  // =====================================================================
  // Init
  // =====================================================================
  document.addEventListener('DOMContentLoaded', function () {
    // Sync grid interval from server settings
    if (window.GRID_INTERVAL) {
      GRID_MINUTES = window.GRID_INTERVAL;
      App.GRID_MINUTES = GRID_MINUTES;
    }
    initBlockMove();
    initMonthBlockMove();
    initQueueDrag();
    initResize();
    initContextMenu();
    initReturnToQueue();
    initQueueSearch();
    initQueueToggle();
    initTaskHoverLink();
    initBlockDetail();
    initWeekendToggle();
    initShiftSchedule();
    initAddButtons();
  });
})();
