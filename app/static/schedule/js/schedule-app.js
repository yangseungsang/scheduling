/**
 * Schedule app entry point — DOMContentLoaded initializer.
 * Calls all ScheduleApp.init* methods registered by other modules.
 */
(function() {
  'use strict';
  var App = window.ScheduleApp;

  function initAll() {
    if (window.GRID_INTERVAL) App.GRID_MINUTES = window.GRID_INTERVAL;
    App.initBlockMove();
    App.initMonthBlockMove();
    App.initQueueDrag();
    App.initResize();
    App.initContextMenu();
    App.initReturnToQueue();
    App.initQueueSearch();
    App.initQueueToggle();
    App.initTaskHoverLink();
    App.initBlockDetail();
    App.initWeekendToggle();
    App.initShiftSchedule();
    App.initAddButtons();
    App.initMonthMoreToggle();
  }

  App.initAll = initAll;
  document.addEventListener('DOMContentLoaded', initAll);
})();
