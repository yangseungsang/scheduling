/**
 * Miscellaneous schedule features: return-to-queue, queue search/toggle,
 * task hover link, weekend toggle, shift schedule, add buttons.
 * Extracted from drag_drop.js
 */
(function () {
  'use strict';

  var App = window.ScheduleApp || {};

  var showToast = App.showToast;
  var api = App.api;
  var isReadonly = App.isReadonly;

  // =====================================================================
  // Return-to-queue buttons
  // =====================================================================
  function initReturnToQueue() {
    document.querySelectorAll('.btn-to-queue[data-block-id]').forEach(function (btn) {
      btn.addEventListener('mousedown', function (e) {
        e.stopPropagation();
      });
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        e.preventDefault();
        if (isReadonly()) return;
        var blockId = btn.dataset.blockId;
        api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
          .then(function () {
            showToast('큐로 되돌렸습니다.', 'success');
            location.reload();
          })
          .catch(function (err) { showToast(err.message, 'danger'); });
      });
    });
  }

  // =====================================================================
  // Queue search + alphabetical sort
  // =====================================================================
  function initQueueSearch() {
    var body = document.getElementById('task-queue-body');
    var input = document.getElementById('queue-search');
    if (!body || !input) return;

    // Initial sort: alphabetical by procedure_id
    function sortItems() {
      var items = Array.from(body.querySelectorAll('.queue-task-item'));
      items.sort(function (a, b) {
        return (a.dataset.title || '').localeCompare(b.dataset.title || '');
      });
      items.forEach(function (item) { body.appendChild(item); });
    }
    sortItems();

    // Search filter
    input.addEventListener('input', function () {
      var query = input.value.trim().toLowerCase();
      body.querySelectorAll('.queue-task-item').forEach(function (item) {
        var id = (item.dataset.title || '').toLowerCase();
        var section = (item.querySelector('.queue-card-section') || {}).textContent || '';
        section = section.toLowerCase();
        var match = !query || id.indexOf(query) !== -1 || section.indexOf(query) !== -1;
        item.style.display = match ? '' : 'none';
      });
    });
  }

  // =====================================================================
  // Queue toggle
  // =====================================================================
  function initQueueToggle() {
    var btn = document.getElementById('toggle-queue');
    var q = document.getElementById('task-queue');
    if (btn && q) btn.onclick = function () { q.classList.toggle('collapsed'); };
  }

  // =====================================================================
  // Same-task hover highlight
  // =====================================================================
  function initTaskHoverLink() {
    var allItems = document.querySelectorAll('[data-task-id]');
    if (!allItems.length) return;

    allItems.forEach(function (el) {
      el.addEventListener('mouseenter', function () {
        var taskId = el.dataset.taskId;
        if (!taskId) return;
        document.querySelectorAll('[data-task-id="' + taskId + '"]').forEach(function (item) {
          item.classList.add('task-linked-hover');
        });
      });
      el.addEventListener('mouseleave', function () {
        document.querySelectorAll('.task-linked-hover').forEach(function (item) {
          item.classList.remove('task-linked-hover');
        });
      });
    });
  }

  // =====================================================================
  // Weekend toggle
  // =====================================================================
  function initWeekendToggle() {
    var btn = document.getElementById('btn-toggle-weekends');
    if (!btn) return;
    var hidden = localStorage.getItem('hideWeekends') === '1';
    function applyWeekendVisibility() {
      // Week view
      document.querySelectorAll('.week-day-col[data-weekday="5"], .week-day-col[data-weekday="6"]').forEach(function (col) {
        col.style.display = hidden ? 'none' : '';
      });
      // Month view
      document.querySelectorAll('th[data-weekday="5"], th[data-weekday="6"]').forEach(function (th) {
        th.style.display = hidden ? 'none' : '';
      });
      document.querySelectorAll('.month-table tbody tr').forEach(function (row) {
        var cells = row.querySelectorAll('td');
        if (cells.length >= 7) {
          cells[5].style.display = hidden ? 'none' : '';
          cells[6].style.display = hidden ? 'none' : '';
        }
      });
      btn.classList.toggle('active', hidden);
    }
    applyWeekendVisibility();
    btn.addEventListener('click', function () {
      hidden = !hidden;
      localStorage.setItem('hideWeekends', hidden ? '1' : '0');
      applyWeekendVisibility();
    });
  }

  // =====================================================================
  // Schedule shift (bulk date move)
  // =====================================================================
  function initShiftSchedule() {
    var btn = document.getElementById('btn-shift-schedule');
    if (!btn) return;
    btn.addEventListener('click', function () {
      if (isReadonly()) return;
      var old = document.getElementById('shift-schedule-popup');
      if (old) old.remove();

      var today = new Date().toISOString().slice(0, 10);
      var overlay = document.createElement('div');
      overlay.id = 'shift-schedule-popup';
      overlay.className = 'block-detail-overlay';
      overlay.innerHTML =
        '<div class="bd-box" style="max-width:360px">' +
          '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">일정 이동</span></div>' +
            '<button class="bd-x" id="shift-close">&times;</button></div>' +
          '<div class="bd-divider"></div>' +
          '<div style="padding:12px">' +
            '<label class="form-label">기준 날짜 (이 날짜 이후 전체 이동)</label>' +
            '<input type="date" class="form-control form-control-sm mb-2" id="shift-from-date" value="' + today + '">' +
            '<label class="form-label">방향</label>' +
            '<select class="form-select form-select-sm mb-2" id="shift-direction">' +
              '<option value="1">+1일 (뒤로 밀기)</option>' +
              '<option value="-1">-1일 (앞으로 당기기)</option>' +
            '</select>' +
            '<div class="form-text mb-2">주말은 자동으로 건너뜁니다.</div>' +
            '<button class="btn btn-sm btn-primary w-100" id="shift-ok">이동 실행</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function (ev) { if (ev.target === overlay) overlay.remove(); });
      document.getElementById('shift-close').addEventListener('click', function () { overlay.remove(); });
      document.getElementById('shift-ok').addEventListener('click', function () {
        var fromDate = document.getElementById('shift-from-date').value;
        var direction = parseInt(document.getElementById('shift-direction').value);
        if (!fromDate) { showToast('날짜를 입력하세요.', 'danger'); return; }
        overlay.remove();
        api('POST', '/schedule/api/blocks/shift', {
          from_date: fromDate, direction: direction
        }).then(function (r) {
          showToast(r.shifted_count + '개 블록 이동 완료', 'success');
          setTimeout(function () { location.reload(); }, 500);
        }).catch(function (err) { showToast(err.message, 'danger'); });
      });
    });
  }

  // =====================================================================
  // Add task / Add simple block
  // =====================================================================
  function initAddButtons() {
    var taskBtn = document.getElementById('btn-add-task');
    if (taskBtn) {
      taskBtn.addEventListener('click', function () {
        window.location.href = '/tasks/new';
      });
    }

    var blockBtn = document.getElementById('btn-add-simple-block');
    if (!blockBtn) return;
    blockBtn.addEventListener('click', function () {
      if (isReadonly()) return;
      var old = document.getElementById('simple-block-popup');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'simple-block-popup';
      overlay.className = 'block-detail-overlay';
      overlay.innerHTML =
        '<div class="bd-box" style="max-width:340px">' +
          '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">블록 추가</span></div>' +
            '<button class="bd-x" id="simple-close">&times;</button></div>' +
          '<div class="bd-divider"></div>' +
          '<div style="padding:12px">' +
            '<label class="form-label">제목</label>' +
            '<input type="text" class="form-control form-control-sm mb-2" id="simple-title" placeholder="예: 시험 준비, 장비 점검">' +
            '<label class="form-label">예상 시간 (분)</label>' +
            '<input type="number" class="form-control form-control-sm mb-2" id="simple-minutes" value="60" min="1" step="1">' +
            '<div class="form-text mb-2">큐에 추가 후 드래그하여 배치하세요.</div>' +
            '<button class="btn btn-sm btn-primary w-100" id="simple-ok">큐에 추가</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function (ev) { if (ev.target === overlay) overlay.remove(); });
      document.getElementById('simple-close').addEventListener('click', function () { overlay.remove(); });
      document.getElementById('simple-ok').addEventListener('click', function () {
        var title = document.getElementById('simple-title').value.trim();
        var minutes = parseInt(document.getElementById('simple-minutes').value) || 60;
        if (!title) { showToast('제목을 입력하세요.', 'danger'); return; }
        overlay.remove();
        api('POST', '/schedule/api/simple-blocks', {
          title: title, estimated_minutes: minutes,
        }).then(function () {
          showToast('큐에 추가되었습니다.', 'success');
          setTimeout(function () { location.reload(); }, 300);
        }).catch(function (err) { showToast(err.message, 'danger'); });
      });
    });
  }

  // Register on App namespace
  App.initReturnToQueue = initReturnToQueue;
  App.initQueueSearch = initQueueSearch;
  App.initQueueToggle = initQueueToggle;
  App.initTaskHoverLink = initTaskHoverLink;
  // =====================================================================
  // Month "more" toggle
  // =====================================================================
  function initMonthMoreToggle() {
    document.querySelectorAll('.month-more-toggle').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.stopPropagation();
        var cell = el.closest('.month-day-cell');
        if (!cell) return;
        var expanded = cell.classList.toggle('expanded');
        if (expanded) {
          el.textContent = '접기';
        } else {
          var hidden = cell.querySelectorAll('.month-block-hidden').length;
          el.textContent = '+' + hidden + '개 더';
        }
      });
    });
  }

  App.initWeekendToggle = initWeekendToggle;
  App.initShiftSchedule = initShiftSchedule;
  App.initAddButtons = initAddButtons;
  App.initMonthMoreToggle = initMonthMoreToggle;
  window.ScheduleApp = App;
})();
