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

  App.initQueueDrag = initQueueDrag;
  App.showIdentifierPicker = showIdentifierPicker;
})(window.ScheduleApp);
