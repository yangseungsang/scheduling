/**
 * 블록 리사이즈 모듈 — 상단/하단 핸들을 드래그하여 블록 크기를 변경한다.
 * 리사이즈 시 시간만 줄어들며 새 블록은 생성되지 않는다.
 */
(function (App) {
  'use strict';

  // utils.js에서 가져온 단축 참조
  var api = App.api;
  var showToast = App.showToast;
  var showConfirmModal = App.showConfirmModal;
  var isReadonly = App.isReadonly;
  var timeToMin = App.timeToMin;
  var minToTime = App.minToTime;
  var workMinutes = App.workMinutes;
  // GRID_MINUTES는 App.GRID_MINUTES를 직접 참조 (initAll에서 갱신되므로 캡처하지 않음)
  var SLOT_HEIGHT = App.SLOT_HEIGHT;

  // =====================================================================
  // 3. 블록 리사이즈
  // =====================================================================
  /**
   * 모든 리사이즈 핸들(.resize-handle)에 드래그 이벤트를 등록한다.
   * 상단 핸들: 시작 시간 변경, 하단 핸들: 종료 시간 변경.
   * SLOT_HEIGHT 단위(=GRID_MINUTES)로 스냅하여 리사이즈한다.
   */
  function initResize() {
    document.querySelectorAll('.resize-handle').forEach(function (handle) {
      handle.addEventListener('mousedown', function (e) {
        if (isReadonly()) return;
        e.preventDefault();
        e.stopPropagation(); // 블록 이동 이벤트 전파 방지

        var block = handle.closest('.schedule-block');
        if (!block) return;

        // 상단 핸들인지 하단 핸들인지 판별
        var isTop = handle.classList.contains('resize-handle-top');
        var blockId = block.dataset.blockId;
        // 리사이즈 시작 시점의 위치/크기 저장 (복원용)
        var origTop = parseInt(block.style.top, 10);
        var origHeight = parseInt(block.style.height, 10);
        var startY = e.clientY;

        block.classList.add('resizing'); // 리사이즈 중 시각적 표시

        /**
         * 마우스 이동 핸들러 — 드래그 양만큼 블록 크기를 실시간 조정
         * @param {MouseEvent} ev
         */
        function onMove(ev) {
          ev.preventDefault();
          var delta = ev.clientY - startY;
          // SLOT_HEIGHT 단위로 스냅
          var snapped = Math.round(delta / SLOT_HEIGHT) * SLOT_HEIGHT;

          if (isTop) {
            // 상단 핸들: top 위치와 높이를 동시에 변경
            var newTop = origTop + snapped;
            var newH = origHeight - snapped;
            // 최소 높이(1슬롯) 및 상단 경계 확인
            if (newH >= SLOT_HEIGHT && newTop >= 0) {
              block.style.top = newTop + 'px';
              block.style.height = newH + 'px';
            }
          } else {
            // 하단 핸들: 높이만 변경
            var newH2 = origHeight + snapped;
            if (newH2 >= SLOT_HEIGHT) {
              block.style.height = newH2 + 'px';
            }
          }
        }

        /**
         * 마우스 업 핸들러 — 리사이즈 종료 후 서버에 변경사항 전송
         */
        function onUp() {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          block.classList.remove('resizing');

          // 최종 위치/크기에서 시간 역산
          var finalTop = parseInt(block.style.top, 10);
          var finalH = parseInt(block.style.height, 10);

          // 첫 번째 시간 슬롯의 시간 = 업무 시작 시간
          var firstSlot = document.querySelector('.time-slot[data-time]');
          var wsMin = firstSlot ? timeToMin(firstSlot.dataset.time) : 540; // 기본 09:00
          // 픽셀 위치 → 슬롯 수 → 시간(분)으로 변환
          var slotFromTop = Math.round(finalTop / SLOT_HEIGHT);
          var slotCount = Math.round(finalH / SLOT_HEIGHT);
          var newStartMin = wsMin + slotFromTop * App.GRID_MINUTES;
          var durMin = slotCount * App.GRID_MINUTES;

          var newStart = minToTime(newStartMin);
          var newEnd = minToTime(newStartMin + durMin);

          // 시간이 실제로 변경된 경우에만 서버 요청
          if (newStart !== block.dataset.startTime || newEnd !== block.dataset.endTime) {
            var taskId = block.dataset.taskId;
            var blockTitle = (block.querySelector('.block-title') || {}).textContent || '';
            var origStartMin = timeToMin(block.dataset.startTime);
            var origEndMin = timeToMin(block.dataset.endTime);
            var prevWorkMin = workMinutes(origStartMin, origEndMin);
            var newWorkMin = workMinutes(newStartMin, newStartMin + durMin);

            /** 서버에 리사이즈 결과를 전송하는 함수 */
            function doResize() {
              api('PUT', '/schedule/api/blocks/' + blockId, {
                start_time: newStart,
                end_time: newEnd,
                resize: true, // 서버에 리사이즈 동작임을 알림
              }).then(function () { return App.softReload(); })
                .catch(function (err) {
                  showToast(err.message, 'danger');
                  // 오류 시 원래 위치/크기로 복원
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
