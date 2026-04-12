/**
 * 컨텍스트 메뉴 모듈 — 스케줄 블록 우클릭 시 동작 메뉴를 표시한다.
 * 상태 변경, 메모, 블록 분리, 큐로 보내기, 잠금, 삭제 기능을 제공한다.
 */
(function () {
  'use strict';

  var App = window.ScheduleApp || {};

  var showToast = App.showToast;
  var api = App.api;
  var isReadonly = App.isReadonly;
  var showConfirmModal = App.showConfirmModal;
  var openMemoModal = App.openMemoModal;

  // =====================================================================
  // 컨텍스트 메뉴
  // =====================================================================
  /**
   * document 레벨에 contextmenu 이벤트를 등록하여
   * 스케줄 블록 우클릭 시 커스텀 컨텍스트 메뉴를 표시한다.
   * 메뉴 항목: 상태 변경, 메모, 분리, 큐로 보내기, 잠금 토글, 삭제
   */
  function initContextMenu() {
    document.addEventListener('contextmenu', function (e) {
      if (isReadonly()) return;
      var block = e.target.closest('.schedule-block[data-block-id]');
      if (!block) return;
      e.preventDefault();
      // 기존 메뉴 제거
      var old = document.getElementById('block-context-menu');
      if (old) old.remove();

      var blockId = block.dataset.blockId;
      var currentStatus = block.dataset.blockStatus || 'pending';

      // 메뉴 요소 생성 (Bootstrap 드롭다운 스타일)
      var menu = document.createElement('div');
      menu.id = 'block-context-menu';
      menu.className = 'dropdown-menu show';
      // 초기에 visibility:hidden으로 렌더링 후 위치 조정 (깜빡임 방지)
      menu.style.cssText = 'position:fixed;z-index:1200;left:' + e.clientX + 'px;top:' + e.clientY + 'px;visibility:hidden;';

      // 상태 변경 항목 구성
      var statusItems = [
        { value: 'pending', label: '시작 전', icon: 'bi-hourglass' },
        { value: 'in_progress', label: '진행 중', icon: 'bi-play-circle' },
        { value: 'completed', label: '완료', icon: 'bi-check-circle' },
        { value: 'cancelled', label: '불가', icon: 'bi-x-circle' },
      ];
      var statusHtml = '<div class="dropdown-header" style="font-size:0.75rem;padding:4px 12px;">상태 변경</div>';
      statusItems.forEach(function (s) {
        var active = s.value === currentStatus ? ' active' : '';
        statusHtml += '<button class="dropdown-item' + active + '" data-action="status" data-status="' + s.value + '">' +
          '<i class="bi ' + s.icon + '"></i> ' + s.label + '</button>';
      });

      menu.innerHTML =
        statusHtml +
        '<div class="dropdown-divider"></div>' +
        '<button class="dropdown-item" data-action="memo"><i class="bi bi-sticky"></i> 메모</button>' +
        '<button class="dropdown-item" data-action="split"><i class="bi bi-scissors"></i> 분리</button>' +
        '<button class="dropdown-item" data-action="to-queue"><i class="bi bi-arrow-left-square"></i> 큐로 보내기</button>' +
        '<button class="dropdown-item" data-action="lock"><i class="bi bi-lock"></i> 잠금 토글</button>' +
        '<button class="dropdown-item text-danger" data-action="delete"><i class="bi bi-trash"></i> 삭제</button>';
      document.body.appendChild(menu);

      // 메뉴가 화면 밖으로 넘칠 경우 위치 조정
      var menuRect = menu.getBoundingClientRect();
      if (menuRect.bottom > window.innerHeight) {
        menu.style.top = Math.max(0, e.clientY - menuRect.height) + 'px';
      }
      if (menuRect.right > window.innerWidth) {
        menu.style.left = Math.max(0, e.clientX - menuRect.width) + 'px';
      }
      // 위치 조정 후 표시
      menu.style.visibility = '';

      // 메뉴 항목 클릭 이벤트 처리
      menu.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-action]');
        if (!btn) return;
        menu.remove();

        if (btn.dataset.action === 'memo') {
          // 메모 모달 열기
          openMemoModal(blockId, block.dataset.memo || '');
        } else if (btn.dataset.action === 'status') {
          // 블록 상태 변경
          api('PUT', '/schedule/api/blocks/' + blockId + '/status', { block_status: btn.dataset.status })
            .then(function () { location.reload(); })
            .catch(function (err) { showToast(err.message, 'danger'); });
        } else if (btn.dataset.action === 'to-queue') {
          // 블록을 큐로 되돌리기 (잔여시간 복원)
          api('DELETE', '/schedule/api/blocks/' + blockId + '?restore=1')
            .then(function () {
              showToast('큐로 되돌렸습니다.', 'success');
              location.reload();
            })
            .catch(function (err) { showToast(err.message, 'danger'); });
        } else if (btn.dataset.action === 'split') {
          // 블록 분리 — 식별자를 2개 블록으로 나누기
          var taskId = block.dataset.taskId;
          if (!taskId) { showToast('분리할 수 없는 블록입니다.', 'danger'); return; }
          // 태스크 정보와 관련 블록을 병렬 조회
          Promise.all([
            api('GET', '/tasks/api/' + taskId),
            api('GET', '/schedule/api/blocks/by-task/' + taskId).catch(function() { return {blocks: []}; }),
          ]).then(function (results) {
            var tsk = results[0].task;
            var allBlocks = (results[1] && results[1].blocks) || [];
            if (!tsk || !tsk.identifiers || tsk.identifiers.length < 2) {
              showToast('식별자가 2개 이상이어야 분리할 수 있습니다.', 'danger');
              return;
            }
            // 현재 블록이 담당하는 식별자 ID 목록 파악
            var blockIdIds = null;
            try { if (block.dataset.identifierIds) blockIdIds = JSON.parse(block.dataset.identifierIds); } catch(ex) {}

            var currentIds;
            if (blockIdIds) {
              // 이미 분할된 블록: 해당 블록의 식별자만 사용
              currentIds = blockIdIds;
            } else {
              // 미분할 블록: 다른 분할 블록에 이미 할당된 식별자 제외
              var otherIds = {};
              allBlocks.forEach(function (b) {
                if (b.id === blockId || !b.identifier_ids) return;
                b.identifier_ids.forEach(function (id) { otherIds[id] = true; });
              });
              currentIds = tsk.identifiers
                .map(function(it) { return typeof it === 'object' ? it.id : it; })
                .filter(function(id) { return !otherIds[id]; });
            }

            // 현재 블록의 식별자만으로 test_list 필터링
            var blockTestList = tsk.identifiers.filter(function(it) {
              var iid = typeof it === 'object' ? it.id : it;
              return currentIds.indexOf(iid) !== -1;
            });
            if (blockTestList.length < 2) {
              showToast('이 블록의 식별자가 2개 이상이어야 분리할 수 있습니다.', 'danger');
              return;
            }

            // 분리 피커 표시: 체크 유지=이 블록에 남김, 체크 해제=새 블록으로 분리
            App.showSplitPicker(blockTestList, function (keepItems) {
              if (!keepItems || keepItems.length === 0 || keepItems.length === blockTestList.length) return;
              var keepIds = keepItems.map(function (s) { return typeof s === 'object' ? s.id : s; });
              // 서버에 분리 요청
              api('POST', '/schedule/api/blocks/' + blockId + '/split', {
                keep_identifier_ids: keepIds
              }).then(function () {
                showToast('블록이 분리되었습니다.', 'success');
                setTimeout(function () { location.reload(); }, 300);
              }).catch(function (err) { showToast(err.message, 'danger'); });
            });
          });
        } else if (btn.dataset.action === 'lock') {
          // 잠금 상태 토글
          api('PUT', '/schedule/api/blocks/' + blockId + '/lock')
            .then(function () { location.reload(); })
            .catch(function (err) { showToast(err.message, 'danger'); });
        } else if (btn.dataset.action === 'delete') {
          // 삭제 확인 모달 후 블록 삭제
          showConfirmModal('이 블록을 삭제하시겠습니까?', {
            title: '블록 삭제', icon: 'trash', okText: '삭제', cancelText: '취소'
          }).then(function (ok) {
            if (ok) {
              api('DELETE', '/schedule/api/blocks/' + blockId)
                .then(function () { location.reload(); })
                .catch(function (err) { showToast(err.message, 'danger'); });
            }
          });
        }
      });

      // 메뉴 외부 클릭 시 닫기 (setTimeout으로 현재 클릭 이벤트 이후 등록)
      setTimeout(function () {
        document.addEventListener('click', function h() {
          menu.remove(); document.removeEventListener('click', h);
        }, { once: true });
      }, 0);
    });
  }

  // =====================================================================
  // 분리 피커 — 체크 유지=이 블록에 남김, 체크 해제=새 블록으로 분리
  // =====================================================================
  /**
   * 블록 분리 시 어떤 식별자를 이 블록에 남기고 어떤 것을 새 블록으로 분리할지 선택하는 팝업.
   * @param {Array<Object|string>} testList - 현재 블록의 식별자 목록
   * @param {function} callback - 선택 결과 콜백 (남길 항목 배열 또는 취소 시 null)
   */
  function showSplitPicker(testList, callback) {
    var old = document.getElementById('identifier-picker');
    if (old) old.remove();

    var overlay = document.createElement('div');
    overlay.id = 'identifier-picker';
    overlay.className = 'block-detail-overlay';
    // 각 식별자별 체크박스 행 (기본 전체 체크)
    var rows = '';
    testList.forEach(function (item, i) {
      var id = typeof item === 'object' ? item.id : item;
      var owners = (typeof item === 'object' && item.owners) ? item.owners : [];
      var mins = typeof item === 'object' ? (item.estimated_minutes || 0) : 0;
      var itemName = (typeof item === 'object' && item.name) ? item.name : '';
      var ownerStr = owners.length ? ' <span class="text-muted">작성: ' + owners.join(', ') + '</span>' : '';
      var nameStr = itemName ? ' <span class="text-muted" style="font-size:0.78rem">- ' + itemName + '</span>' : '';
      rows += '<label class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem;white-space:nowrap">' +
        '<input type="checkbox" class="form-check-input" value="' + i + '" checked> ' +
        '<span>' + id + '</span>' + nameStr + ownerStr +
        (mins > 0 ? ' <span class="text-muted">(' + mins + '분)</span>' : '') +
        '</label>';
    });
    overlay.innerHTML =
      '<div class="bd-box">' +
        '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">블록 분리</span></div>' +
          '<button class="bd-x" id="picker-close">&times;</button></div>' +
        '<div class="bd-divider"></div>' +
        '<div style="padding:12px">' +
          '<div class="form-text mb-2"><strong>체크 유지</strong> = 이 블록에 남김<br><strong>체크 해제</strong> = 새 블록으로 분리</div>' +
          '<div id="picker-list">' + rows + '</div>' +
          '<button class="btn btn-sm btn-primary w-100 mt-2" id="picker-ok">분리</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    /** 스페이스 키로 분리 버튼 빠른 실행 */
    function onSpace(ev) {
      if (ev.key === ' ') {
        ev.preventDefault();
        document.getElementById('picker-ok').click();
      }
    }
    document.addEventListener('keydown', onSpace);
    // 오버레이 바깥 클릭 시 취소
    overlay.addEventListener('click', function (ev) { if (ev.target === overlay) { document.removeEventListener('keydown', onSpace); overlay.remove(); callback(null); } });
    // 닫기 버튼 클릭 시 취소
    document.getElementById('picker-close').addEventListener('click', function () { document.removeEventListener('keydown', onSpace); overlay.remove(); callback(null); });
    // 분리 버튼 클릭 — 유효성 검증 후 콜백
    document.getElementById('picker-ok').addEventListener('click', function () {
      document.removeEventListener('keydown', onSpace);
      var checked = [];
      overlay.querySelectorAll('#picker-list input:checked').forEach(function (cb) {
        checked.push(parseInt(cb.value));
      });
      overlay.remove();
      // 최소 1개는 남겨야 분리 가능
      if (checked.length === 0) { showToast('최소 1개는 남겨야 합니다.', 'danger'); callback(null); return; }
      // 전체를 남기면 분리가 아님
      if (checked.length === testList.length) { showToast('전체를 남기면 분리되지 않습니다.', 'info'); callback(null); return; }
      var selected = checked.map(function (i) { return testList[i]; });
      callback(selected);
    });
  }

  // App 네임스페이스에 등록
  App.initContextMenu = initContextMenu;
  App.showSplitPicker = showSplitPicker;
  window.ScheduleApp = App;
})();
