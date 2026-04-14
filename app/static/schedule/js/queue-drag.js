/**
 * 큐 드래그 모듈 — 큐에서 캘린더로 태스크를 드래그하여 배치한다.
 * 식별자 선택 피커, 월간 배치 설정 피커, 장소 선택 피커 기능도 포함한다.
 */
(function (App) {
  'use strict';

  // utils.js, drag-core.js에서 가져온 단축 참조
  var startDrag = App.startDrag;
  var api = App.api;
  var showToast = App.showToast;
  var getTaskRemaining = App.getTaskRemaining;
  var checkRemainingAfterPlace = App.checkRemainingAfterPlace;
  var timeToMin = App.timeToMin;
  var minToTime = App.minToTime;
  var snapMin = App.snapMin;
  // GRID_MINUTES는 App.GRID_MINUTES를 직접 참조 (initAll에서 갱신되므로 캡처하지 않음)
  var SLOT_HEIGHT = App.SLOT_HEIGHT;

  // =====================================================================
  // 2. 큐 드래그 — 큐 아이템을 캘린더에 드래그하여 블록 생성
  // =====================================================================
  /**
   * 큐의 모든 태스크 아이템에 드래그 이벤트를 등록한다.
   * 시간 슬롯 또는 월간뷰 셀에 드롭하면 블록이 생성된다.
   * 식별자가 2개 이상이면 선택 피커를 표시하여 부분 배치가 가능하다.
   */
  function initQueueDrag() {
    document.querySelectorAll('.queue-task-item[data-task-id]').forEach(function (item) {
      item.addEventListener('mousedown', function (e) {
        var taskId = item.dataset.taskId;
        // 담당자 이름 배열 파싱 (쉼표 구분 문자열)
        var assigneeNames = item.dataset.assigneeNames ? item.dataset.assigneeNames.split(',').filter(Boolean) : [];
        var locationId = item.dataset.locationId || '';
        // 잔여 시간(분) — 블록 길이 결정에 사용
        var remaining = parseFloat(item.dataset.remainingMinutes) || 1;
        var title = (item.querySelector('.queue-card-section-title') || item.querySelector('.queue-card-id') || {}).textContent || '';

        // 식별자 목록 파싱 (JSON 배열)
        var identifiersRaw = item.dataset.identifiers || '[]';
        var testList = [];
        try { testList = JSON.parse(identifiersRaw); } catch(e2) {}

        // 블록 길이를 잔여 시간(분)으로 설정
        var blockMin = Math.round(remaining);
        blockMin = Math.max(blockMin, 1); // 최소 1분
        // 고스트 요소 높이 계산 (시간 비례)
        var expectedHeight = (blockMin / App.GRID_MINUTES) * SLOT_HEIGHT;

        startDrag(e, {
          sourceEl: item,
          ghostText: title,
          ghostColor: '#0d6efd',
          ghostWidth: 150,
          ghostHeight: expectedHeight,
          onDrop: function (target) {
            // 큐에 다시 드롭한 경우 무시
            if (target.type === 'queue') return;

            /**
             * 현재 뷰의 업무 종료 시간(분)을 계산한다.
             * 시간 슬롯 중 가장 늦은 시간을 찾는다.
             * @returns {number} 업무 종료 시간 (분)
             */
            function getWorkEndMin() {
              var slots = document.querySelectorAll('.time-slot[data-time]');
              var max = 0;
              slots.forEach(function (s) {
                var t2 = timeToMin(s.dataset.time);
                if (t2 > max) max = t2;
              });
              return max || timeToMin('17:00'); // 기본 17:00
            }

            /**
             * 실제 블록을 생성하는 핵심 함수.
             * 분할 배치 시 선택된 식별자만, 전체 배치 시 null을 전달한다.
             * @param {Array<string>|null} selectedIds - 선택된 식별자 ID 목록 (null이면 전체)
             * @param {number|null} overrideMin - 분할 시 개별 시간 합계 (null이면 원래 blockMin 사용)
             */
            function createBlock(selectedIds, overrideMin) {
              var bMin = overrideMin || blockMin;
              var identifierIds = selectedIds || null;
              var isPartial = !!selectedIds; // 분할 배치 여부

              /**
               * 서버에 블록 생성 API를 호출한다.
               * @param {number} startMin - 시작 시간 (분)
               * @param {number} endMin - 종료 시간 (분)
               * @param {number} overflowMin - 초과 시간 (분, 업무 종료 이후 잘린 시간)
               * @param {string} [locOverride] - 장소 ID 오버라이드 (월간뷰 피커에서 선택 시)
               */
              function doCreate(startMin, endMin, overflowMin, locOverride) {
                var prevRem;
                // 드롭 위치의 장소 결정 (오버라이드 > 슬롯 장소 > 태스크 기본 장소 > 활성 필터 장소)
                var dropLocationId = locOverride || (target.type === 'slot' ? (target.locationId || locationId) : locationId);
                // 장소가 여전히 비어있으면 활성 장소 필터에서 추론
                if (!dropLocationId) {
                  var activeLocs = [];
                  var allBtn = document.querySelector('.loc-filter-btn.active[data-loc-id=""]');
                  if (!allBtn) {
                    document.querySelectorAll('.loc-filter-btn.active[data-loc-id]').forEach(function (b) {
                      if (b.dataset.locId) activeLocs.push(b.dataset.locId);
                    });
                  }
                  if (activeLocs.length === 1) {
                    dropLocationId = activeLocs[0];
                  }
                }
                // 시간표 배치 시 장소는 필수
                if (!dropLocationId) {
                  App.showLocationPicker(function (pickedLocId) {
                    if (!pickedLocId) { showToast('장소를 선택해야 배치할 수 있습니다.', 'danger'); return; }
                    doCreate(startMin, endMin, overflowMin, pickedLocId);
                  });
                  return;
                }
                getTaskRemaining(taskId).then(function (r) {
                  prevRem = r;
                  var payload = {
                    task_id: taskId, assignee_names: assigneeNames,
                    location_id: dropLocationId,
                    date: target.date,
                    start_time: minToTime(startMin),
                    end_time: minToTime(endMin),
                    identifier_ids: identifierIds,
                  };
                  // 초과 시간이 있으면 서버에 알림
                  if (overflowMin > 0) payload.overflow_minutes = overflowMin;
                  return api('POST', '/schedule/api/blocks', payload);
                }).then(function () {
                  // 전체 배치일 때만 잔여 시간 경고 확인
                  if (!isPartial) return checkRemainingAfterPlace(taskId, title.trim(), prevRem);
                }).then(function () { return App.softReload(); })
                  .catch(function (err) { showToast(err.message, 'danger'); });
              }

              /**
               * 시작 시간과 업무 종료 시간을 비교하여 초과 시 확인 후 생성한다.
               * @param {number} startMin - 시작 시간 (분)
               * @param {number} duration - 배치할 시간 (분)
               * @param {string} [locOverride] - 장소 ID 오버라이드
               */
              function clampAndCreate(startMin, duration, locOverride) {
                var endMin = startMin + duration;
                var workEnd = getWorkEndMin();
                if (endMin > workEnd) {
                  // 업무 종료 시간 초과 시 사용자 확인
                  var overflow = endMin - workEnd;
                  var clampedMin = workEnd - startMin;
                  if (clampedMin <= 0) {
                    showToast('업무 종료 시간 이후에는 배치할 수 없습니다.', 'danger');
                    return;
                  }
                  if (!confirm('종료 시간이 ' + minToTime(workEnd) + '을 초과합니다.\n' +
                    minToTime(workEnd) + '까지 ' + clampedMin + '분만 배치하고, 초과 ' + overflow + '분은 줄어든 시간으로 처리됩니다.\n계속하시겠습니까?')) {
                    return;
                  }
                  // 업무 종료 시간까지만 배치, 초과분은 overflow로 전달
                  doCreate(startMin, workEnd, overflow, locOverride);
                } else {
                  doCreate(startMin, endMin, 0, locOverride);
                }
              }

              if (target.type === 'slot') {
                // 시간 슬롯에 드롭: 인접 블록 끝에 스냅하여 배치
                var t = App.snapToBlockEdge(target.el);
                clampAndCreate(t, bMin);
              } else if (target.type === 'month') {
                // 월간뷰에 드롭: 장소/시간 선택 피커 표시 후 배치
                showMonthPlacePicker(locationId, function (result) {
                  if (!result) return;
                  var st = timeToMin(result.startTime);
                  clampAndCreate(st, bMin, result.locationId);
                });
              }
            }

            // 식별자가 2개 이상이면 식별자 선택 피커 표시
            if (testList.length > 1) {
              // 이미 배치된 식별자 조회 (배치됨 표시를 위해)
              api('GET', '/schedule/api/blocks/by-task/' + taskId).then(function (res) {
                var existingBlocks = (res && res.blocks) || [];
                var scheduledIds = [];
                existingBlocks.forEach(function (b) {
                  var ids = b.identifier_ids;
                  if (ids && ids.length) {
                    // 명시적으로 할당된 식별자만 배치된 것으로 간주
                    ids.forEach(function (id) { scheduledIds.push(id); });
                  }
                  // identifier_ids=null은 미분할 블록 — 모두를 배치됨으로 표시하지 않음
                });

                showIdentifierPicker(testList, { scheduledIds: scheduledIds }, function (selected) {
                  if (!selected) return;
                  var allIds = testList.map(function (s) { return typeof s === 'object' ? s.id : s; });
                  var selectedIds = selected.map(function (s) { return typeof s === 'object' ? s.id : s; });
                  var isAll = selectedIds.length === allIds.length;
                  if (isAll) {
                    // 전체 선택 시 identifier_ids = null (미분할 블록)
                    createBlock(null, null);
                  } else {
                    // 부분 선택 시 선택된 식별자들의 시간 합계로 블록 생성
                    var totalMin = 0;
                    selected.forEach(function (s) { totalMin += typeof s === 'object' ? (s.estimated_minutes || 0) : 0; });
                    totalMin = Math.max(totalMin, 1);
                    createBlock(selectedIds, totalMin);
                  }
                });
              }).catch(function () {
                // 폴백: 배치 정보 없이 피커 표시
                showIdentifierPicker(testList, function (selected) {
                  if (!selected) return;
                  createBlock(null, null);
                });
              });
            } else {
              // 식별자 1개 이하: 바로 블록 생성
              createBlock(null, null);
            }
          },
        });
      });
    });
  }

  // =====================================================================
  // 14. 식별자 선택 피커 (큐 드래그 시 분할 배치)
  // =====================================================================
  /**
   * 식별자 선택 팝업을 표시한다.
   * 각 식별자에 체크박스를 표시하며, 이미 배치된 식별자는 '배치됨' 배지와 함께 비활성화 표시된다.
   * @param {Array<Object|string>} testList - 전체 식별자 목록
   * @param {Object} [opts] - 옵션 (또는 2인자 호출 시 callback)
   * @param {Array<string>} [opts.scheduledIds] - 이미 배치된 식별자 ID 목록
   * @param {function} callback - 선택 결과 콜백 (선택된 항목 배열 또는 취소 시 null)
   */
  function showIdentifierPicker(testList, opts, callback) {
    // 구버전 2인자 호출 지원: showIdentifierPicker(list, cb)
    if (typeof opts === 'function') { callback = opts; opts = {}; }
    opts = opts || {};
    // 이미 배치된 식별자 ID를 빠른 조회를 위해 객체로 변환
    var scheduledSet = {};
    (opts.scheduledIds || []).forEach(function (id) { scheduledSet[id] = true; });

    // 기존 피커 제거
    var old = document.getElementById('identifier-picker');
    if (old) old.remove();

    var overlay = document.createElement('div');
    overlay.id = 'identifier-picker';
    overlay.className = 'block-detail-overlay';
    // 각 식별자별 체크박스 행 생성
    var rows = '';
    testList.forEach(function (item, i) {
      var id = typeof item === 'object' ? item.id : item;
      var owners = (typeof item === 'object' && item.owners) ? item.owners : [];
      var mins = typeof item === 'object' ? (item.estimated_minutes || 0) : 0;
      var isScheduled = !!scheduledSet[id];
      // 이미 배치된 식별자는 기본 체크 해제, 미배치는 체크
      var checked = isScheduled ? '' : ' checked';
      var badge = isScheduled
        ? ' <span class="badge bg-secondary" style="font-size:0.65rem;vertical-align:middle">배치됨</span>'
        : '';
      var itemName = (typeof item === 'object' && item.name) ? item.name : '';
      var ownerStr = owners.length ? ' <span class="text-muted">작성: ' + owners.join(', ') + '</span>' : '';
      var nameStr = itemName ? ' <span class="text-muted" style="font-size:0.78rem">- ' + itemName + '</span>' : '';
      rows += '<label class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem;white-space:nowrap' + (isScheduled ? ';opacity:0.55' : '') + '">' +
        '<input type="checkbox" class="form-check-input" value="' + i + '"' + checked + '> ' +
        '<span>' + id + '</span>' + nameStr + ownerStr +
        (mins > 0 ? ' <span class="text-muted">(' + mins + '분)</span>' : '') +
        badge +
        '</label>';
    });
    overlay.innerHTML =
      '<div class="bd-box">' +
        '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">식별자 선택</span></div>' +
          '<button class="bd-x" id="picker-close">&times;</button></div>' +
        '<div class="bd-divider"></div>' +
        '<div style="padding:12px">' +
          '<div class="form-text mb-2">배치할 식별자를 선택하세요</div>' +
          '<div class="d-flex gap-1 mb-2">' +
            '<button type="button" class="btn btn-outline-secondary btn-sm" id="picker-select-all">전체 선택</button>' +
            '<button type="button" class="btn btn-outline-secondary btn-sm" id="picker-deselect-all">전체 해제</button>' +
          '</div>' +
          '<div id="picker-list">' + rows + '</div>' +
          '<button class="btn btn-sm btn-primary w-100 mt-2" id="picker-ok">확인</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    // 전체 선택/해제 버튼
    document.getElementById('picker-select-all').addEventListener('click', function () {
      overlay.querySelectorAll('#picker-list input[type="checkbox"]').forEach(function (cb) { cb.checked = true; });
    });
    document.getElementById('picker-deselect-all').addEventListener('click', function () {
      overlay.querySelectorAll('#picker-list input[type="checkbox"]').forEach(function (cb) { cb.checked = false; });
    });
    // 오버레이 바깥 클릭 시 취소
    overlay.addEventListener('click', function (ev) { if (ev.target === overlay) { document.removeEventListener('keydown', onSpace); overlay.remove(); callback(null); } });
    // 닫기 버튼 클릭 시 취소
    document.getElementById('picker-close').addEventListener('click', function () { document.removeEventListener('keydown', onSpace); overlay.remove(); callback(null); });
    /** 스페이스 키로 확인 버튼 빠른 실행 */
    function onSpace(ev) {
      if (ev.key === ' ') {
        ev.preventDefault();
        document.getElementById('picker-ok').click();
      }
    }
    document.addEventListener('keydown', onSpace);
    // 확인 버튼 클릭 — 체크된 항목 수집
    document.getElementById('picker-ok').addEventListener('click', function () {
      document.removeEventListener('keydown', onSpace);
      var checked = [];
      overlay.querySelectorAll('#picker-list input:checked').forEach(function (cb) {
        checked.push(parseInt(cb.value));
      });
      overlay.remove();
      if (checked.length === 0) { callback(null); return; }
      // 인덱스를 원본 testList 항목으로 변환
      var selected = checked.map(function (i) { return testList[i]; });
      callback(selected);
    });
  }

  // =====================================================================
  // 월간 배치 피커 — 장소 + 시작 시간 선택
  // =====================================================================
  /**
   * 월간뷰에서 블록 배치 시 장소와 시작 시간을 선택하는 팝업을 표시한다.
   * @param {string} defaultLocId - 기본 선택할 장소 ID
   * @param {function} callback - 선택 결과 콜백 ({locationId, startTime} 또는 취소 시 null)
   */
  function showMonthPlacePicker(defaultLocId, callback) {
    // 장소 필터 버튼에서 장소 목록 수집
    var locs = [];
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (b.dataset.locId) {
        var dot = b.querySelector('.loc-filter-dot');
        locs.push({
          id: b.dataset.locId,
          name: b.textContent.trim(),
          color: dot ? (dot.style.background || dot.style.backgroundColor || '#6c757d') : '#6c757d',
        });
      }
    });

    // 필터 버튼이 없으면 API에서 장소 목록 조회
    if (locs.length === 0) {
      api('GET', '/admin/api/locations').then(function (res) {
        var items = res.locations || res || [];
        items.forEach(function (loc) {
          locs.push({ id: loc.id, name: loc.name, color: loc.color || '#6c757d' });
        });
        showPicker(locs);
      }).catch(function () { callback(null); });
      return;
    }
    showPicker(locs);

    /**
     * 장소/시간 선택 피커 팝업을 실제로 생성한다.
     * @param {Array<{id: string, name: string, color: string}>} locations - 장소 목록
     */
    function showPicker(locations) {
      var old = document.getElementById('month-place-picker');
      if (old) old.remove();

      // 장소 드롭다운 옵션 생성
      var locOptions = locations.map(function (loc) {
        var sel = loc.id === defaultLocId ? ' selected' : '';
        return '<option value="' + loc.id + '"' + sel + '>' + loc.name + '</option>';
      }).join('');

      var overlay = document.createElement('div');
      overlay.id = 'month-place-picker';
      overlay.className = 'block-detail-overlay';
      overlay.innerHTML =
        '<div class="bd-box" style="max-width:300px">' +
          '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">배치 설정</span></div>' +
            '<button class="bd-x" id="mpp-close">&times;</button></div>' +
          '<div class="bd-divider"></div>' +
          '<div style="padding:12px">' +
            '<label class="form-label" style="font-size:0.82rem">장소</label>' +
            '<select class="form-select form-select-sm mb-2" id="mpp-location">' +
              '<option value="">선택</option>' + locOptions +
            '</select>' +
            '<label class="form-label" style="font-size:0.82rem">시작 시간</label>' +
            '<input type="time" class="form-control form-control-sm mb-2" id="mpp-time" value="08:30">' +
            '<button class="btn btn-sm btn-primary w-100" id="mpp-ok">배치</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      // 닫기/취소 이벤트
      overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay) { overlay.remove(); callback(null); }
      });
      document.getElementById('mpp-close').addEventListener('click', function () {
        overlay.remove(); callback(null);
      });
      // 배치 버튼 — 입력값 검증 후 콜백 호출
      document.getElementById('mpp-ok').addEventListener('click', function () {
        var locId = document.getElementById('mpp-location').value;
        var time = document.getElementById('mpp-time').value;
        overlay.remove();
        if (!locId) { showToast('장소를 선택하세요.', 'danger'); callback(null); return; }
        if (!time) { showToast('시간을 입력하세요.', 'danger'); callback(null); return; }
        callback({ locationId: locId, startTime: time });
      });
    }
  }

  // =====================================================================
  // 장소 선택 피커 (레거시, 다른 용도로 유지)
  // =====================================================================
  /**
   * 장소 선택 팝업을 표시한다 (버튼 형태).
   * @param {function} callback - 선택 결과 콜백 (장소 ID 또는 취소 시 null)
   */
  function showLocationPicker(callback) {
    var locs = [];
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (b.dataset.locId) {
        var dot = b.querySelector('.loc-filter-dot');
        locs.push({
          id: b.dataset.locId,
          name: b.textContent.trim(),
          color: dot ? (dot.style.background || dot.style.backgroundColor || '#6c757d') : '#6c757d',
        });
      }
    });
    // 필터 버튼이 없으면 API에서 조회
    if (locs.length === 0) {
      api('GET', '/admin/api/locations').then(function (res) {
        var items = res.locations || res || [];
        items.forEach(function (loc) {
          locs.push({ id: loc.id, name: loc.name, color: loc.color || '#6c757d' });
        });
        showPicker(locs);
      }).catch(function () { callback(null); });
      return;
    }
    showPicker(locs);

    /**
     * 장소 버튼 목록 팝업을 실제로 생성한다.
     * @param {Array<{id: string, name: string, color: string}>} locations - 장소 목록
     */
    function showPicker(locations) {
      if (locations.length === 0) { callback(null); return; }
      var old = document.getElementById('location-picker');
      if (old) old.remove();

      var overlay = document.createElement('div');
      overlay.id = 'location-picker';
      overlay.className = 'block-detail-overlay';
      // 각 장소를 버튼으로 표시 (색상 점 + 이름)
      var rows = locations.map(function (loc) {
        return '<button class="btn btn-sm w-100 mb-1 text-start loc-pick-btn" data-loc-id="' + loc.id + '" style="border:2px solid ' + loc.color + ';color:' + loc.color + '">' +
          '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + loc.color + ';margin-right:6px"></span>' +
          loc.name + '</button>';
      }).join('');
      overlay.innerHTML =
        '<div class="bd-box" style="max-width:280px">' +
          '<div class="bd-header"><div class="bd-header-left"><span class="bd-id">장소 선택</span></div>' +
            '<button class="bd-x" id="loc-pick-close">&times;</button></div>' +
          '<div class="bd-divider"></div>' +
          '<div style="padding:12px">' + rows + '</div>' +
        '</div>';
      document.body.appendChild(overlay);

      // 오버레이/버튼 클릭 이벤트
      overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay) { overlay.remove(); callback(null); }
        var btn = ev.target.closest('.loc-pick-btn');
        if (btn) { overlay.remove(); callback(btn.dataset.locId); }
      });
      document.getElementById('loc-pick-close').addEventListener('click', function () {
        overlay.remove(); callback(null);
      });
    }
  }

  App.initQueueDrag = initQueueDrag;
  App.showIdentifierPicker = showIdentifierPicker;
  App.showLocationPicker = showLocationPicker;
})(window.ScheduleApp);
