/**
 * Block resize — top/bottom handles.
 */
(function (App) {
  'use strict';

  var api = App.api;
  var showToast = App.showToast;
  var showConfirmModal = App.showConfirmModal;
  var isReadonly = App.isReadonly;
  var timeToMin = App.timeToMin;
  var minToTime = App.minToTime;
  var workMinutes = App.workMinutes;
  var GRID_MINUTES = App.GRID_MINUTES;
  var SLOT_HEIGHT = App.SLOT_HEIGHT;

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
              }).then(function () { return App.softReload(); })
                .catch(function (err) {
                  showToast(err.message, 'danger');
                  block.style.top = origTop + 'px';
                  block.style.height = origHeight + 'px';
                });
            }

            doResize();
          }
        }

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });
    });
  }

  App.initResize = initResize;
})(window.ScheduleApp);
