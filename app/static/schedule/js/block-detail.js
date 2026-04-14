/**
 * 블록 상세 팝업 모듈 — 블록/큐 아이템 더블클릭 시 상세 정보를 표시한다.
 * 식별자 목록, 예상 시간, 배치 정보, 메모 편집 기능을 제공한다.
 */
(function () {
  'use strict';

  var App = window.ScheduleApp || {};

  var showToast = App.showToast;
  var api = App.api;
  var isReadonly = App.isReadonly;

  // =====================================================================
  // 블록 상세 팝업
  // =====================================================================

  /**
   * 태스크 상세 정보 팝업을 표시한다.
   * 서버에서 태스크 정보와 해당 태스크의 모든 블록을 조회하여
   * 식별자별 배치 현황, 시간, 상태 등을 테이블 형태로 보여준다.
   * @param {string} taskId - 태스크 ID
   * @param {Object} [opts={}] - 표시 옵션
   * @param {string} [opts.blockId] - 현재 블록 ID
   * @param {string} [opts.startTime] - 블록 시작 시간
   * @param {string} [opts.endTime] - 블록 종료 시간
   * @param {string} [opts.locationName] - 장소 이름
   * @param {string} [opts.assigneeName] - 담당자 이름
   * @param {string} [opts.memo] - 메모 내용
   * @param {string} [opts.blockStatus] - 블록 상태 ('pending'|'in_progress'|'completed'|'cancelled')
   * @param {string} [opts.color] - 블록 색상
   * @param {Array<string>} [opts.identifierIds] - 현재 블록에 할당된 식별자 ID 목록
   * @param {boolean} [opts.isQueued] - 큐 아이템 여부
   */
  function showTaskDetailPopup(taskId, opts) {
    opts = opts || {};
    var blockId = opts.blockId || null;
    // 태스크 정보와 해당 태스크의 모든 블록을 병렬로 조회
    Promise.all([
      api('GET', '/tasks/api/' + taskId),
      api('GET', '/schedule/api/blocks/by-task/' + taskId).catch(function() { return {blocks: []}; }),
    ]).then(function (results) {
      var task = results[0] && results[0].task;
      var allBlocks = (results[1] && results[1].blocks) || [];
      if (!task) { showToast('항목 정보를 불러올 수 없습니다.', 'danger'); return; }

      // 표시할 기본 정보 구성
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

      // 현재 블록에 할당된 식별자 ID 집합 구성
      var blockIdentifierIds = opts.identifierIds || null;
      var blockIdSet = {};
      if (blockIdentifierIds) {
        blockIdentifierIds.forEach(function(id) { blockIdSet[id] = true; });
      }
      // 분할 블록 여부: 현재 블록의 식별자 수 < 전체 식별자 수
      var isSplit = blockIdentifierIds && (task.identifiers || []).length > blockIdentifierIds.length;

      // 식별자 → 배치 정보 매핑 구성 (모든 블록에서)
      var allTestList = task.identifiers || [];
      var allTaskIds = allTestList.map(function(it) { return typeof it === 'object' ? it.id : it; });
      var idScheduleMap = {};  // id → {time, status, date}
      // 블록을 날짜+시간 순으로 정렬
      allBlocks.sort(function(a,b) { return (a.date + a.start_time).localeCompare(b.date + b.start_time); });
      allBlocks.forEach(function(blk) {
        var bids = blk.identifier_ids || allTaskIds;
        bids.forEach(function(iid) {
          // 각 식별자의 첫 번째 배치 정보만 기록
          if (!idScheduleMap[iid]) {
            idScheduleMap[iid] = {
              time: blk.date + ' ' + blk.start_time + '–' + blk.end_time,
              date: blk.date,
              status: blk.block_status || 'pending',
            };
          }
        });
      });

      // 식별자 목록 HTML 구성 (체크박스 포함)
      var testListHtml = '-';
      var idTotalMin = 0; // 식별자별 시간 합계
      // 이 블록에 속한 식별자 목록 (체크박스 액션 대상)
      var thisBlockIds = [];
      if (allTestList.length) {
        testListHtml =
          '<div class="d-flex gap-1 mb-1">' +
            '<button type="button" class="btn btn-outline-secondary" style="font-size:0.65rem;padding:1px 6px" id="bd-id-select-all">전체 선택</button>' +
            '<button type="button" class="btn btn-outline-secondary" style="font-size:0.65rem;padding:1px 6px" id="bd-id-deselect-all">전체 해제</button>' +
          '</div>' +
          '<table style="font-size:0.78rem;border-collapse:collapse;border-spacing:0;white-space:nowrap">' +
          '<tr style="color:#9ca3af;font-size:0.68rem;border-bottom:1px solid #f3f4f6">' +
            '<td style="padding:3px 4px"></td>' +
            '<td style="padding:3px 10px 3px 4px">식별자</td><td style="padding:3px 10px 3px 4px">시험항목</td><td style="padding:3px 10px 3px 4px">시간</td>' +
            '<td style="padding:3px 10px 3px 4px">작성자</td><td style="padding:3px 4px">배치</td></tr>' +
          allTestList.map(function(item) {
            if (typeof item === 'object' && item.id) {
              var mins = item.estimated_minutes || 0;
              idTotalMin += mins;
              var ow = (item.owners || []).join(', ') || '-';
              // 이 블록에 속한 식별자인지 여부 (분할 블록이 아니면 모두 해당)
              var inThisBlock = !isSplit || blockIdSet[item.id];
              if (inThisBlock) thisBlockIds.push(item.id);
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
              var itemName = item.name || '-';
              var cbDisabled = !inThisBlock ? ' disabled' : '';
              var cbChecked = inThisBlock ? ' checked' : '';
              return '<tr style="' + rowStyle + '">' +
                '<td style="padding:3px 4px"><input type="checkbox" class="bd-id-check" data-id="' + item.id + '"' + cbChecked + cbDisabled + '></td>' +
                '<td style="padding:3px 10px 3px 4px;font-weight:600;white-space:nowrap">' + item.id + marker + '</td>' +
                '<td style="padding:3px 10px 3px 4px;color:#475569">' + itemName + '</td>' +
                '<td style="padding:3px 10px 3px 4px;white-space:nowrap">' + mins + '분</td>' +
                '<td style="padding:3px 10px 3px 4px;color:#6c757d">' + ow + '</td>' +
                '<td style="padding:3px 4px">' + schedHtml + '</td></tr>';
            }
            return '<tr><td colspan="6" style="padding:3px 4px">' + item + '</td></tr>';
          }).join('') +
          '<tr style="border-top:1px solid #e5e7eb">' +
            '<td></td><td style="padding:4px;font-weight:700">합계</td>' +
            '<td style="padding:4px;font-weight:700" colspan="2"><span id="bd-id-total">' + idTotalMin + '</span>분</td>' +
            '<td colspan="2"></td></tr>' +
          '</table>' +
          (blockId && thisBlockIds.length >= 2
            ? '<div class="d-flex gap-1 mt-2">' +
                '<button type="button" class="btn btn-sm btn-outline-primary flex-fill" id="bd-id-split"><i class="bi bi-scissors"></i> 선택 분리</button>' +
                '<button type="button" class="btn btn-sm btn-outline-secondary flex-fill" id="bd-id-to-queue"><i class="bi bi-box-arrow-left"></i> 선택 큐로</button>' +
              '</div>'
            : '');
      }
      // 분할 블록일 때 (현재 블록 식별자 수 / 전체 식별자 수) 표시
      var splitInfo = '';
      var totalIdCount = (task.identifiers || []).length;
      if (blockIdentifierIds && blockIdentifierIds.length < totalIdCount) {
        splitInfo = ' <span style="font-size:0.75rem;color:#6c757d">(분할 ' + blockIdentifierIds.length + '/' + totalIdCount + ')</span>';
      }

      // 기존 팝업 제거
      var old = document.getElementById('block-detail-popup');
      if (old) old.remove();

      // 오버레이 생성
      var overlay = document.createElement('div');
      overlay.id = 'block-detail-popup';
      overlay.className = 'block-detail-overlay';

      // 상태 배지 (큐 아이템이면 '미배치', 아니면 블록 상태)
      var statusBadge = isQueued
        ? '<span class="bd-badge bd-badge-queued">미배치</span>'
        : '<span class="bd-badge bd-badge-' + status + '">' + statusLabel + '</span>';

      // 메모 HTML 이스케이프
      var escapedMemo = memo.replace(/"/g, '&quot;').replace(/</g, '&lt;');

      // 태스크 전체 상태 (블록 상태와 별개)
      var taskStatus = task.status || 'waiting';
      var taskStatusLabel = { waiting: '대기', in_progress: '진행 중', completed: '완료' }[taskStatus] || taskStatus;

      // 팝업 HTML 구성
      var html =
        '<div class="bd-box">' +
          '<div class="bd-header">' +
            '<div class="bd-header-left">' +
              '<span class="bd-id">' + (task.doc_name || '') + '</span>' +
              statusBadge +
            '</div>' +
            '<button class="bd-x" id="block-detail-close">&times;</button>' +
          '</div>' +
          '<div class="bd-divider"></div>' +
          '<table class="bd-tbl">' +
            '<tr><td class="bd-k">시험 식별자' + splitInfo + '</td><td class="bd-v">' + testListHtml + '</td></tr>' +
            '<tr><td class="bd-k">예상 시간</td><td class="bd-v">' +
              (task.estimated_minutes || 0) + '분' +
              // 식별자 합계가 태스크 예상 시간과 다르면 별도 표시
              (idTotalMin && idTotalMin !== (task.estimated_minutes || 0) ? ' <span class="bd-sub">(식별자 합계 ' + idTotalMin + '분)</span>' : '') +
              ' <span class="bd-sub">(잔여 ' + (task.remaining_minutes || 0) + '분)</span>' +
            '</td></tr>' +
            '<tr><td class="bd-k">시험장소</td><td class="bd-v">' + (locationName || '-') + '</td></tr>' +
            (startTime ? '<tr><td class="bd-k">배치 시간</td><td class="bd-v" style="white-space:nowrap">' +
              '<input type="time" id="bd-start-time" value="' + startTime + '" style="font-size:0.82rem;border:1px solid #d1d5db;border-radius:3px;padding:1px 6px;width:115px;box-sizing:content-box"> – ' +
              '<input type="time" id="bd-end-time" value="' + endTime + '" style="font-size:0.82rem;border:1px solid #d1d5db;border-radius:3px;padding:1px 6px;width:115px;box-sizing:content-box">' +
              ' <span class="bd-sub" id="bd-time-dur"></span>' +
            '</td></tr>' : '') +
            '<tr><td class="bd-k">시험 담당자</td><td class="bd-v">' + (assigneeName || '-') + '</td></tr>' +
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

      // 닫기 버튼 클릭 이벤트
      document.getElementById('block-detail-close').addEventListener('click', function () {
        overlay.remove();
      });
      // 오버레이 바깥 클릭 시 닫기
      overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay) overlay.remove();
      });

      // 식별자 체크박스 전체 선택/해제
      var selectAllBtn = document.getElementById('bd-id-select-all');
      var deselectAllBtn = document.getElementById('bd-id-deselect-all');
      if (selectAllBtn) {
        selectAllBtn.addEventListener('click', function () {
          overlay.querySelectorAll('.bd-id-check:not(:disabled)').forEach(function (cb) { cb.checked = true; });
        });
      }
      if (deselectAllBtn) {
        deselectAllBtn.addEventListener('click', function () {
          overlay.querySelectorAll('.bd-id-check:not(:disabled)').forEach(function (cb) { cb.checked = false; });
        });
      }

      // 선택 분리 버튼
      var splitBtn = document.getElementById('bd-id-split');
      if (splitBtn && blockId) {
        splitBtn.addEventListener('click', function () {
          var checked = [];
          overlay.querySelectorAll('.bd-id-check:checked').forEach(function (cb) { checked.push(cb.dataset.id); });
          if (checked.length === 0) { showToast('최소 1개는 선택하세요.', 'danger'); return; }
          if (checked.length === thisBlockIds.length) { showToast('전체를 남기면 분리되지 않습니다.', 'info'); return; }
          overlay.remove();
          api('POST', '/schedule/api/blocks/' + blockId + '/split', {
            keep_identifier_ids: checked
          }).then(function () {
            showToast('블록이 분리되었습니다.', 'success');
            App.softReload();
          }).catch(function (err) { showToast(err.message, 'danger'); });
        });
      }

      // 선택 큐로 보내기 버튼
      var toQueueBtn = document.getElementById('bd-id-to-queue');
      if (toQueueBtn && blockId) {
        toQueueBtn.addEventListener('click', function () {
          var checked = [];
          overlay.querySelectorAll('.bd-id-check:checked').forEach(function (cb) { checked.push(cb.dataset.id); });
          var unchecked = thisBlockIds.filter(function (id) { return checked.indexOf(id) === -1; });
          if (unchecked.length === 0) { showToast('큐로 보낼 식별자를 해제하세요. (체크 해제 = 큐로)', 'info'); return; }
          overlay.remove();
          if (checked.length === 0) {
            // 전체 큐로 → 블록 삭제
            api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
              .then(function () { showToast('전체를 큐로 되돌렸습니다.', 'success'); App.softReload(); })
              .catch(function (err) { showToast(err.message, 'danger'); });
          } else {
            api('POST', '/schedule/api/blocks/' + blockId + '/return-identifiers', {
              keep_identifier_ids: checked
            }).then(function () {
              showToast(unchecked.length + '건을 큐로 되돌렸습니다.', 'success');
              App.softReload();
            }).catch(function (err) { showToast(err.message, 'danger'); });
          }
        });
      }

      // 배치 시간 인풋이 있으면 실시간 소요시간 표시
      var startInput = document.getElementById('bd-start-time');
      var endInput = document.getElementById('bd-end-time');
      var durSpan = document.getElementById('bd-time-dur');
      function updateDurDisplay() {
        if (!startInput || !endInput || !durSpan) return;
        var s = App.timeToMin(startInput.value), e = App.timeToMin(endInput.value);
        durSpan.textContent = (s >= 0 && e > s) ? '(' + (e - s) + '분)' : '';
      }
      if (startInput) { startInput.addEventListener('input', updateDurDisplay); endInput.addEventListener('input', updateDurDisplay); updateDurDisplay(); }

      // 저장 버튼 클릭 — 메모 및 배치 시간 저장
      document.getElementById('bd-save').addEventListener('click', function () {
        var newMemo = document.getElementById('bd-memo').value;
        var newStart = startInput ? startInput.value : startTime;
        var newEnd = endInput ? endInput.value : endTime;

        // 배치 시간 유효성 확인
        if (newStart && newEnd && App.timeToMin(newStart) >= App.timeToMin(newEnd)) {
          showToast('종료 시간은 시작 시간보다 늦어야 합니다.', 'danger');
          return;
        }

        // 블록 시간 변경 (blockId가 있고 시간이 바뀐 경우)
        // resize:true 플래그로 백엔드가 사용자가 입력한 start/end를 그대로 적용하도록 지시
        // (기본 분기는 드래그-이동용이라 end_time을 원래 duration으로 재계산함)
        var timeChanged = blockId && newStart && newEnd && (newStart !== startTime || newEnd !== endTime);
        var blockSave = timeChanged
          ? api('PUT', '/schedule/api/blocks/' + blockId, {
              start_time: newStart,
              end_time: newEnd,
              resize: true,
            })
          : Promise.resolve();

        // 메모 저장
        var memoSave = api('PUT', '/tasks/api/' + taskId + '/update', Object.assign({}, task, { memo: newMemo }));

        Promise.all([blockSave, memoSave])
          .then(function () {
            showToast('저장되었습니다.', 'success');
            overlay.remove();
            App.softReload();
          })
          .catch(function (err) { showToast(err.message, 'danger'); });
      });
    }).catch(function (err) { showToast(err.message || '팝업 로드 실패', 'danger'); });
  }

  /**
   * 스케줄 블록 및 큐 아이템에 더블클릭 이벤트를 등록하여 상세 팝업을 표시한다.
   * - 스케줄 블록(.schedule-block) / 월간 블록(.month-block-item): 블록 상세 정보 팝업
   * - 큐 아이템(.queue-task-item): 큐 상태 팝업
   */
  function initBlockDetail() {
    // 스케줄 블록 + 월간 블록에 더블클릭 이벤트 등록
    document.querySelectorAll('.schedule-block[data-block-id], .month-block-item[data-block-id]').forEach(function (block) {
      block.addEventListener('dblclick', function (e) {
        e.preventDefault();
        e.stopPropagation();

        var taskId = block.dataset.taskId;
        if (!taskId || taskId === 'None') return;
        // data-identifier-ids 속성에서 식별자 ID 배열 파싱
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

    // 큐 아이템에 더블클릭 이벤트 등록
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

  // App 네임스페이스에 등록
  App.showTaskDetailPopup = showTaskDetailPopup;
  App.initBlockDetail = initBlockDetail;
  window.ScheduleApp = App;
})();
