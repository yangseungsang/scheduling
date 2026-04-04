/**
 * Shared utility functions for the scheduling app.
 * Registered on window.ScheduleApp namespace.
 */
window.ScheduleApp = window.ScheduleApp || {};
(function (App) {
  'use strict';

  // =====================================================================
  // Constants
  // =====================================================================
  App.GRID_MINUTES = window.GRID_INTERVAL || 15;
  App.SLOT_HEIGHT = 24;

  // =====================================================================
  // Toast
  // =====================================================================
  function showToast(msg, type) {
    var c = document.getElementById('toast-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-container';
      c.className = 'position-fixed bottom-0 end-0 p-3';
      c.style.zIndex = '1100';
      document.body.appendChild(c);
    }
    var t = document.createElement('div');
    t.className = 'toast align-items-center text-bg-' + (type || 'info') + ' border-0 show';
    t.innerHTML = '<div class="d-flex"><div class="toast-body">' + msg +
      '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    c.appendChild(t);
    setTimeout(function () { t.remove(); }, 4000);
  }
  App.showToast = showToast;

  // =====================================================================
  // API
  // =====================================================================
  function api(method, url, data) {
    return fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error(j.error || '오류가 발생했습니다.');
        return j;
      });
    });
  }
  App.api = api;

  // =====================================================================
  // Remaining-hours check after placing a block
  // =====================================================================
  function getTaskRemaining(taskId) {
    return api('GET', '/tasks/api/' + taskId).then(function (res) {
      return res.task ? res.task.remaining_hours : 0;
    }).catch(function () { return 0; });
  }
  App.getTaskRemaining = getTaskRemaining;

  function checkRemainingAfterPlace(taskId, procedureId, prevRemaining) {
    return api('GET', '/tasks/api/' + taskId).then(function (res) {
      var task = res.task;
      if (!task) return false;
      var remaining = task.remaining_hours;
      // Only alert when remaining hours INCREASED (time was cut)
      if (remaining > 0 && remaining > (prevRemaining || 0)) {
        return showRemainingAlert(procedureId || task.procedure_id, remaining);
      }
      return false;
    }).catch(function () { return false; });
  }
  App.checkRemainingAfterPlace = checkRemainingAfterPlace;

  function showRemainingAlert(procedureId, remaining) {
    return new Promise(function (resolve) {
      var old = document.getElementById('remaining-alert');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'remaining-alert';
      overlay.className = 'remaining-alert-overlay';
      overlay.innerHTML =
        '<div class="remaining-alert-box">' +
          '<div class="remaining-alert-icon"><i class="bi bi-exclamation-triangle-fill"></i></div>' +
          '<div class="remaining-alert-title">시험이 당일에 완료되지 않습니다</div>' +
          '<div class="remaining-alert-body">' +
            '<strong>' + procedureId + '</strong> 항목의 잔여 시간 <strong>' + Math.round(remaining * 60) + '분</strong>이 ' +
            '시험 큐에 남아있습니다.<br>추가 일정 배치가 필요합니다.' +
          '</div>' +
          '<button class="remaining-alert-btn" id="remaining-alert-close">확인</button>' +
        '</div>';

      document.body.appendChild(overlay);

      function close() {
        overlay.remove();
        resolve(true);
      }
      document.getElementById('remaining-alert-close').addEventListener('click', close);
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) close();
      });
    });
  }
  App.showRemainingAlert = showRemainingAlert;

  // =====================================================================
  // Time helpers
  // =====================================================================
  function pad(n) { return String(n).padStart(2, '0'); }
  function timeToMin(t) { var p = t.split(':'); return +p[0] * 60 + +p[1]; }
  function minToTime(m) { return pad(Math.floor(m / 60)) + ':' + pad(m % 60); }
  function snapMin(m) { return Math.round(m / App.GRID_MINUTES) * App.GRID_MINUTES; }

  /** Calculate work minutes between start and end, excluding break periods. */
  function workMinutes(startMin, endMin) {
    var breaks = window.SCHEDULE_BREAKS || [];
    var breakMin = 0;
    for (var i = 0; i < breaks.length; i++) {
      var bs = timeToMin(breaks[i].start);
      var be = timeToMin(breaks[i].end);
      var ovStart = Math.max(startMin, bs);
      var ovEnd = Math.min(endMin, be);
      if (ovStart < ovEnd) breakMin += ovEnd - ovStart;
    }
    return Math.max(0, endMin - startMin - breakMin);
  }

  App.pad = pad;
  App.timeToMin = timeToMin;
  App.minToTime = minToTime;
  App.snapMin = snapMin;
  App.workMinutes = workMinutes;

  // =====================================================================
  // Readonly check
  // =====================================================================
  function isReadonly() {
    return document.body.classList.contains('readonly-mode');
  }
  App.isReadonly = isReadonly;

})(window.ScheduleApp);
