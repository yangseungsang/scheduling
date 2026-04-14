/**
 * 기타 스케줄 기능 모듈 — 큐 복귀 버튼, 큐 검색/토글, 태스크 호버 링크,
 * 주말 토글, 일정 이동(shift), 블록/태스크 추가 버튼 등 부가 기능을 제공한다.
 */
(function () {
  'use strict';

  var App = window.ScheduleApp || {};

  var showToast = App.showToast;
  var api = App.api;
  var isReadonly = App.isReadonly;

  // =====================================================================
  // 큐로 되돌리기 버튼
  // =====================================================================
  /**
   * 각 블록의 '큐로 보내기' 버튼(.btn-to-queue)에 클릭 이벤트를 등록한다.
   * 클릭 시 해당 블록을 삭제하고 잔여시간을 복원한다.
   */
  function initReturnToQueue() {
    document.querySelectorAll('.btn-to-queue[data-block-id]').forEach(function (btn) {
      // mousedown 전파 방지 — 블록 드래그 이벤트와 충돌 방지
      btn.addEventListener('mousedown', function (e) {
        e.stopPropagation();
      });
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        e.preventDefault();
        if (isReadonly()) return;
        var blockId = btn.dataset.blockId;
        // restore=1: 잔여시간 복원과 함께 블록 삭제
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
  // 큐 검색 + 가나다순 정렬
  // =====================================================================
  /**
   * 큐 검색 입력란과 큐 아이템 정렬을 초기화한다.
   * 초기 로드 시 procedure_id 기준 가나다순 정렬하고,
   * 검색어 입력 시 제목/섹션명으로 실시간 필터링한다.
   */
  function initQueueSearch() {
    var body = document.getElementById('task-queue-body');
    var input = document.getElementById('queue-search');
    if (!body || !input) return;

    /** 큐 아이템을 담당자 → 제목 순으로 정렬하고 담당자별 구분선 추가 */
    function sortItems() {
      // 기존 구분선 제거
      body.querySelectorAll('.queue-group-header').forEach(function (h) { h.remove(); });
      var items = Array.from(body.querySelectorAll('.queue-task-item'));
      // 1차 담당자명, 2차 제목 순 정렬
      items.sort(function (a, b) {
        var aAssignee = (a.dataset.assigneeName || '(미배정)');
        var bAssignee = (b.dataset.assigneeName || '(미배정)');
        var cmp = aAssignee.localeCompare(bAssignee);
        if (cmp !== 0) return cmp;
        return (a.dataset.title || '').localeCompare(b.dataset.title || '');
      });
      // DOM 재배치 + 담당자 그룹 헤더 삽입
      var lastAssignee = null;
      items.forEach(function (item) {
        var assignee = item.dataset.assigneeName || '(미배정)';
        if (assignee !== lastAssignee) {
          var header = document.createElement('div');
          header.className = 'queue-group-header';
          header.textContent = assignee;
          body.appendChild(header);
          lastAssignee = assignee;
        }
        body.appendChild(item);
      });
    }
    sortItems();

    // 검색어 입력 시 실시간 필터링
    input.addEventListener('input', function () {
      var query = input.value.trim().toLowerCase();
      body.querySelectorAll('.queue-task-item').forEach(function (item) {
        var id = (item.dataset.title || '').toLowerCase();
        var section = (item.querySelector('.queue-card-section') || {}).textContent || '';
        section = section.toLowerCase();
        // 제목 또는 섹션명에 검색어가 포함되면 표시
        var match = !query || id.indexOf(query) !== -1 || section.indexOf(query) !== -1;
        item.style.display = match ? '' : 'none';
      });
    });
  }

  // =====================================================================
  // 큐 접기/펼치기 토글
  // =====================================================================
  /**
   * 큐 영역의 접기/펼치기 토글 버튼을 초기화한다.
   */
  function initQueueToggle() {
    var btn = document.getElementById('toggle-queue');
    var q = document.getElementById('task-queue');
    if (btn && q) btn.onclick = function () { q.classList.toggle('collapsed'); };
  }

  // =====================================================================
  // 동일 태스크 호버 하이라이트
  // =====================================================================
  /**
   * 같은 task-id를 가진 모든 요소에 마우스 호버 시 동시 하이라이트를 적용한다.
   * 큐 아이템, 스케줄 블록, 월간 블록 등이 같은 태스크이면 함께 강조된다.
   */
  function initTaskHoverLink() {
    var allItems = document.querySelectorAll('[data-task-id]');
    if (!allItems.length) return;

    allItems.forEach(function (el) {
      el.addEventListener('mouseenter', function () {
        var taskId = el.dataset.taskId;
        if (!taskId) return;
        // 같은 task-id를 가진 모든 요소에 하이라이트 클래스 추가
        document.querySelectorAll('[data-task-id="' + taskId + '"]').forEach(function (item) {
          item.classList.add('task-linked-hover');
        });
      });
      el.addEventListener('mouseleave', function () {
        // 모든 하이라이트 제거
        document.querySelectorAll('.task-linked-hover').forEach(function (item) {
          item.classList.remove('task-linked-hover');
        });
      });
    });
  }

  // =====================================================================
  // 주말 표시/숨기기 토글
  // =====================================================================
  /**
   * 주말(토/일) 컬럼 표시/숨기기 토글 버튼을 초기화한다.
   * 설정은 localStorage에 저장되어 페이지 새로고침 후에도 유지된다.
   */
  function initWeekendToggle() {
    var btn = document.getElementById('btn-toggle-weekends');
    if (!btn) return;
    // localStorage에서 이전 설정 불러오기
    var hidden = localStorage.getItem('hideWeekends') === '1';

    /** 주말 컬럼의 표시/숨김을 현재 설정에 맞게 적용 */
    function applyWeekendVisibility() {
      // 주간뷰 주말 컬럼 (weekday: 5=토, 6=일)
      document.querySelectorAll('.week-day-col[data-weekday="5"], .week-day-col[data-weekday="6"]').forEach(function (col) {
        col.style.display = hidden ? 'none' : '';
      });
      // 월간뷰 주말 헤더
      document.querySelectorAll('th[data-weekday="5"], th[data-weekday="6"]').forEach(function (th) {
        th.style.display = hidden ? 'none' : '';
      });
      // 월간뷰 주말 셀 (각 행의 6, 7번째 셀)
      document.querySelectorAll('.month-table tbody tr').forEach(function (row) {
        var cells = row.querySelectorAll('td');
        if (cells.length >= 7) {
          cells[5].style.display = hidden ? 'none' : '';
          cells[6].style.display = hidden ? 'none' : '';
        }
      });
      // 버튼 활성화 상태 표시
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
  // 일정 이동 (일괄 날짜 이동)
  // =====================================================================
  /**
   * 일정 일괄 이동 버튼을 초기화한다.
   * 기준 날짜 이후의 모든 블록을 +1일 또는 -1일 이동한다.
   * 주말은 자동으로 건너뛴다.
   */
  function initShiftSchedule() {
    var btn = document.getElementById('btn-shift-schedule');
    if (!btn) return;
    btn.addEventListener('click', function () {
      if (isReadonly()) return;
      var old = document.getElementById('shift-schedule-popup');
      if (old) old.remove();

      // URL의 date 파라미터 또는 오늘 날짜를 기본값으로 사용
      var params = new URLSearchParams(window.location.search);
      var defaultDate = params.get('date') || new Date().toISOString().slice(0, 10);
      // 이동 설정 팝업 생성
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
            '<input type="date" class="form-control form-control-sm mb-2" id="shift-from-date" value="' + defaultDate + '">' +
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

      // 닫기 이벤트
      overlay.addEventListener('click', function (ev) { if (ev.target === overlay) overlay.remove(); });
      document.getElementById('shift-close').addEventListener('click', function () { overlay.remove(); });
      // 이동 실행 버튼
      document.getElementById('shift-ok').addEventListener('click', function () {
        var fromDate = document.getElementById('shift-from-date').value;
        var direction = parseInt(document.getElementById('shift-direction').value);
        if (!fromDate) { showToast('날짜를 입력하세요.', 'danger'); return; }
        overlay.remove();
        // 서버에 일괄 이동 요청
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
  // 태스크 추가 / 간단 블록 추가 버튼
  // =====================================================================
  /**
   * '태스크 추가' 및 '간단 블록 추가' 버튼을 초기화한다.
   * - 태스크 추가: 태스크 생성 페이지로 이동
   * - 간단 블록 추가: 제목/시간만 입력하여 큐에 추가
   */
  function initAddButtons() {
    // 태스크 추가 버튼 — 새 태스크 생성 페이지로 이동
    var taskBtn = document.getElementById('btn-add-task');
    if (taskBtn) {
      taskBtn.addEventListener('click', function () {
        window.location.href = '/tasks/new';
      });
    }

    // 간단 블록 추가 버튼
    var blockBtn = document.getElementById('btn-add-simple-block');
    if (!blockBtn) return;
    blockBtn.addEventListener('click', function () {
      if (isReadonly()) return;
      var old = document.getElementById('simple-block-popup');
      if (old) old.remove();

      // 간단 블록 추가 팝업 생성
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

      // 닫기 이벤트
      overlay.addEventListener('click', function (ev) { if (ev.target === overlay) overlay.remove(); });
      document.getElementById('simple-close').addEventListener('click', function () { overlay.remove(); });
      // 큐에 추가 버튼
      document.getElementById('simple-ok').addEventListener('click', function () {
        var title = document.getElementById('simple-title').value.trim();
        var minutes = parseInt(document.getElementById('simple-minutes').value) || 60;
        if (!title) { showToast('제목을 입력하세요.', 'danger'); return; }
        overlay.remove();
        // 서버에 간단 블록 생성 요청
        api('POST', '/schedule/api/simple-blocks', {
          title: title, estimated_minutes: minutes,
        }).then(function () {
          showToast('큐에 추가되었습니다.', 'success');
          setTimeout(function () { location.reload(); }, 300);
        }).catch(function (err) { showToast(err.message, 'danger'); });
      });
    });
  }

  // App 네임스페이스에 등록
  App.initReturnToQueue = initReturnToQueue;
  App.initQueueSearch = initQueueSearch;
  App.initQueueToggle = initQueueToggle;
  App.initTaskHoverLink = initTaskHoverLink;

  // =====================================================================
  // 월간뷰 "더보기" 토글
  // =====================================================================
  /**
   * 월간뷰 셀에서 숨겨진 블록의 '더보기/접기' 토글을 초기화한다.
   * 셀에 블록이 많으면 일부를 숨기고 '+N개 더' 링크로 표시한다.
   */
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
          // 숨겨진 블록 수를 세어 표시
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
