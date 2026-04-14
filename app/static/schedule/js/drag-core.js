/**
 * 드래그 인프라 모듈 — 드롭 대상 탐색, 고스트 요소, 하이라이트, 장소 가이드.
 * 모든 드래그 동작(블록 이동, 큐 드래그 등)의 기반이 되는 헬퍼 함수들을 제공한다.
 * window.ScheduleApp 네임스페이스에 등록된다.
 */
(function (App) {
  'use strict';

  // =====================================================================
  // 모듈 내부 상태
  // =====================================================================
  /** @type {HTMLElement|null} 현재 표시 중인 주간뷰 장소 가이드 오버레이 */
  var weekGuideEl = null;
  /** @type {Array|null} 캐시된 주간뷰 장소 목록 */
  var weekGuideLocs = null;
  /** @type {HTMLElement|null} 현재 하이라이트된 슬롯 요소 */
  var highlighted = null;
  /** @type {HTMLElement|null} 현재 하이라이트된 장소 영역 요소 */
  var highlightedZone = null;

  // utils.js에서 가져온 단축 참조
  // GRID_MINUTES는 App.GRID_MINUTES를 직접 참조 (initAll에서 갱신되므로 캡처하지 않음)
  var SLOT_HEIGHT = App.SLOT_HEIGHT;
  var isReadonly = App.isReadonly;

  // =====================================================================
  // 블록 가시성 토글 — elementFromPoint가 시간 슬롯을 인식하도록 블록 숨기기
  // =====================================================================
  /**
   * 모든 스케줄 블록의 포인터 이벤트를 비활성화한다.
   * 드래그 중에 마우스 아래의 시간 슬롯을 감지하기 위해 사용한다.
   */
  function hideAllBlocks() {
    document.querySelectorAll('.schedule-block, .month-block-item').forEach(function (b) {
      b.style.pointerEvents = 'none';
    });
  }

  /**
   * hideAllBlocks()로 비활성화한 포인터 이벤트를 복원한다.
   */
  function showAllBlocks() {
    document.querySelectorAll('.schedule-block, .month-block-item').forEach(function (b) {
      b.style.pointerEvents = '';
    });
  }

  // =====================================================================
  // 주간뷰 장소 가이드 — 드래그 중 장소 영역 표시
  // =====================================================================
  /**
   * DOM에서 장소 필터 버튼을 읽어 장소 목록을 반환한다.
   * @returns {Array<{id: string, name: string, color: string}>} 장소 목록
   */
  function getLocations() {
    var locs = [];
    // 1차: 장소 ID와 이름 수집
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (b.dataset.locId) locs.push({ id: b.dataset.locId, name: b.textContent.trim(), color: '' });
    });
    // 2차: 각 장소의 색상 점(dot) 요소에서 색상 추출
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (!b.dataset.locId) return;
      var dot = b.querySelector('.loc-filter-dot');
      for (var i = 0; i < locs.length; i++) {
        if (locs[i].id === b.dataset.locId && dot) {
          locs[i].color = dot.style.background || dot.style.backgroundColor || '#94a3b8';
          break;
        }
      }
    });
    return locs;
  }

  /**
   * 주간뷰 장소 가이드에 표시할 장소 목록을 반환한다.
   * 필터에서 선택된 장소만 포함하며, 결과를 캐시한다.
   * @returns {Array<{id: string, name: string, color: string}>} 활성화된 장소 목록
   */
  function getWeekGuideLocs() {
    if (weekGuideLocs) return weekGuideLocs;
    var locs = getLocations();
    if (locs.length === 0) return locs;
    // "전체" 버튼이 활성화 상태인지 확인
    var allBtn = document.querySelector('.loc-filter-btn.active[data-loc-id=""]');
    if (!allBtn) {
      // "전체"가 아니면 활성화된 장소만 필터링
      var activeIds = {};
      document.querySelectorAll('.loc-filter-btn.active[data-loc-id]').forEach(function (b) {
        if (b.dataset.locId) activeIds[b.dataset.locId] = true;
      });
      if (Object.keys(activeIds).length > 0) {
        locs = locs.filter(function (l) { return activeIds[l.id]; });
      }
    }
    weekGuideLocs = locs;
    return locs;
  }

  /**
   * 주간뷰 특정 컬럼에 장소 가이드 오버레이를 생성/표시한다.
   * 장소가 2개 이상일 때만 표시한다.
   * @param {HTMLElement} slotsEl - 주간뷰의 .week-day-slots 요소
   * @returns {HTMLElement|null} 생성된 오버레이 요소, 또는 불필요 시 null
   */
  function ensureWeekGuide(slotsEl) {
    // 이미 같은 컬럼에 표시 중이면 재사용
    if (weekGuideEl && weekGuideEl.parentNode === slotsEl) return weekGuideEl;
    // 이전 컬럼의 가이드 제거
    if (weekGuideEl) { weekGuideEl.remove(); weekGuideEl = null; }

    var locs = getWeekGuideLocs();
    // 장소가 1개 이하면 가이드 불필요
    if (locs.length <= 1) return null;

    // 오버레이 생성: flex 레이아웃으로 장소 영역을 균등 분할
    var overlay = document.createElement('div');
    overlay.className = 'week-loc-guide-overlay';
    overlay.style.cssText = 'position:absolute;top:0;left:0;right:0;bottom:0;z-index:8;pointer-events:none;display:flex;';
    for (var i = 0; i < locs.length; i++) {
      // 각 장소별 영역(zone) 생성
      var zone = document.createElement('div');
      zone.className = 'week-loc-guide-zone';
      zone.dataset.locationId = locs[i].id;
      zone.style.cssText = 'flex:1;border-right:1px dashed ' + locs[i].color + ';position:relative;';
      if (i === locs.length - 1) zone.style.borderRight = 'none'; // 마지막 영역은 우측 테두리 없음
      // 장소 이름 라벨
      var label = document.createElement('div');
      label.className = 'week-loc-guide-label';
      label.textContent = locs[i].name;
      label.style.cssText = 'position:sticky;top:0;font-size:0.6rem;font-weight:600;color:' + locs[i].color +
        ';text-align:center;padding:2px 0;background:rgba(255,255,255,0.85);border-bottom:2px solid ' + locs[i].color + ';white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
      zone.appendChild(label);
      overlay.appendChild(zone);
    }
    slotsEl.appendChild(overlay);
    weekGuideEl = overlay;
    return overlay;
  }

  /**
   * 주간뷰 장소 가이드 표시 (현재는 no-op; 컬럼별 hover 시 표시로 변경됨).
   */
  function showWeekLocationGuides() { /* no-op: guides are now shown per-column on hover */ }

  /**
   * 주간뷰 장소 가이드 오버레이를 제거한다.
   */
  function hideWeekLocationGuides() {
    if (weekGuideEl) { weekGuideEl.remove(); weekGuideEl = null; }
  }

  /**
   * 주간뷰에서 마우스 X 좌표를 기준으로 해당 장소 ID를 결정한다.
   * 슬롯에 직접 locationId가 있으면(일간뷰) 그것을 사용하고,
   * 없으면(주간뷰) 장소 가이드 오버레이의 영역 위치로 결정한다.
   * @param {number} x - 마우스 clientX 좌표
   * @param {HTMLElement} slot - 대상 시간 슬롯 요소
   * @returns {string} 결정된 장소 ID (없으면 빈 문자열)
   */
  function resolveWeekLocation(x, slot) {
    // 일간뷰는 슬롯 자체에 locationId가 있음
    if (slot.dataset.locationId) return slot.dataset.locationId;
    var slotsEl = slot.closest('.week-day-slots');
    if (!slotsEl) return '';
    var overlay = ensureWeekGuide(slotsEl);
    if (!overlay) return '';
    var zones = overlay.querySelectorAll('.week-loc-guide-zone');
    if (zones.length === 0) return '';
    // 마우스 X 위치를 기반으로 영역 인덱스 계산
    var rect = slotsEl.getBoundingClientRect();
    var relX = x - rect.left;
    var zoneWidth = rect.width / zones.length;
    var idx = Math.max(0, Math.min(zones.length - 1, Math.floor(relX / zoneWidth)));
    return zones[idx].dataset.locationId || '';
  }

  // =====================================================================
  // 커서 아래의 드롭 대상 탐색
  // =====================================================================
  /**
   * 화면 좌표에서 드롭 가능한 대상 요소를 찾는다.
   * 시간 슬롯, 월간뷰 셀, 큐 영역 순서로 탐색한다.
   * @param {number} x - clientX 좌표
   * @param {number} y - clientY 좌표
   * @returns {{type: string, date?: string, time?: string, locationId?: string, el: HTMLElement}|null}
   *   - type='slot': 시간 슬롯 (date, time, locationId 포함)
   *   - type='month': 월간뷰 셀 (date 포함)
   *   - type='queue': 큐 영역
   *   - null: 유효한 대상 없음
   */
  function findTarget(x, y) {
    var el = document.elementFromPoint(x, y);
    if (!el) return null;
    // 시간 슬롯 (일간뷰/주간뷰)
    var slot = el.closest('.time-slot');
    if (slot && slot.dataset.date && slot.dataset.time) {
      var locId = slot.dataset.locationId || resolveWeekLocation(x, slot);
      return { type: 'slot', date: slot.dataset.date, time: slot.dataset.time, locationId: locId, el: slot };
    }
    // 월간뷰 셀
    var cell = el.closest('.month-day-cell[data-date]');
    if (cell) {
      return { type: 'month', date: cell.dataset.date, el: cell };
    }
    // 태스크 큐 영역
    var queue = el.closest('#task-queue');
    if (queue) {
      return { type: 'queue', el: queue };
    }
    return null;
  }

  // =====================================================================
  // 고스트(Ghost) 요소 — 드래그 중 마우스를 따라다니는 시각적 표시
  // =====================================================================
  /**
   * 드래그 중 마우스를 따라다니는 고스트 요소를 생성한다.
   * @param {string} text - 표시할 텍스트
   * @param {string} [color='#0d6efd'] - 배경색
   * @param {number} [w=120] - 너비 (px)
   * @param {number} [h] - 높이 (px, 미지정 시 자동)
   * @returns {HTMLElement} 생성된 고스트 요소
   */
  function createGhost(text, color, w, h) {
    var g = document.createElement('div');
    g.textContent = text;
    g.style.cssText =
      'position:fixed;z-index:9999;pointer-events:none;opacity:0.8;' +
      'padding:4px 8px;border-radius:4px;font-size:0.75rem;color:#fff;' +
      'overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.3);' +
      'background:' + (color || '#0d6efd') + ';' +
      'width:' + (w || 120) + 'px;' +
      (h ? 'height:' + h + 'px;' : '');
    document.body.appendChild(g);
    return g;
  }

  // =====================================================================
  // 하이라이트 — 드롭 대상에 시각적 표시
  // =====================================================================
  /**
   * 드롭 대상 요소에 하이라이트(drag-over 클래스)를 적용한다.
   * 주간뷰에서 장소 가이드 영역이 있으면 해당 영역도 하이라이트한다.
   * @param {{type: string, locationId?: string, el: HTMLElement}|null} target - 드롭 대상 정보
   * @param {number} x - 마우스 clientX 좌표
   */
  function setHighlight(target, x) {
    clearHighlight();
    if (!target || !target.el) {
      // 커서가 그리드 밖으로 나간 경우 — 가이드 제거
      hideWeekLocationGuides();
      return;
    }
    // 주간뷰에서 장소 가이드가 있는 경우: 전체 슬롯 대신 해당 장소 영역만 하이라이트
    if (target.type === 'slot' && target.locationId && !target.el.dataset.locationId) {
      var slotsEl = target.el.closest('.week-day-slots');
      if (slotsEl) {
        var overlay = slotsEl.querySelector('.week-loc-guide-overlay');
        if (overlay) {
          var zones = overlay.querySelectorAll('.week-loc-guide-zone');
          for (var i = 0; i < zones.length; i++) {
            if (zones[i].dataset.locationId === target.locationId) {
              zones[i].classList.add('week-loc-guide-active');
              highlightedZone = zones[i];
              break;
            }
          }
        }
      }
    } else {
      // 주간 슬롯이 아닌 경우 — 이전 컬럼의 가이드 제거
      hideWeekLocationGuides();
    }
    target.el.classList.add('drag-over');
    highlighted = target.el;
  }

  /**
   * 현재 적용된 하이라이트를 모두 제거한다.
   */
  function clearHighlight() {
    if (highlighted) highlighted.classList.remove('drag-over');
    highlighted = null;
    if (highlightedZone) highlightedZone.classList.remove('week-loc-guide-active');
    highlightedZone = null;
  }

  // =====================================================================
  // 범용 드래그 헬퍼 — 마우스 드래그 동작의 공통 로직
  // =====================================================================
  /**
   * 마우스 드래그 동작을 시작한다. 5px 이상 이동해야 드래그로 인식한다.
   * 드래그 중 고스트 표시, 블록 숨기기, 대상 하이라이트를 처리하고,
   * 마우스 업 시 onDrop 콜백을 호출한다.
   * @param {MouseEvent} e - mousedown 이벤트
   * @param {Object} opts - 드래그 옵션
   * @param {HTMLElement} [opts.sourceEl] - 드래그 원본 요소 (반투명 처리용)
   * @param {string} opts.ghostText - 고스트에 표시할 텍스트
   * @param {string} [opts.ghostColor] - 고스트 배경색
   * @param {number} [opts.ghostWidth] - 고스트 너비
   * @param {number} [opts.ghostHeight] - 고스트 높이
   * @param {function} opts.onDrop - 드롭 시 호출되는 콜백, target 객체를 인자로 받음
   */
  function startDrag(e, opts) {
    if (e.button !== 0) return; // 좌클릭만 허용
    if (isReadonly()) return;   // 읽기 전용 모드에서는 드래그 불가
    e.preventDefault();

    var startX = e.clientX, startY = e.clientY;
    var dragging = false;
    var ghost = null;

    /** 마우스 이동 핸들러 */
    function onMove(ev) {
      ev.preventDefault();
      var dx = ev.clientX - startX, dy = ev.clientY - startY;
      // 5px 미만 이동은 드래그로 인식하지 않음 (클릭과 구분)
      if (!dragging && Math.abs(dx) + Math.abs(dy) < 5) return;

      if (!dragging) {
        // 최초 드래그 시작 시 초기화
        dragging = true;
        ghost = createGhost(opts.ghostText, opts.ghostColor, opts.ghostWidth, opts.ghostHeight);
        hideAllBlocks();          // 블록 숨겨서 아래 슬롯 감지 가능하게
        showWeekLocationGuides(); // 장소 가이드 표시
        if (opts.sourceEl) opts.sourceEl.style.opacity = '0.3'; // 원본 반투명 처리
        document.body.style.userSelect = 'none';  // 텍스트 선택 방지
        document.body.style.cursor = 'grabbing';
      }

      // 현재 커서 아래의 드롭 대상 탐색 및 하이라이트
      var target = findTarget(ev.clientX, ev.clientY);
      setHighlight(target, ev.clientX);

      // 고스트를 마우스 위치에 맞춰 이동 (슬롯 위에서는 그리드에 스냅)
      var ghostLeft = ev.clientX - (ghost.offsetWidth / 2);
      var ghostTop = ev.clientY - 10;
      if (target && target.type === 'slot' && target.el) {
        // 슬롯 컬럼의 상대 위치에서 그리드 스냅 계산
        var slotsContainer = target.el.closest('.week-day-slots, .day-loc-body');
        if (slotsContainer) {
          var containerRect = slotsContainer.getBoundingClientRect();
          var slotH = App.SLOT_HEIGHT || 24;
          var relY = ev.clientY - containerRect.top + slotsContainer.scrollTop;
          var snappedSlot = Math.round(relY / slotH);
          ghostTop = containerRect.top - slotsContainer.scrollTop + (snappedSlot * slotH);
          ghostLeft = containerRect.left;
          ghost.style.width = containerRect.width + 'px';
        }
      }
      ghost.style.left = ghostLeft + 'px';
      ghost.style.top = ghostTop + 'px';
    }

    /** 마우스 업 핸들러 — 드래그 종료 처리 */
    function onUp(ev) {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);

      var target = null;
      if (dragging) {
        target = findTarget(ev.clientX, ev.clientY);
      }

      // 드래그 상태 정리
      clearHighlight();
      hideWeekLocationGuides();
      weekGuideLocs = null; // 장소 캐시 초기화
      showAllBlocks();
      if (ghost) ghost.remove();
      if (opts.sourceEl) opts.sourceEl.style.opacity = '';
      document.body.style.userSelect = '';
      document.body.style.cursor = '';

      // 드래그가 시작되지 않았으면 (클릭이면) 아무것도 하지 않음
      if (!dragging) return;

      // 유효한 대상에 드롭된 경우 콜백 호출
      if (target) opts.onDrop(target);
    }

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  // App 네임스페이스에 등록
  App.hideAllBlocks = hideAllBlocks;
  App.showAllBlocks = showAllBlocks;
  App.getLocations = getLocations;
  App.getWeekGuideLocs = getWeekGuideLocs;
  App.ensureWeekGuide = ensureWeekGuide;
  App.resolveWeekLocation = resolveWeekLocation;
  App.showWeekLocationGuides = showWeekLocationGuides;
  App.hideWeekLocationGuides = hideWeekLocationGuides;
  App.findTarget = findTarget;
  App.createGhost = createGhost;
  App.setHighlight = setHighlight;
  App.clearHighlight = clearHighlight;
  App.startDrag = startDrag;
})(window.ScheduleApp);
