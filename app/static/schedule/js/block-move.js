/**
 * 블록 이동 모듈 — 일간/주간/월간 뷰에서의 스케줄 블록 드래그 이동을 처리한다.
 * 블록을 다른 시간/날짜/장소로 이동하거나, 큐로 되돌리는 기능을 제공한다.
 */
(function (App) {
  'use strict';

  // utils.js, drag-core.js에서 가져온 단축 참조
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
  // GRID_MINUTES는 App.GRID_MINUTES를 직접 참조 (initAll에서 갱신되므로 캡처하지 않음)
  var SLOT_HEIGHT = App.SLOT_HEIGHT;

  // =====================================================================
  // 1. 일간/주간뷰 블록 이동
  // =====================================================================
  /**
   * 일간/주간뷰의 스케줄 블록에 마우스 드래그 이벤트를 등록한다.
   * 블록을 다른 시간 슬롯, 월간 셀, 또는 큐로 이동할 수 있다.
   */
  function initBlockMove() {
    // Ctrl+클릭으로 블록 다중 선택
    document.querySelectorAll('.schedule-block[data-block-id]').forEach(function (block) {
      block.addEventListener('click', function (e) {
        if (!e.ctrlKey && !e.metaKey) return; // Ctrl/Cmd 없으면 무시
        e.preventDefault();
        e.stopPropagation();
        block.classList.toggle('block-selected');
      });
    });

    document.querySelectorAll('.schedule-block[data-block-id]').forEach(function (block) {
      block.addEventListener('mousedown', function (e) {
        // 리사이즈 핸들 클릭 시에는 이동 처리하지 않음
        if (e.target.closest('.resize-handle')) return;
        // Ctrl+클릭은 선택 모드이므로 드래그 하지 않음
        if (e.ctrlKey || e.metaKey) return;

        var blockId = block.dataset.blockId;
        var taskId = block.dataset.taskId;
        var title = (block.querySelector('.block-title') || {}).textContent || '';
        var color = block.style.backgroundColor || '#0d6efd';
        var startTime = block.dataset.startTime;
        var endTime = block.dataset.endTime;
        // 휴식 시간 제외한 실제 업무 시간 계산
        var durationMin = workMinutes(timeToMin(startTime), timeToMin(endTime));
        // 고스트 높이: 순수 작업 시간 기준 (adjustedDuration이 휴식 추가)
        var ghostH = (durationMin / App.GRID_MINUTES) * SLOT_HEIGHT;

        // 다중 선택된 블록 수집 (현재 드래그 블록 포함)
        var selectedBlocks = Array.from(document.querySelectorAll('.schedule-block.block-selected'));
        var isMulti = selectedBlocks.length > 0 && (block.classList.contains('block-selected') || selectedBlocks.length > 0);
        if (isMulti && !block.classList.contains('block-selected')) {
          // 드래그 대상이 선택 안 된 블록이면 단일 드래그
          isMulti = false;
        }

        startDrag(e, {
          sourceEl: block,
          ghostText: isMulti ? title + ' 외 ' + (selectedBlocks.length - 1) + '건' : title,
          ghostColor: color,
          ghostWidth: block.offsetWidth,
          ghostHeight: ghostH,
          onDrop: function (target) {
            if (target.type === 'queue') {
              if (isMulti) {
                // 다중 선택 블록 일괄 큐로 보내기
                var chain = Promise.resolve();
                selectedBlocks.forEach(function (sb) {
                  chain = chain.then(function () {
                    return api('DELETE', '/schedule/api/blocks/' + sb.dataset.blockId + '?restore=1');
                  });
                });
                chain.then(function () { softReload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              } else {
                api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
                  .then(function () { softReload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              }
            } else if (target.type === 'slot') {
              var t = App.snapToBlockEdge(target.el);
              if (isMulti) {
                // 다중 선택 블록 순차 이동 (이어 배치)
                var curMin = t;
                var chain = Promise.resolve();
                selectedBlocks.forEach(function (sb) {
                  chain = chain.then(function () {
                    var dur = workMinutes(timeToMin(sb.dataset.startTime), timeToMin(sb.dataset.endTime));
                    var moveUpdate = {
                      date: target.date,
                      start_time: minToTime(curMin),
                      end_time: minToTime(curMin + dur),
                    };
                    if (target.locationId) moveUpdate.location_id = target.locationId;
                    curMin += dur;
                    return api('PUT', '/schedule/api/blocks/' + sb.dataset.blockId, moveUpdate);
                  });
                });
                chain.then(function () { softReload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              } else {
                var moveUpdate = {
                  date: target.date,
                  start_time: minToTime(t),
                  end_time: minToTime(t + durationMin),
                };
                if (target.locationId) moveUpdate.location_id = target.locationId;
                api('PUT', '/schedule/api/blocks/' + blockId, moveUpdate)
                  .then(function () { softReload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              }
            } else if (target.type === 'month') {
              if (isMulti) {
                var chain = Promise.resolve();
                selectedBlocks.forEach(function (sb) {
                  chain = chain.then(function () {
                    return api('PUT', '/schedule/api/blocks/' + sb.dataset.blockId, { date: target.date });
                  });
                });
                chain.then(function () { softReload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              } else {
                api('PUT', '/schedule/api/blocks/' + blockId, { date: target.date })
                  .then(function () { softReload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              }
            }
          },
        });
      });
    });
  }

  // =====================================================================
  // 2b. 월간뷰 블록 이동
  // =====================================================================
  /**
   * 월간뷰의 블록 아이템에 마우스 드래그 이벤트를 등록한다.
   * 다른 날짜 셀 또는 큐로 이동할 수 있다.
   * 이동 후 잔여 시간이 증가하면 경고 알림을 표시한다.
   */
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
              // 큐로 되돌리기
              api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
                .then(function () { softReload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            } else if (target.type === 'month') {
              var prevRem;
              // 이동 전 잔여 시간 저장 → 이동 → 잔여 시간 비교
              (taskId ? getTaskRemaining(taskId) : Promise.resolve(0)).then(function (r) {
                prevRem = r;
                return api('PUT', '/schedule/api/blocks/' + blockId, {
                  date: target.date,
                });
              }).then(function () {
                // 잔여 시간이 증가했으면 경고 표시
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
