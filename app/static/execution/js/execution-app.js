/**
 * 시험 실행 페이지 — 블록/식별자 로드 + 시작/완료/취소/코멘트 처리
 */
(function () {
  'use strict';

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

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── 날짜 피커 ──
  var datePicker = document.getElementById('exec-date-picker');
  if (datePicker) {
    datePicker.addEventListener('change', function () {
      window.location.href = '/execution/?date=' + datePicker.value;
    });
  }

  // ── 데이터 로드 + 렌더링 ──
  function load() {
    api('GET', '/execution/api/day?date=' + EXEC_DATE).then(function (data) {
      renderSummary(data.summary);
      renderBlocks(data.blocks);
    }).catch(function (err) {
      document.getElementById('exec-blocks').innerHTML =
        '<div class="exec-empty"><i class="bi bi-exclamation-circle"></i><p>' + err.message + '</p></div>';
    });
  }

  function renderSummary(s) {
    var pct = s.total > 0 ? Math.round(s.completed / s.total * 100) : 0;
    document.getElementById('exec-summary').innerHTML =
      '<div class="exec-summary-counts">' +
        '<span>전체 ' + s.total + '</span>' +
        '<span style="color:#16a34a">완료 ' + s.completed + '</span>' +
        '<span style="color:#2563eb">진행 ' + s.in_progress + '</span>' +
        '<span style="color:#6b7280">대기 ' + s.pending + '</span>' +
        '<span style="color:#16a34a">PASS ' + s.total_pass + '</span>' +
        '<span style="color:#dc2626">FAIL ' + s.total_fail + '</span>' +
      '</div>' +
      '<div class="exec-progress"><div class="exec-progress-bar" style="width:' + pct + '%"></div></div>';
  }

  function renderBlocks(blocks) {
    var container = document.getElementById('exec-blocks');
    if (!blocks.length) {
      container.innerHTML = '<div class="exec-empty"><i class="bi bi-calendar-x"></i><p>배치된 시험이 없습니다</p></div>';
      return;
    }
    var html = '';
    blocks.forEach(function (b) {
      html += '<div class="exec-block">' +
        '<div class="exec-block-header">' +
          '<div>' +
            '<div class="exec-block-title">' + escapeHtml(b.doc_name) + '</div>' +
            '<div class="exec-block-meta">' + b.start_time + '–' + b.end_time +
              (b.location_name ? ' @ ' + escapeHtml(b.location_name) : '') +
              ' | 담당: ' + (b.assignee_names.length ? escapeHtml(b.assignee_names.join(', ')) : '-') +
            '</div>' +
          '</div>' +
        '</div>';

      b.identifiers.forEach(function (id) {
        html += renderIdentifier(b, id);
      });

      html += '</div>';
    });
    container.innerHTML = html;
    bindEvents();
  }

  function renderIdentifier(block, id) {
    var ex = id.execution;
    var status = ex ? ex.status : 'pending';
    var statusLabel = { pending: '미시험', in_progress: '진행중', completed: '완료' }[status];
    var statusClass = 'exec-status-' + status;

    var html = '<div class="exec-id-row" data-block-id="' + block.block_id + '" data-identifier-id="' + id.id + '" data-task-id="' + block.task_id + '" data-doc-name="' + escapeHtml(block.doc_name) + '">';

    // 헤더
    html += '<div class="exec-id-header">' +
      '<div>' +
        '<span class="exec-id-name">' + id.id + '</span>' +
        ' <span class="exec-id-info">' + escapeHtml(id.name) + ' | ' + id.estimated_minutes + '분 | 작성: ' + (id.owners.length ? escapeHtml(id.owners.join(', ')) : '-') + '</span>' +
      '</div>' +
      '<span class="exec-status-badge ' + statusClass + '">' + statusLabel + '</span>' +
    '</div>';

    html += '<div class="exec-id-body">';

    if (status === 'pending') {
      // 미시험 — 시험 시작 버튼
      html += '<div class="exec-actions">' +
        '<button class="btn btn-sm btn-primary btn-exec-start">시험 시작</button>' +
      '</div>';

    } else if (status === 'in_progress') {
      // 진행중 — 시작시간 표시 + PASS/FAIL 입력 + 특이사항/조치 + 결과 저장
      html += '<div class="exec-result-display">시작: ' + (ex.started_at || '') + '</div>';
      html += '<div class="exec-field-row"><label>PASS</label><input type="number" class="form-control form-control-sm exec-pass" value="' + (ex.pass_count || 0) + '" min="0" style="width:80px">';
      html += '<label>FAIL</label><input type="number" class="form-control form-control-sm exec-fail" value="' + (ex.fail_count || 0) + '" min="0" style="width:80px"></div>';
      html += '<div class="exec-field-row"><label>특이사항</label><textarea class="form-control form-control-sm exec-comment" rows="1">' + escapeHtml(ex.comment) + '</textarea></div>';
      html += '<div class="exec-field-row"><label>조치사항</label><textarea class="form-control form-control-sm exec-action" rows="1">' + escapeHtml(ex.action) + '</textarea></div>';
      html += '<div class="exec-actions">' +
        '<button class="btn btn-sm btn-success btn-exec-complete" data-ex-id="' + ex.id + '">결과 저장</button>' +
        '<button class="btn btn-sm btn-outline-secondary btn-exec-cancel" data-ex-id="' + ex.id + '">시작 취소</button>' +
      '</div>';

    } else if (status === 'completed') {
      // 완료 — 결과 표시 + 특이사항/조치 수정
      html += '<div class="exec-result-display">' +
        '<span style="color:#16a34a;font-weight:600">PASS ' + ex.pass_count + '</span> / ' +
        '<span style="color:#dc2626;font-weight:600">FAIL ' + ex.fail_count + '</span>' +
        ' (' + (ex.started_at || '') + ' ~ ' + (ex.completed_at || '') + ')' +
      '</div>';
      html += '<div class="exec-field-row"><label>특이사항</label><textarea class="form-control form-control-sm exec-comment" rows="1">' + escapeHtml(ex.comment) + '</textarea></div>';
      html += '<div class="exec-field-row"><label>조치사항</label><textarea class="form-control form-control-sm exec-action" rows="1">' + escapeHtml(ex.action) + '</textarea></div>';
      html += '<div class="exec-actions">' +
        '<button class="btn btn-sm btn-outline-primary btn-exec-save-comment" data-ex-id="' + ex.id + '">저장</button>' +
      '</div>';
    }

    html += '</div></div>';
    return html;
  }

  // ── 이벤트 바인딩 ──
  function bindEvents() {
    // 시험 시작
    document.querySelectorAll('.btn-exec-start').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var row = btn.closest('.exec-id-row');
        var testerName = prompt('시험자 이름을 입력하세요:');
        if (!testerName) return;
        api('POST', '/execution/api/start', {
          block_id: row.dataset.blockId,
          task_id: row.dataset.taskId,
          doc_name: row.dataset.docName,
          identifier_id: row.dataset.identifierId,
          tester_name: testerName,
        }).then(function () { load(); })
          .catch(function (err) { alert(err.message); });
      });
    });

    // 결과 저장
    document.querySelectorAll('.btn-exec-complete').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var row = btn.closest('.exec-id-row');
        var passCount = parseInt(row.querySelector('.exec-pass').value) || 0;
        var failCount = parseInt(row.querySelector('.exec-fail').value) || 0;
        var comment = row.querySelector('.exec-comment').value;
        var action = row.querySelector('.exec-action').value;
        var exId = btn.dataset.exId;

        // 먼저 코멘트 저장, 그 다음 결과 저장
        api('PUT', '/execution/api/' + exId + '/comment', {
          comment: comment, action: action
        }).then(function () {
          return api('POST', '/execution/api/complete', {
            execution_id: exId,
            pass_count: passCount,
            fail_count: failCount,
          });
        }).then(function () { load(); })
          .catch(function (err) { alert(err.message); });
      });
    });

    // 시작 취소
    document.querySelectorAll('.btn-exec-cancel').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (!confirm('시작을 취소하시겠습니까?')) return;
        api('POST', '/execution/api/cancel', {
          execution_id: btn.dataset.exId,
        }).then(function () { load(); })
          .catch(function (err) { alert(err.message); });
      });
    });

    // 특이사항/조치 저장 (완료 상태)
    document.querySelectorAll('.btn-exec-save-comment').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var row = btn.closest('.exec-id-row');
        api('PUT', '/execution/api/' + btn.dataset.exId + '/comment', {
          comment: row.querySelector('.exec-comment').value,
          action: row.querySelector('.exec-action').value,
        }).then(function () {
          btn.textContent = '저장됨';
          setTimeout(function () { btn.textContent = '저장'; }, 1500);
        }).catch(function (err) { alert(err.message); });
      });
    });
  }

  // ── 초기 로드 ──
  load();
})();
