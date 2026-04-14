/**
 * 스케줄 앱 진입점 — DOMContentLoaded 시 모든 모듈을 초기화한다.
 * 각 모듈(block-move, queue-drag, block-resize 등)에서 등록한
 * ScheduleApp.init* 메서드를 순서대로 호출한다.
 */
(function() {
  'use strict';
  var App = window.ScheduleApp;

  /**
   * 모든 스케줄 기능 모듈을 초기화한다.
   * 페이지 최초 로드(DOMContentLoaded) 및 소프트 리로드(softReload) 후에 호출된다.
   * 그리드 간격 설정을 반영하고, 각 모듈의 init 함수를 실행한다.
   */
  function initAll() {
    // 서버에서 전달된 그리드 간격 설정 반영
    if (window.GRID_INTERVAL) App.GRID_MINUTES = window.GRID_INTERVAL;
    // 각 모듈 초기화 (이벤트 핸들러 등록)
    App.initBlockMove();        // 일간/주간뷰 블록 이동
    App.initMonthBlockMove();   // 월간뷰 블록 이동
    App.initQueueDrag();        // 큐 → 캘린더 드래그 배치
    App.initResize();           // 블록 리사이즈
    App.initContextMenu();      // 우클릭 컨텍스트 메뉴
    App.initReturnToQueue();    // 큐 복귀 버튼
    App.initQueueSearch();      // 큐 검색 + 정렬
    App.initQueueToggle();      // 큐 접기/펼치기
    App.initTaskHoverLink();    // 동일 태스크 호버 하이라이트
    App.initBlockDetail();      // 블록 상세 팝업 (더블클릭)
    App.initWeekendToggle();    // 주말 표시 토글
    App.initShiftSchedule();    // 일정 일괄 이동
    App.initAddButtons();       // 태스크/블록 추가 버튼
    App.initMonthMoreToggle();  // 월간뷰 더보기 토글
    App.initBatchPlace();       // 큐 일괄 배치 (체크박스)
  }

  App.initAll = initAll;
  // DOM 로드 완료 시 초기화 실행
  document.addEventListener('DOMContentLoaded', initAll);
})();
