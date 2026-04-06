/**
 * Block move — day/week/month views.
 */
(function (App) {
  'use strict';

  var startDrag = App.startDrag;
  var api = App.api;
  var showToast = App.showToast;
  var getTaskRemaining = App.getTaskRemaining;
  var checkRemainingAfterPlace = App.checkRemainingAfterPlace;
  var softReload = function () { return App.softReload(); };
  var timeToMin = App.timeToMin;
  var minToTime = App.minToTime;
  var workMinutes = App.workMinutes;
  var snapMin = App.snapMin;
  var GRID_MINUTES = App.GRID_MINUTES;
  var SLOT_HEIGHT = App.SLOT_HEIGHT;

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
        var ghostH = block.offsetHeight || (durationMin / GRID_MINUTES) * SLOT_HEIGHT;

        startDrag(e, {
          sourceEl: block,
          ghostText: title,
          ghostColor: color,
          ghostWidth: block.offsetWidth,
          ghostHeight: ghostH,
          onDrop: function (target) {
            if (target.type === 'queue') {
              api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
                .then(function () { softReload(); })
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
                softReload();
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
                softReload();
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
                .then(function () { softReload(); })
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
              }).then(function () { softReload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            }
          },
        });
      });
    });
  }

  App.initBlockMove = initBlockMove;
  App.initMonthBlockMove = initMonthBlockMove;
})(window.ScheduleApp);
