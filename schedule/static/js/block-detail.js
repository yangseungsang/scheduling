/**
 * Block detail popup (double-click).
 * Extracted from drag_drop.js
 */
(function () {
  'use strict';

  var App = window.ScheduleApp || {};

  var showToast = App.showToast;
  var api = App.api;
  var isReadonly = App.isReadonly;

  // =====================================================================
  // Block detail popup
  // =====================================================================
  function hrsToMin(h) { return Math.round(h * 60); }

  function showTaskDetailPopup(taskId, opts) {
    opts = opts || {};
    var blockId = opts.blockId || null;
    Promise.all([
      api('GET', '/tasks/api/' + taskId),
      api('GET', '/schedule/api/blocks/by-task/' + taskId).catch(function() { return {blocks: []}; }),
    ]).then(function (results) {
      var task = results[0] && results[0].task;
      var allBlocks = (results[1] && results[1].blocks) || [];
      if (!task) { showToast('항목 정보를 불러올 수 없습니다.', 'danger'); return; }

      var startTime = opts.startTime || '';
      var endTime = opts.endTime || '';
      var locationName = task.location_name || opts.locationName || '';
      var assigneeName = (task.assignee_names && task.assignee_names.length)
        ? task.assignee_names.join(', ')
        : (opts.assigneeName || '-');
      var memo = task.memo || opts.memo || '';
      var status = opts.blockStatus || 'pending';
      var statusLabel = { pending: '대기', in_progress: '진행', completed: '완료', cancelled: '불가' }[status] || status;
      var blockColor = opts.color || '#64748b';
      var isQueued = opts.isQueued || false;

      var blockIdentifierIds = opts.identifierIds || null;
      var blockIdSet = {};
      if (blockIdentifierIds) {
        blockIdentifierIds.forEach(function(id) { blockIdSet[id] = true; });
      }
      var isSplit = blockIdentifierIds && (task.test_list || []).length > blockIdentifierIds.length;

      // Build identifier -> schedule mapping from allBlocks
      var allTestList = task.test_list || [];
      var allTaskIds = allTestList.map(function(it) { return typeof it === 'object' ? it.id : it; });
      var idScheduleMap = {};  // id → {time, status}
      allBlocks.sort(function(a,b) { return (a.date + a.start_time).localeCompare(b.date + b.start_time); });
      allBlocks.forEach(function(blk) {
        var bids = blk.identifier_ids || allTaskIds;
        bids.forEach(function(iid) {
          if (!idScheduleMap[iid]) {
            idScheduleMap[iid] = {
              time: blk.date + ' ' + blk.start_time + '–' + blk.end_time,
              date: blk.date,
              status: blk.block_status || 'pending',
            };
          }
        });
      });

      var testListHtml = '-';
      var idTotalMin = 0;
      if (allTestList.length) {
        testListHtml = '<table style="width:100%;font-size:0.78rem;border-collapse:collapse;border-spacing:0">' +
          '<colgroup><col style="width:20%"><col style="width:15%"><col style="width:30%"><col style="width:35%"></colgroup>' +
          '<tr style="color:#9ca3af;font-size:0.68rem;border-bottom:1px solid #f3f4f6">' +
            '<td style="padding:3px 4px">식별자</td><td style="padding:3px 4px">시간</td>' +
            '<td style="padding:3px 4px">작성자</td><td style="padding:3px 4px">배치</td></tr>' +
          allTestList.map(function(item) {
            if (typeof item === 'object' && item.id) {
              var mins = Math.round((item.estimated_hours || 0) * 60);
              idTotalMin += mins;
              var ow = (item.owners || []).join(', ') || '-';
              var inThisBlock = !isSplit || blockIdSet[item.id];
              var sched = idScheduleMap[item.id];
              var schedHtml;
              if (sched) {
                var statusColors = {completed:'#16a34a', in_progress:'#2563eb', cancelled:'#dc2626', pending:'#6c757d'};
                var statusLabels = {completed:'완료', in_progress:'진행', cancelled:'불가', pending:'대기'};
                var sColor = statusColors[sched.status] || '#6c757d';
                var sLabel = statusLabels[sched.status] || '';
                var statusBadge = sched.status !== 'pending'
                  ? ' <span style="font-size:0.6rem;font-weight:700;color:' + sColor + '">' + sLabel + '</span>'
                  : '';
                schedHtml = '<a href="/schedule/?date=' + sched.date + '" style="color:#2563eb;text-decoration:none;font-size:0.72rem;white-space:nowrap">' + sched.time + '</a>' + statusBadge;
              } else {
                schedHtml = '<span style="color:#adb5bd">미배치</span>';
              }
              var rowStyle = inThisBlock
                ? 'border-bottom:1px solid #f9fafb'
                : 'border-bottom:1px solid #f9fafb;opacity:0.45';
              var marker = inThisBlock ? '' : ' <span style="font-size:0.6rem;color:#9ca3af">타 블록</span>';
              return '<tr style="' + rowStyle + '">' +
                '<td style="padding:3px 4px;font-weight:600;white-space:nowrap">' + item.id + marker + '</td>' +
                '<td style="padding:3px 4px;white-space:nowrap">' + mins + '분</td>' +
                '<td style="padding:3px 4px;color:#6c757d">' + ow + '</td>' +
                '<td style="padding:3px 4px">' + schedHtml + '</td></tr>';
            }
            return '<tr><td colspan="4" style="padding:3px 4px">' + item + '</td></tr>';
          }).join('') +
          '<tr style="border-top:1px solid #e5e7eb">' +
            '<td style="padding:4px;font-weight:700">합계</td>' +
            '<td style="padding:4px;font-weight:700">' + idTotalMin + '분</td>' +
            '<td colspan="2"></td></tr>' +
          '</table>';
      }
      var splitInfo = '';
      var totalIdCount = (task.test_list || []).length;
      if (blockIdentifierIds && blockIdentifierIds.length < totalIdCount) {
        splitInfo = ' <span style="font-size:0.75rem;color:#6c757d">(분할 ' + blockIdentifierIds.length + '/' + totalIdCount + ')</span>';
      }

      var old = document.getElementById('block-detail-popup');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'block-detail-popup';
      overlay.className = 'block-detail-overlay';

      var statusBadge = isQueued
        ? '<span class="bd-badge bd-badge-queued">미배치</span>'
        : '<span class="bd-badge bd-badge-' + status + '">' + statusLabel + '</span>';

      var escapedMemo = memo.replace(/"/g, '&quot;').replace(/</g, '&lt;');

      var taskStatus = task.status || 'waiting';
      var taskStatusLabel = { waiting: '대기', in_progress: '진행 중', completed: '완료' }[taskStatus] || taskStatus;

      var html =
        '<div class="bd-box">' +
          '<div class="bd-header">' +
            '<div class="bd-header-left">' +
              '<span class="bd-id">' + (task.section_name || '') + '</span>' +
              statusBadge +
            '</div>' +
            '<button class="bd-x" id="block-detail-close">&times;</button>' +
          '</div>' +
          '<div class="bd-divider"></div>' +
          '<table class="bd-tbl">' +
            '<tr><td class="bd-k">시험 식별자' + splitInfo + '</td><td class="bd-v">' + testListHtml + '</td></tr>' +
            '<tr><td class="bd-k">예상 시간</td><td class="bd-v bd-v-edit">' +
              '<input type="number" class="bd-input" id="bd-est-min" value="' + hrsToMin(task.estimated_hours) + '" min="0" step="1">분' +
              ' <span class="bd-sub">(기준 ' + idTotalMin + '분 / 잔여 ' + hrsToMin(task.remaining_hours) + '분)</span>' +
            '</td></tr>' +
            '<tr><td class="bd-k">시험장소</td><td class="bd-v">' + (locationName || '-') + '</td></tr>' +
            (startTime ? '<tr><td class="bd-k">배치 시간</td><td class="bd-v">' + startTime + ' – ' + endTime + '</td></tr>' : '') +
            '<tr><td class="bd-k">시험 담당자</td><td class="bd-v">' + (assigneeName || '-') + '</td></tr>' +
            '<tr><td class="bd-k">버전</td><td class="bd-v">' + (task.version_name || '-') + '</td></tr>' +
            '<tr><td class="bd-k">상태</td><td class="bd-v">' + taskStatusLabel + '</td></tr>' +
            '<tr><td class="bd-k">메모</td><td class="bd-v">' +
              '<textarea class="bd-textarea" id="bd-memo" rows="2" placeholder="메모 입력...">' + escapedMemo + '</textarea>' +
            '</td></tr>' +
          '</table>' +
          '<div class="bd-foot">' +
            '<a href="/tasks/' + taskId + '/edit">수정 페이지 &rarr;</a>' +
            '<button class="bd-save" id="bd-save">저장</button>' +
          '</div>' +
        '</div>';

      overlay.innerHTML = html;
      document.body.appendChild(overlay);

      document.getElementById('block-detail-close').addEventListener('click', function () {
        overlay.remove();
      });
      overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay) overlay.remove();
      });

      document.getElementById('bd-save').addEventListener('click', function () {
        var newMemo = document.getElementById('bd-memo').value;
        var newEstMin = parseInt(document.getElementById('bd-est-min').value, 10) || 0;
        var newEstHours = newEstMin / 60.0;
        var updates = { memo: newMemo };
        var durationChanged = newEstHours !== task.estimated_hours;
        if (durationChanged) {
          updates.estimated_hours = newEstHours;
          updates.remaining_hours = Math.max(0, newEstHours - (task.estimated_hours - task.remaining_hours));
        }
        // Update task only — block position/size is unchanged
        api('PUT', '/tasks/api/' + taskId + '/update', Object.assign({}, task, updates))
          .then(function () {
            showToast('저장되었습니다.', 'success');
            overlay.remove();
            setTimeout(function () { location.reload(); }, 300);
          })
          .catch(function (err) { showToast(err.message, 'danger'); });
      });
    }).catch(function (err) { showToast(err.message || '팝업 로드 실패', 'danger'); });
  }

  function initBlockDetail() {
    // Schedule blocks + month blocks
    document.querySelectorAll('.schedule-block[data-block-id], .month-block-item[data-block-id]').forEach(function (block) {
      block.addEventListener('dblclick', function (e) {
        e.preventDefault();
        e.stopPropagation();

        var taskId = block.dataset.taskId;
        if (!taskId || taskId === 'None') return;
        var idIds = null;
        try { if (block.dataset.identifierIds) idIds = JSON.parse(block.dataset.identifierIds); } catch(ex) {}
        showTaskDetailPopup(taskId, {
          blockId: block.dataset.blockId || null,
          startTime: block.dataset.startTime || '',
          endTime: block.dataset.endTime || '',
          locationName: block.dataset.locationName || '',
          assigneeName: block.dataset.assigneeName || '',
          memo: block.dataset.memo || '',
          blockStatus: block.dataset.blockStatus || 'pending',
          color: block.style.backgroundColor || '#64748b',
          identifierIds: idIds,
        });
      });
    });

    // Queue items
    document.querySelectorAll('.queue-task-item[data-task-id]').forEach(function (item) {
      item.addEventListener('dblclick', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var taskId = item.dataset.taskId;
        if (!taskId) return;
        showTaskDetailPopup(taskId, {
          locationName: item.dataset.locationName || '',
          assigneeName: item.dataset.assigneeName || '',
          color: item.dataset.queueColor || '#64748b',
          isQueued: true,
        });
      });
    });
  }

  // Register on App namespace
  App.showTaskDetailPopup = showTaskDetailPopup;
  App.initBlockDetail = initBlockDetail;
  window.ScheduleApp = App;
})();
