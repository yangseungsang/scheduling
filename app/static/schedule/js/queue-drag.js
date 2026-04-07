/**
 * Queue drag — drag tasks from queue to calendar.
 */
(function (App) {
  'use strict';

  var startDrag = App.startDrag;
  var api = App.api;
  var showToast = App.showToast;
  var getTaskRemaining = App.getTaskRemaining;
  var checkRemainingAfterPlace = App.checkRemainingAfterPlace;
  var timeToMin = App.timeToMin;
  var minToTime = App.minToTime;
  var snapMin = App.snapMin;
  var GRID_MINUTES = App.GRID_MINUTES;
  var SLOT_HEIGHT = App.SLOT_HEIGHT;

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
        var remaining = parseFloat(item.dataset.remainingMinutes) || 1;
        var title = (item.querySelector('.queue-card-section-title') || item.querySelector('.queue-card-id') || {}).textContent || '';

        var testListRaw = item.dataset.testList || '[]';
        var testList = [];
        try { testList = JSON.parse(testListRaw); } catch(e2) {}

        var blockMin = Math.round(remaining);
        blockMin = Math.max(blockMin, 1);
        var expectedHeight = (blockMin / GRID_MINUTES) * SLOT_HEIGHT;

        startDrag(e, {
          sourceEl: item,
          ghostText: title,
          ghostColor: '#0d6efd',
          ghostWidth: 150,
          ghostHeight: expectedHeight,
          onDrop: function (target) {
            if (target.type === 'queue') return; // dropped back into queue — do nothing
            function getWorkEndMin() {
              var slots = document.querySelectorAll('.time-slot[data-time]');
              var max = 0;
              slots.forEach(function (s) {
                var t2 = timeToMin(s.dataset.time);
                if (t2 > max) max = t2;
              });
              return max || timeToMin('17:00');
            }

            function createBlock(selectedIds, overrideMin) {
              var bMin = overrideMin || blockMin;
              var identifierIds = selectedIds || null;
              var isPartial = !!selectedIds; // 분할 배치 여부

              function doCreate(startMin, endMin, overflowMin, locOverride) {
                var prevRem;
                var dropLocationId = locOverride || (target.type === 'slot' ? (target.locationId || locationId) : locationId);
                getTaskRemaining(taskId).then(function (r) {
                  prevRem = r;
                  var payload = {
                    task_id: taskId, assignee_ids: assigneeIds,
                    location_id: dropLocationId, version_id: versionId,
                    date: target.date,
                    start_time: minToTime(startMin),
                    end_time: minToTime(endMin),
                    identifier_ids: identifierIds,
                  };
                  if (overflowMin > 0) payload.overflow_minutes = overflowMin;
                  return api('POST', '/schedule/api/blocks', payload);
                }).then(function () {
                  if (!isPartial) return checkRemainingAfterPlace(taskId, title.trim(), prevRem);
                }).then(function () { return App.softReload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              }

              function clampAndCreate(startMin, duration, locOverride) {
                var endMin = startMin + duration;
                var workEnd = getWorkEndMin();
                if (endMin > workEnd) {
                  var overflow = endMin - workEnd;
                  var clampedMin = workEnd - startMin;
                  if (clampedMin <= 0) {
                    showToast('업무 종료 시간 이후에는 배치할 수 없습니다.', 'danger');
                    return;
                  }
                  if (!confirm('종료 시간이 ' + minToTime(workEnd) + '을 초과합니다.\n' +
                    minToTime(workEnd) + '까지 ' + clampedMin + '분만 배치하고, 초과 ' + overflow + '분은 줄어든 시간으로 처리됩니다.\n계속하시겠습니까?')) {
                    return;
                  }
                  doCreate(startMin, workEnd, overflow, locOverride);
                } else {
                  doCreate(startMin, endMin, 0, locOverride);
                }
              }

              if (target.type === 'slot') {
                var t = App.snapToBlockEdge(target.el);
                clampAndCreate(t, bMin);
              } else if (target.type === 'month') {
                showMonthPlacePicker(locationId, function (result) {
                  if (!result) return;
                  var st = timeToMin(result.startTime);
                  clampAndCreate(st, bMin, result.locationId);
                });
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
                    selected.forEach(function (s) { totalMin += typeof s === 'object' ? (s.estimated_minutes || 0) : 0; });
                    totalMin = Math.max(totalMin, 1);
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
      var mins = typeof item === 'object' ? (item.estimated_minutes || 0) : 0;
      var isScheduled = !!scheduledSet[id];
      var checked = isScheduled ? '' : ' checked';
      var badge = isScheduled
        ? ' <span class="badge bg-secondary" style="font-size:0.65rem;vertical-align:middle">배치됨</span>'
        : '';
      var itemName = (typeof item === 'object' && item.name) ? item.name : '';
      var ownerStr = owners.length ? ' <span class="text-muted">작성: ' + owners.join(', ') + '</span>' : '';
      var nameStr = itemName ? ' <span class="text-muted" style="font-size:0.78rem">- ' + itemName + '</span>' : '';
      rows += '<label class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem' + (isScheduled ? ';opacity:0.55' : '') + '">' +
        '<input type="checkbox" class="form-check-input" value="' + i + '"' + checked + '> ' +
        '<span>' + id + '</span>' + nameStr + ownerStr +
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

    overlay.addEventListener('click', function (ev) { if (ev.target === overlay) { document.removeEventListener('keydown', onSpace); overlay.remove(); callback(null); } });
    document.getElementById('picker-close').addEventListener('click', function () { document.removeEventListener('keydown', onSpace); overlay.remove(); callback(null); });
    function onSpace(ev) {
      if (ev.key === ' ') {
        ev.preventDefault();
        document.getElementById('picker-ok').click();
      }
    }
    document.addEventListener('keydown', onSpace);
    document.getElementById('picker-ok').addEventListener('click', function () {
      document.removeEventListener('keydown', onSpace);
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
  // Month place picker — location + start time
  // =====================================================================
  function showMonthPlacePicker(defaultLocId, callback) {
    var locs = [];
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (b.dataset.locId) {
        var dot = b.querySelector('.loc-filter-dot');
        locs.push({
          id: b.dataset.locId,
          name: b.textContent.trim(),
          color: dot ? (dot.style.background || dot.style.backgroundColor || '#6c757d') : '#6c757d',
        });
      }
    });

    if (locs.length === 0) {
      api('GET', '/admin/api/locations').then(function (res) {
        var items = res.locations || res || [];
        items.forEach(function (loc) {
          locs.push({ id: loc.id, name: loc.name, color: loc.color || '#6c757d' });
        });
        showPicker(locs);
      }).catch(function () { callback(null); });
      return;
    }
    showPicker(locs);

    function showPicker(locations) {
      var old = document.getElementById('month-place-picker');
      if (old) old.remove();

      var locOptions = locations.map(function (loc) {
        var sel = loc.id === defaultLocId ? ' selected' : '';
        return '<option value="' + loc.id + '"' + sel + '>' + loc.name + '</option>';
      }).join('');

      var overlay = document.createElement('div');
      overlay.id = 'month-place-picker';
      overlay.className = 'block-detail-overlay';
      overlay.innerHTML =
        '<div class="bd-box" style="max-width:300px">' +
          '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">배치 설정</span></div>' +
            '<button class="bd-x" id="mpp-close">&times;</button></div>' +
          '<div class="bd-divider"></div>' +
          '<div style="padding:12px">' +
            '<label class="form-label" style="font-size:0.82rem">장소</label>' +
            '<select class="form-select form-select-sm mb-2" id="mpp-location">' +
              '<option value="">선택</option>' + locOptions +
            '</select>' +
            '<label class="form-label" style="font-size:0.82rem">시작 시간</label>' +
            '<input type="time" class="form-control form-control-sm mb-2" id="mpp-time" value="08:30">' +
            '<button class="btn btn-sm btn-primary w-100" id="mpp-ok">배치</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay) { overlay.remove(); callback(null); }
      });
      document.getElementById('mpp-close').addEventListener('click', function () {
        overlay.remove(); callback(null);
      });
      document.getElementById('mpp-ok').addEventListener('click', function () {
        var locId = document.getElementById('mpp-location').value;
        var time = document.getElementById('mpp-time').value;
        overlay.remove();
        if (!locId) { showToast('장소를 선택하세요.', 'danger'); callback(null); return; }
        if (!time) { showToast('시간을 입력하세요.', 'danger'); callback(null); return; }
        callback({ locationId: locId, startTime: time });
      });
    }
  }

  // =====================================================================
  // Location picker (legacy, kept for other uses)
  // =====================================================================
  function showLocationPicker(callback) {
    var locs = [];
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (b.dataset.locId) {
        var dot = b.querySelector('.loc-filter-dot');
        locs.push({
          id: b.dataset.locId,
          name: b.textContent.trim(),
          color: dot ? (dot.style.background || dot.style.backgroundColor || '#6c757d') : '#6c757d',
        });
      }
    });
    // Fallback: fetch from API if no filter buttons on page
    if (locs.length === 0) {
      api('GET', '/admin/api/locations').then(function (res) {
        var items = res.locations || res || [];
        items.forEach(function (loc) {
          locs.push({ id: loc.id, name: loc.name, color: loc.color || '#6c757d' });
        });
        showPicker(locs);
      }).catch(function () { callback(null); });
      return;
    }
    showPicker(locs);

    function showPicker(locations) {
      if (locations.length === 0) { callback(null); return; }
      var old = document.getElementById('location-picker');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'location-picker';
      overlay.className = 'block-detail-overlay';
      var rows = locations.map(function (loc) {
        return '<button class="btn btn-sm w-100 mb-1 text-start loc-pick-btn" data-loc-id="' + loc.id + '" style="border:2px solid ' + loc.color + ';color:' + loc.color + '">' +
          '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + loc.color + ';margin-right:6px"></span>' +
          loc.name + '</button>';
      }).join('');
      overlay.innerHTML =
        '<div class="bd-box" style="max-width:280px">' +
          '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">장소 선택</span></div>' +
            '<button class="bd-x" id="loc-pick-close">&times;</button></div>' +
          '<div class="bd-divider"></div>' +
          '<div style="padding:12px">' + rows + '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay) { overlay.remove(); callback(null); }
        var btn = ev.target.closest('.loc-pick-btn');
        if (btn) { overlay.remove(); callback(btn.dataset.locId); }
      });
      document.getElementById('loc-pick-close').addEventListener('click', function () {
        overlay.remove(); callback(null);
      });
    }
  }

  App.initQueueDrag = initQueueDrag;
  App.showIdentifierPicker = showIdentifierPicker;
  App.showLocationPicker = showLocationPicker;
})(window.ScheduleApp);
