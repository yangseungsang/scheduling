/**
 * Schedule app entry point — DOMContentLoaded initializer.
 * Calls all ScheduleApp.init* methods registered by other modules.
 */
(function() {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    var App = window.ScheduleApp;
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
  });
})();
