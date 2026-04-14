/**
 * 스케줄링 앱 공용 유틸리티 함수 모듈.
 * window.ScheduleApp 네임스페이스에 등록됨.
 * 토스트, API 호출, 시간 변환, 소프트 리로드 등 앱 전체에서 사용하는 기반 함수를 제공한다.
 */
window.ScheduleApp = window.ScheduleApp || {};
(function (App) {
  'use strict';

  // =====================================================================
  // 상수 정의
  // =====================================================================
  /** @type {number} 그리드 스냅 간격 (분 단위, 기본값 15분) */
  App.GRID_MINUTES = window.GRID_INTERVAL || 15;
  /** @type {number} 시간 슬롯 1칸의 픽셀 높이 */
  App.SLOT_HEIGHT = 24;

  // =====================================================================
  // 토스트 알림
  // =====================================================================
  /**
   * 화면 우하단에 토스트 메시지를 표시한다.
   * 4초 후 자동으로 사라진다.
   * @param {string} msg - 표시할 메시지 텍스트
   * @param {string} [type='info'] - Bootstrap 색상 클래스 (예: 'success', 'danger', 'info')
   */
  function showToast(msg, type) {
    // 토스트 컨테이너가 없으면 동적으로 생성
    var c = document.getElementById('toast-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-container';
      c.className = 'position-fixed bottom-0 end-0 p-3';
      c.style.zIndex = '1100';
      document.body.appendChild(c);
    }
    // 토스트 요소 생성 및 삽입
    var t = document.createElement('div');
    t.className = 'toast align-items-center text-bg-' + (type || 'info') + ' border-0 show';
    t.innerHTML = '<div class="d-flex"><div class="toast-body">' + msg +
      '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    c.appendChild(t);
    // 4초 후 자동 제거
    setTimeout(function () { t.remove(); }, 4000);
  }
  App.showToast = showToast;

  // =====================================================================
  // API 호출 래퍼
  // =====================================================================
  /**
   * JSON 기반 API 요청을 보내고 응답을 파싱하여 반환한다.
   * HTTP 오류 시 Error를 throw한다.
   * @param {string} method - HTTP 메서드 ('GET', 'POST', 'PUT', 'DELETE' 등)
   * @param {string} url - 요청 URL
   * @param {Object} [data] - 전송할 JSON 본문 데이터 (없으면 undefined)
   * @returns {Promise<Object>} 파싱된 JSON 응답 객체
   */
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
  // 잔여 시간 확인 (블록 배치 후)
  // =====================================================================
  /**
   * 특정 태스크의 잔여 시간(분)을 서버에서 조회한다.
   * @param {string} taskId - 태스크 ID
   * @returns {Promise<number>} 잔여 시간 (분), 오류 시 0
   */
  function getTaskRemaining(taskId) {
    return api('GET', '/tasks/api/' + taskId).then(function (res) {
      return res.task ? res.task.remaining_minutes : 0;
    }).catch(function () { return 0; });
  }
  App.getTaskRemaining = getTaskRemaining;

  /**
   * 블록 배치 후 잔여 시간이 증가했는지 확인하고, 증가 시 알림을 표시한다.
   * 잔여 시간이 증가했다는 것은 배치 시 시간이 잘린(cut) 것을 의미한다.
   * @param {string} taskId - 태스크 ID
   * @param {string} procedureId - 절차 식별자 (알림 표시용)
   * @param {number} prevRemaining - 배치 전 잔여 시간 (분)
   * @returns {Promise<boolean>} 알림 표시 여부
   */
  function checkRemainingAfterPlace(taskId, procedureId, prevRemaining) {
    return api('GET', '/tasks/api/' + taskId).then(function (res) {
      var task = res.task;
      if (!task) return false;
      var remaining = task.remaining_minutes;
      // 잔여 시간이 이전보다 증가한 경우에만 알림 (시간이 잘렸음을 의미)
      if (remaining > 0 && remaining > (prevRemaining || 0)) {
        return showRemainingAlert(procedureId || task.doc_name || task.doc_id, remaining);
      }
      return false;
    }).catch(function () { return false; });
  }
  App.checkRemainingAfterPlace = checkRemainingAfterPlace;

  /**
   * 잔여 시간 경고 오버레이를 화면에 표시한다.
   * 사용자가 확인 버튼을 누르거나 오버레이 바깥을 클릭하면 닫힌다.
   * @param {string} procedureId - 절차 식별자 (알림에 표시)
   * @param {number} remaining - 잔여 시간 (분)
   * @returns {Promise<boolean>} 닫힐 때 true로 resolve
   */
  function showRemainingAlert(procedureId, remaining) {
    return new Promise(function (resolve) {
      // 기존 알림이 있으면 제거
      var old = document.getElementById('remaining-alert');
      if (old) old.remove();

      // 오버레이 및 알림 박스 생성
      var overlay = document.createElement('div');
      overlay.id = 'remaining-alert';
      overlay.className = 'remaining-alert-overlay';
      overlay.innerHTML =
        '<div class="remaining-alert-box">' +
          '<div class="remaining-alert-icon"><i class="bi bi-exclamation-triangle-fill"></i></div>' +
          '<div class="remaining-alert-title">시험이 당일에 완료되지 않습니다</div>' +
          '<div class="remaining-alert-body">' +
            '<strong>' + procedureId + '</strong> 항목의 잔여 시간 <strong>' + remaining + '분</strong>이 ' +
            '시험 큐에 남아있습니다.<br>추가 일정 배치가 필요합니다.' +
          '</div>' +
          '<button class="remaining-alert-btn" id="remaining-alert-close">확인</button>' +
        '</div>';

      document.body.appendChild(overlay);

      /** 알림 닫기 핸들러 */
      function close() {
        overlay.remove();
        resolve(true);
      }
      document.getElementById('remaining-alert-close').addEventListener('click', close);
      // 오버레이 바깥 영역 클릭 시에도 닫기
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) close();
      });
    });
  }
  App.showRemainingAlert = showRemainingAlert;

  // =====================================================================
  // 시간 관련 유틸리티 함수
  // =====================================================================

  /**
   * 숫자를 2자리 문자열로 변환한다 (앞에 0 채움).
   * @param {number} n - 변환할 숫자
   * @returns {string} 2자리 문자열 (예: 5 → '05')
   */
  function pad(n) { return String(n).padStart(2, '0'); }

  /**
   * 'HH:MM' 형식의 시간 문자열을 자정 기준 분(minute) 값으로 변환한다.
   * @param {string} t - 시간 문자열 (예: '09:30')
   * @returns {number} 분 값 (예: 570)
   */
  function timeToMin(t) { var p = t.split(':'); return +p[0] * 60 + +p[1]; }

  /**
   * 자정 기준 분 값을 'HH:MM' 형식 문자열로 변환한다.
   * @param {number} m - 분 값 (예: 570)
   * @returns {string} 시간 문자열 (예: '09:30')
   */
  function minToTime(m) { return pad(Math.floor(m / 60)) + ':' + pad(m % 60); }

  /**
   * 분 값을 GRID_MINUTES 단위로 반올림(스냅)한다.
   * @param {number} m - 원본 분 값
   * @returns {number} 그리드에 스냅된 분 값
   */
  function snapMin(m) { return Math.round(m / App.GRID_MINUTES) * App.GRID_MINUTES; }

  /**
   * 시작~종료 사이의 실제 업무 시간(분)을 계산한다.
   * 휴식 시간(SCHEDULE_BREAKS)을 제외한다.
   * @param {number} startMin - 시작 시간 (분)
   * @param {number} endMin - 종료 시간 (분)
   * @returns {number} 휴식 제외 업무 시간 (분)
   */
  function workMinutes(startMin, endMin) {
    var breaks = window.SCHEDULE_BREAKS || [];
    var breakMin = 0;
    for (var i = 0; i < breaks.length; i++) {
      var bs = timeToMin(breaks[i].start);
      var be = timeToMin(breaks[i].end);
      // 구간 겹침(overlap) 계산
      var ovStart = Math.max(startMin, bs);
      var ovEnd = Math.min(endMin, be);
      if (ovStart < ovEnd) breakMin += ovEnd - ovStart;
    }
    return Math.max(0, endMin - startMin - breakMin);
  }

  /**
   * 드롭 대상 슬롯에서 최적의 시작 시간(분)을 결정한다.
   * 같은 슬롯 내에 그리드가 아닌 시간에 끝나는 블록이 있으면 그 끝 시간에 스냅한다.
   * (인접 블록 사이에 빈틈이 생기지 않도록 하기 위함)
   * 그렇지 않으면 기본 그리드 스냅 시간을 반환한다.
   * @param {HTMLElement} targetSlot - 드롭 대상 time-slot 요소
   * @returns {number} 최적 시작 시간 (분)
   */
  function snapToBlockEdge(targetSlot) {
    var gridMin = App.GRID_MINUTES;
    // 슬롯의 시간을 그리드 단위로 스냅
    var snapT = snapMin(timeToMin(targetSlot.dataset.time));
    var nextGrid = snapT + gridMin;
    var best = snapT;
    // 해당 슬롯이 속한 컨테이너 내의 모든 블록 검사
    var container = targetSlot.closest('.day-loc-body, .week-day-slots');
    if (!container) return best;
    container.querySelectorAll('.schedule-block[data-end-time]').forEach(function (b) {
      var endMin = timeToMin(b.dataset.endTime);
      // 현재 그리드~다음 그리드 사이에 끝나는 블록이 있으면 그 끝 시간 사용
      if (endMin > snapT && endMin <= nextGrid && endMin > best) {
        best = endMin;
      }
    });
    return best;
  }

  /**
   * 시작 시간(분)과 작업 시간(분)으로 휴식 포함 총 소요 시간(분)을 계산한다.
   * adjust_end_for_breaks의 JS 버전.
   * @param {number} startMin - 시작 시간 (분)
   * @param {number} durationMin - 순수 작업 시간 (분)
   * @returns {number} 휴식 포함 총 소요 시간 (분, 슬롯 기준)
   */
  function adjustedDuration(startMin, durationMin) {
    var breaks = window.SCHEDULE_BREAKS || [];
    // 휴식 구간을 시작 시간 순으로 정렬
    var sorted = breaks.map(function (b) { return { s: timeToMin(b.start), e: timeToMin(b.end) }; })
      .filter(function (b) { return b.e > b.s; }) // 유효한 휴식만
      .sort(function (a, b) { return a.s - b.s; });
    var current = startMin;
    var remaining = durationMin;
    for (var i = 0; i < sorted.length && remaining > 0; i++) {
      var bs = sorted[i].s, be = sorted[i].e;
      if (be <= current) continue;
      if (bs <= current) { current = be; continue; }
      var available = bs - current;
      if (available >= remaining) { current += remaining; remaining = 0; }
      else { remaining -= available; current = be; }
    }
    if (remaining > 0) current += remaining;
    return current - startMin;
  }

  App.pad = pad;
  App.timeToMin = timeToMin;
  App.minToTime = minToTime;
  App.snapMin = snapMin;
  App.snapToBlockEdge = snapToBlockEdge;
  App.workMinutes = workMinutes;
  App.adjustedDuration = adjustedDuration;

  // =====================================================================
  // 소프트 리로드 — 전체 페이지 새로고침 없이 메인 콘텐츠만 교체
  // =====================================================================
  /**
   * 현재 페이지를 fetch로 다시 불러와 <main> 영역만 교체한다.
   * 인라인 스크립트도 재실행하며, 실패 시 전체 페이지 새로고침으로 폴백한다.
   * @returns {Promise<void>}
   */
  function softReload() {
    return fetch(location.href).then(function (r) { return r.text(); }).then(function (html) {
      var parser = new DOMParser();
      var doc = parser.parseFromString(html, 'text/html');
      var newMain = doc.querySelector('main');
      var oldMain = document.querySelector('main');
      if (newMain && oldMain) {
        oldMain.innerHTML = newMain.innerHTML;
        // 인라인 스크립트 재실행 (예: 장소 필터 초기화)
        oldMain.querySelectorAll('script').forEach(function (old) {
          var s = document.createElement('script');
          s.textContent = old.textContent;
          old.parentNode.replaceChild(s, old);
        });
        // 모든 이벤트 핸들러 재등록
        App.initAll();
      } else {
        location.reload();
      }
    }).catch(function () {
      location.reload();
    });
  }
  App.softReload = softReload;

  // =====================================================================
  // 읽기 전용 모드 확인
  // =====================================================================
  /**
   * 현재 페이지가 읽기 전용 모드인지 확인한다.
   * body에 'readonly-mode' 클래스가 있으면 읽기 전용이다.
   * @returns {boolean} 읽기 전용이면 true
   */
  function isReadonly() {
    return document.body.classList.contains('readonly-mode');
  }
  App.isReadonly = isReadonly;

  // =====================================================================
  // 전역 Esc 키 처리 — 최상위 오버레이 닫기
  // =====================================================================
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    // DOM 순서상 마지막(=최상위) 오버레이를 찾아 닫기
    var overlays = document.querySelectorAll(
      '.block-detail-overlay, .remaining-alert-overlay, .memo-modal-backdrop'
    );
    if (!overlays.length) return;
    var top = overlays[overlays.length - 1];
    // 닫기 버튼이 있으면 클릭, 없으면 직접 제거
    var closeBtn = top.querySelector('.bd-x, #remaining-alert-close, #memo-cancel, #confirm-modal-cancel');
    if (closeBtn) {
      closeBtn.click();
    } else {
      top.remove();
    }
  });

  // Esc 키로 컨텍스트 메뉴도 닫기
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var menu = document.getElementById('block-context-menu');
    if (menu) menu.remove();
  });

})(window.ScheduleApp);
