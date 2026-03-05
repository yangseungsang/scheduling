/* drag_drop.js — SortableJS 기반 스케줄 드래그앤드랍 */

var _wasResizing = false;

document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('week-timeline-scroll')) {
        initWeekDragDrop();
        initWeekBlockMove();
    } else {
        initDragDrop();
    }
    initBlockClickNavigation();
    initBlockResize();
});

function initDragDrop() {
    const unscheduledList = document.getElementById('unscheduled-list');
    const dropTargets = document.querySelectorAll('.drop-target');

    if (!unscheduledList) return;

    // 미배치 업무 목록 → 복제 드래그
    new Sortable(unscheduledList, {
        group: {
            name: 'schedule',
            pull: 'clone',
            put: false,
        },
        sort: false,
        animation: 150,
        ghostClass: 'sortable-ghost',
        chosenClass: 'sortable-chosen',
    });

    // 각 타임슬롯 → 드롭 가능
    dropTargets.forEach(function (target) {
        new Sortable(target, {
            group: {
                name: 'schedule',
                pull: true,
                put: true,
            },
            animation: 150,
            ghostClass: 'sortable-ghost',
            onMove: function (evt) {
                // 드래그 중 현재 drop target 하이라이트
                document.querySelectorAll('.drop-target').forEach(function (el) {
                    el.classList.remove('drop-zone-active');
                });
                if (evt.to) evt.to.classList.add('drop-zone-active');
            },
            onEnd: function () {
                // 드래그 종료 시 모든 하이라이트 제거
                document.querySelectorAll('.drop-target').forEach(function (el) {
                    el.classList.remove('drop-zone-active');
                });
            },
            onAdd: function (evt) {
                const taskId = evt.item.dataset.taskId;
                const estimatedMinutes = parseInt(evt.item.dataset.estimated || 60);
                const date = target.dataset.date;
                const startTime = target.dataset.time;

                if (!taskId || !date || !startTime) return;

                const endTime = addMinutes(startTime, estimatedMinutes);

                const existingBlockId = evt.item.dataset.blockId;

                if (existingBlockId) {
                    // 이미 배치된 블록을 다른 슬롯으로 이동 → PUT
                    var prevParent = evt.from;
                    var prevIndex = evt.oldIndex;
                    showSaveIndicator();
                    fetch('/schedule/api/blocks/' + existingBlockId, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            assigned_date: date,
                            start_time: startTime,
                            end_time: endTime,
                        }),
                    })
                    .then(function (r) {
                        if (!r.ok) throw new Error('HTTP ' + r.status);
                        return r.json();
                    })
                    .then(function () {
                        hideSaveIndicator();
                    })
                    .catch(function (err) {
                        console.error(err);
                        hideSaveIndicator();
                        showToast('서버 오류가 발생했습니다. 다시 시도해주세요.', 'danger');
                        // 롤백: 원래 위치로 복원
                        if (prevParent) {
                            evt.item.remove();
                            if (prevParent.children[prevIndex]) {
                                prevParent.insertBefore(evt.item, prevParent.children[prevIndex]);
                            } else {
                                prevParent.appendChild(evt.item);
                            }
                        }
                    });
                } else {
                    // 미배치 업무를 슬롯에 드롭 → POST
                    showSaveIndicator();
                    fetch('/schedule/api/blocks', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            task_id: parseInt(taskId),
                            assigned_date: date,
                            start_time: startTime,
                            end_time: endTime,
                            is_draft: false,
                        }),
                    })
                    .then(function (r) {
                        if (!r.ok) throw new Error('HTTP ' + r.status);
                        return r.json();
                    })
                    .then(function (data) {
                        hideSaveIndicator();
                        if (data.success) {
                            evt.item.dataset.blockId = data.block_id;
                            evt.item.dataset.startTime = startTime;
                            evt.item.dataset.endTime = endTime;
                            evt.item.classList.add('schedule-block');

                            var resizeTop = document.createElement('div');
                            resizeTop.className = 'block-resize-top';
                            resizeTop.title = '위로 드래그: 시작 시간 변경';
                            evt.item.insertBefore(resizeTop, evt.item.firstChild);

                            var timeSpan = document.createElement('span');
                            timeSpan.className = 'text-muted ms-1 small block-time';
                            timeSpan.textContent = startTime + '-' + endTime;
                            evt.item.appendChild(timeSpan);

                            var removeBtn = document.createElement('button');
                            removeBtn.className = 'btn btn-sm btn-link text-danger p-0 float-end';
                            removeBtn.setAttribute('aria-label', '블록 삭제');
                            removeBtn.innerHTML = '<i class="bi bi-x" aria-hidden="true"></i>';
                            removeBtn.onclick = function(e) { removeBlock(data.block_id, e); };
                            evt.item.appendChild(removeBtn);

                            var resizeBottom = document.createElement('div');
                            resizeBottom.className = 'block-resize-bottom';
                            resizeBottom.title = '아래로 드래그: 종료 시간 변경';
                            evt.item.appendChild(resizeBottom);
                        } else {
                            showToast('블록 생성에 실패했습니다.', 'danger');
                            evt.item.remove();
                        }
                    })
                    .catch(function (err) {
                        console.error(err);
                        hideSaveIndicator();
                        showToast('서버 오류가 발생했습니다. 다시 시도해주세요.', 'danger');
                        // 롤백: 드롭된 아이템 제거 (clone이므로 원본은 남아있음)
                        evt.item.remove();
                    });
                }
            },
            onUpdate: function (evt) {
                // 같은 슬롯 내 순서 변경 시 무시 (슬롯 간 이동은 onAdd에서 처리)
            },
        });
    });
}

/* ─────────────────────────────────────────────
   주간 뷰 전용: HTML5 drag API 기반 드래그앤드랍
   ───────────────────────────────────────────── */

function _getColY(col, clientY) {
    /* 컬럼 내 Y 픽셀 좌표 → 30분 단위로 스냅 */
    var rect = col.getBoundingClientRect();
    var y = clientY - rect.top;
    return Math.max(0, Math.min(y, col.offsetHeight - 1));
}

function _yToTime(y) {
    /* Y 픽셀 → 30분 스냅 시간 문자열 (PX_PER_MIN, WORK_START_MIN 전역 변수 사용) */
    var pxPerMin = (typeof PX_PER_MIN !== 'undefined') ? PX_PER_MIN : 2;
    var wsMin    = (typeof WORK_START_MIN !== 'undefined') ? WORK_START_MIN : 540;
    var weMin    = (typeof WORK_END_MIN !== 'undefined') ? WORK_END_MIN : 1080;
    var snap = 30;
    var minutes = Math.floor(y / pxPerMin / snap) * snap;
    var total = Math.max(0, Math.min(wsMin + minutes, weMin - snap));
    return minutesToTimeStr(total);
}

function _showDropIndicator(col, clientY) {
    var ind = col.querySelector('.week-drop-indicator');
    if (!ind) {
        ind = document.createElement('div');
        ind.className = 'week-drop-indicator';
        col.appendChild(ind);
    }
    var y = _getColY(col, clientY);
    var pxPerMin = (typeof PX_PER_MIN !== 'undefined') ? PX_PER_MIN : 2;
    var snap = 30;
    var snappedY = Math.floor(y / (pxPerMin * snap)) * (pxPerMin * snap);
    ind.style.top = snappedY + 'px';
    ind.dataset.time = _yToTime(y);
}

function _hideDropIndicator(col) {
    var ind = col.querySelector('.week-drop-indicator');
    if (ind) ind.remove();
}

function initWeekDragDrop() {
    /* 미배치 업무 → 주간 타임라인 드롭 */
    document.querySelectorAll('#unscheduled-list .task-item').forEach(function (item) {
        item.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'copy';
            e.dataTransfer.setData('dragType', 'unscheduled');
            e.dataTransfer.setData('taskId', item.dataset.taskId);
            e.dataTransfer.setData('estimated', item.dataset.estimated || '60');
        });
    });

    document.querySelectorAll('.week-day-col').forEach(function (col) {
        col.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
            col.classList.add('drag-over');
            _showDropIndicator(col, e.clientY);
        });

        col.addEventListener('dragleave', function (e) {
            if (!col.contains(e.relatedTarget)) {
                col.classList.remove('drag-over');
                _hideDropIndicator(col);
            }
        });

        col.addEventListener('drop', function (e) {
            e.preventDefault();
            col.classList.remove('drag-over');
            _hideDropIndicator(col);

            var dragType  = e.dataTransfer.getData('dragType');
            var date      = col.dataset.date;
            var y         = _getColY(col, e.clientY);
            var startTime = _yToTime(y);

            if (dragType === 'unscheduled') {
                var taskId    = parseInt(e.dataTransfer.getData('taskId'));
                var estimated = parseInt(e.dataTransfer.getData('estimated') || '60');
                var endTime   = addMinutes(startTime, estimated);
                _createBlockOnCol(col, taskId, date, startTime, endTime, estimated);

            } else if (dragType === 'block') {
                var blockId   = e.dataTransfer.getData('blockId');
                var origStart = e.dataTransfer.getData('origStart');
                var origEnd   = e.dataTransfer.getData('origEnd');
                var duration  = timeToMinutes(origEnd) - timeToMinutes(origStart);
                var endTime   = addMinutes(startTime, Math.max(30, duration));
                _moveBlockOnCol(blockId, col, date, startTime, endTime);
            }
        });
    });
}

function _createBlockOnCol(col, taskId, date, startTime, endTime, estimatedMinutes) {
    showSaveIndicator();
    fetch('/schedule/api/blocks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId, assigned_date: date, start_time: startTime, end_time: endTime, is_draft: false }),
    })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (data) {
        hideSaveIndicator();
        if (data.success) {
            _renderBlockOnCol(col, {
                blockId: data.block_id, taskId: taskId, date: date,
                startTime: startTime, endTime: endTime,
            });
            // 미배치 목록에서 제거
            var src = document.querySelector('#unscheduled-list [data-task-id="' + taskId + '"]');
            if (src) src.remove();
            // 미배치 없으면 안내 문구
            if (!document.querySelector('#unscheduled-list .task-item')) {
                var empty = document.createElement('div');
                empty.className = 'text-muted text-center py-3 small';
                empty.textContent = '미배치 업무 없음';
                document.getElementById('unscheduled-list').appendChild(empty);
            }
        } else {
            showToast('블록 생성에 실패했습니다.', 'danger');
        }
    })
    .catch(function (err) {
        console.error(err);
        hideSaveIndicator();
        showToast('서버 오류가 발생했습니다.', 'danger');
    });
}

function _moveBlockOnCol(blockId, col, date, startTime, endTime) {
    var block = document.querySelector('[data-block-id="' + blockId + '"]');
    var origParent = block ? block.parentElement : null;
    var origStyle  = block ? { top: block.style.top, height: block.style.height } : null;

    showSaveIndicator();
    fetch('/schedule/api/blocks/' + blockId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assigned_date: date, start_time: startTime, end_time: endTime }),
    })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function () {
        hideSaveIndicator();
        if (!block) return;
        var pxPerMin = (typeof PX_PER_MIN !== 'undefined') ? PX_PER_MIN : 2;
        var wsMin    = (typeof WORK_START_MIN !== 'undefined') ? WORK_START_MIN : 540;
        var topPx    = (timeToMinutes(startTime) - wsMin) * pxPerMin;
        var heightPx = Math.max(20, (timeToMinutes(endTime) - timeToMinutes(startTime)) * pxPerMin);
        block.style.top    = topPx + 'px';
        block.style.height = heightPx + 'px';
        block.dataset.startTime = startTime;
        block.dataset.endTime   = endTime;
        var ts = block.querySelector('.block-time');
        if (ts) ts.textContent = startTime + '-' + endTime;
        // 다른 날 컬럼으로 이동
        if (block.parentElement !== col) col.appendChild(block);
    })
    .catch(function (err) {
        console.error(err);
        hideSaveIndicator();
        showToast('이동에 실패했습니다.', 'danger');
        if (block && origParent && origStyle) {
            block.style.top    = origStyle.top;
            block.style.height = origStyle.height;
            if (block.parentElement !== origParent) origParent.appendChild(block);
        }
    });
}

function _renderBlockOnCol(col, opts) {
    var pxPerMin = (typeof PX_PER_MIN !== 'undefined') ? PX_PER_MIN : 2;
    var wsMin    = (typeof WORK_START_MIN !== 'undefined') ? WORK_START_MIN : 540;
    var topPx    = (timeToMinutes(opts.startTime) - wsMin) * pxPerMin;
    var heightPx = Math.max(20, (timeToMinutes(opts.endTime) - timeToMinutes(opts.startTime)) * pxPerMin);

    var el = document.createElement('div');
    el.className = 'schedule-block';
    el.setAttribute('draggable', 'true');
    el.dataset.blockId   = opts.blockId;
    el.dataset.taskId    = opts.taskId;
    el.dataset.startTime = opts.startTime;
    el.dataset.endTime   = opts.endTime;
    el.style.cssText = 'position:absolute; top:' + topPx + 'px; height:' + heightPx + 'px; left:2px; right:2px; overflow:hidden; white-space:nowrap;';

    el.innerHTML =
        '<div class="block-resize-top" draggable="false" title="시작 시간 조정"></div>' +
        '<span class="fw-semibold d-block text-truncate" style="padding:0 20px 0 0;font-size:0.75rem;">업무</span>' +
        '<span class="text-muted block-time" style="font-size:0.7rem;">' + opts.startTime + '-' + opts.endTime + '</span>' +
        '<button class="btn btn-link text-danger p-0" style="position:absolute;top:2px;right:2px;font-size:0.75rem;line-height:1" aria-label="블록 삭제" draggable="false">' +
            '<i class="bi bi-x" aria-hidden="true"></i></button>' +
        '<div class="block-resize-bottom" draggable="false" title="종료 시간 조정"></div>';

    el.querySelector('button').onclick = function (e) { removeBlock(opts.blockId, e); };
    _makeDraggableBlock(el);
    col.appendChild(el);
}

function initWeekBlockMove() {
    /* 기존 블록을 드래그해서 다른 날짜/시간으로 이동 */
    document.querySelectorAll('.week-day-col .schedule-block').forEach(_makeDraggableBlock);
}

function _makeDraggableBlock(block) {
    block.addEventListener('dragstart', function (e) {
        if (e.target.classList.contains('block-resize-top') ||
            e.target.classList.contains('block-resize-bottom')) {
            e.preventDefault();
            return;
        }
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('dragType',  'block');
        e.dataTransfer.setData('blockId',   block.dataset.blockId);
        e.dataTransfer.setData('origStart', block.dataset.startTime);
        e.dataTransfer.setData('origEnd',   block.dataset.endTime);
        block.style.opacity = '0.5';
    });
    block.addEventListener('dragend', function () {
        block.style.opacity = '';
    });
}

/* ─────────────────────────────────────────────
   블록 상단/하단 드래그로 소요시간 변경 (픽셀 기반)
   ───────────────────────────────────────────── */
/* 블록 상단/하단 드래그로 소요시간 변경 (주간/일간 공통) */
function initBlockResize() {
    document.addEventListener('mousedown', function (e) {
        var handle = e.target.closest('.block-resize-top, .block-resize-bottom');
        if (!handle) return;

        e.preventDefault();
        e.stopPropagation();
        _wasResizing = true;

        var block = handle.closest('.schedule-block');
        if (!block) return;

        var isBottom  = handle.classList.contains('block-resize-bottom');
        var blockId   = block.dataset.blockId;
        if (!blockId) return;

        var originalStart = block.dataset.startTime;
        var originalEnd   = block.dataset.endTime;
        var col  = block.closest('.week-day-col');  // 주간 뷰
        var slot = block.closest('.drop-target');   // 일간 뷰

        var isWeekView = !!col;
        var date = isWeekView ? col.dataset.date : (slot ? slot.dataset.date : null);
        if (!date) return;

        block.classList.add('resizing');

        /* ── 주간 뷰: 픽셀 Y 좌표로 계산 ── */
        function onMoveWeek(me) {
            var y    = _getColY(col, me.clientY);
            var time = _yToTime(y);
            var pxPerMin = (typeof PX_PER_MIN !== 'undefined') ? PX_PER_MIN : 2;
            var wsMin    = (typeof WORK_START_MIN !== 'undefined') ? WORK_START_MIN : 540;
            var weMin    = (typeof WORK_END_MIN !== 'undefined') ? WORK_END_MIN : 1080;

            if (isBottom) {
                var newEndMin = Math.max(timeToMinutes(originalStart) + 30,
                                        Math.min(timeToMinutes(addMinutes(time, 30)), weMin));
                var heightPx  = (newEndMin - timeToMinutes(originalStart)) * pxPerMin;
                block.style.height = Math.max(20, heightPx) + 'px';
            } else {
                var newStartMin = Math.max(wsMin,
                                  Math.min(timeToMinutes(time), timeToMinutes(originalEnd) - 30));
                var topPx    = (newStartMin - wsMin) * pxPerMin;
                var heightPx = (timeToMinutes(originalEnd) - newStartMin) * pxPerMin;
                block.style.top    = topPx + 'px';
                block.style.height = Math.max(20, heightPx) + 'px';
            }
        }

        /* ── 일간 뷰: 슬롯 감지 방식 ── */
        var currentTargetSlot = null;
        function onMoveLegacy(me) {
            handle.style.pointerEvents = 'none';
            var el = document.elementFromPoint(me.clientX, me.clientY);
            handle.style.pointerEvents = '';
            var s = el ? el.closest('.time-slot') : null;
            document.querySelectorAll('.time-slot.resize-target').forEach(function (x) { x.classList.remove('resize-target'); });
            if (s && s.dataset.time) { s.classList.add('resize-target'); currentTargetSlot = s; }
        }

        function onUp() {
            document.removeEventListener('mousemove', isWeekView ? onMoveWeek : onMoveLegacy);
            document.removeEventListener('mouseup', onUp);
            setTimeout(function () { _wasResizing = false; }, 0);
            block.classList.remove('resizing');
            document.querySelectorAll('.time-slot.resize-target').forEach(function (s) { s.classList.remove('resize-target'); });

            var pxPerMin = (typeof PX_PER_MIN !== 'undefined') ? PX_PER_MIN : 2;
            var wsMin    = (typeof WORK_START_MIN !== 'undefined') ? WORK_START_MIN : 540;
            var newStart, newEnd;

            if (isWeekView) {
                /* 현재 block style에서 역산 */
                var curTop    = parseFloat(block.style.top);
                var curHeight = parseFloat(block.style.height);
                var startMin  = Math.round(curTop / pxPerMin / 30) * 30 + wsMin;
                var endMin    = Math.round((curTop + curHeight) / pxPerMin / 30) * 30 + wsMin;
                newStart = minutesToTimeStr(startMin);
                newEnd   = minutesToTimeStr(endMin);
            } else {
                if (!currentTargetSlot) return;
                var slotTime = currentTargetSlot.dataset.time;
                newStart = isBottom ? originalStart : slotTime;
                newEnd   = isBottom ? addMinutes(slotTime, 30) : originalEnd;
            }

            if (newStart >= newEnd) { showToast('시작 시간은 종료 시간보다 빨라야 합니다.', 'warning'); _resetBlockStyle(); return; }
            if (newStart === originalStart && newEnd === originalEnd) return;

            showSaveIndicator();
            fetch('/schedule/api/blocks/' + blockId, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ assigned_date: date, start_time: newStart, end_time: newEnd }),
            })
            .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
            .then(function () {
                hideSaveIndicator();
                block.dataset.startTime = newStart;
                block.dataset.endTime   = newEnd;
                var ts = block.querySelector('.block-time');
                if (ts) ts.textContent = newStart + '-' + newEnd;
                /* 주간 뷰: 픽셀 위치 확정 (이미 style에 반영됨) */
                if (isWeekView) {
                    var topPx    = (timeToMinutes(newStart) - wsMin) * pxPerMin;
                    var heightPx = Math.max(20, (timeToMinutes(newEnd) - timeToMinutes(newStart)) * pxPerMin);
                    block.style.top    = topPx + 'px';
                    block.style.height = heightPx + 'px';
                }
            })
            .catch(function (err) {
                console.error(err);
                hideSaveIndicator();
                showToast('소요시간 변경에 실패했습니다.', 'danger');
                _resetBlockStyle();
            });
        }

        function _resetBlockStyle() {
            if (isWeekView) {
                var wsMin    = (typeof WORK_START_MIN !== 'undefined') ? WORK_START_MIN : 540;
                var pxPerMin = (typeof PX_PER_MIN !== 'undefined') ? PX_PER_MIN : 2;
                block.style.top    = (timeToMinutes(originalStart) - wsMin) * pxPerMin + 'px';
                block.style.height = Math.max(20, (timeToMinutes(originalEnd) - timeToMinutes(originalStart)) * pxPerMin) + 'px';
            }
        }

        document.addEventListener('mousemove', isWeekView ? onMoveWeek : onMoveLegacy);
        document.addEventListener('mouseup', onUp);
    });
}

/* 업무 블록 클릭 시 상세 보기로 이동 */
function initBlockClickNavigation() {
    document.addEventListener('click', function (e) {
        if (_wasResizing) return;
        var block = e.target.closest('.schedule-block');
        if (!block) return;
        // 삭제 버튼, 링크, 리사이즈 핸들 클릭은 무시
        if (e.target.closest('button') || e.target.closest('a')) return;
        if (e.target.closest('.block-resize-top, .block-resize-bottom')) return;
        var taskId = block.dataset.taskId;
        if (taskId) window.location.href = '/tasks/' + taskId;
    });
}

/* 자동 저장 인디케이터 */
function showSaveIndicator() {
    var indicator = document.getElementById('save-indicator');
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'save-indicator';
        indicator.className = 'save-indicator';
        indicator.setAttribute('role', 'status');
        indicator.setAttribute('aria-live', 'polite');
        indicator.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> 저장 중...';
        document.body.appendChild(indicator);
    }
    indicator.classList.add('visible');
}

function hideSaveIndicator() {
    var indicator = document.getElementById('save-indicator');
    if (indicator) indicator.classList.remove('visible');
}

function removeBlock(blockId, event) {
    event.stopPropagation();
    if (!confirm('이 스케줄 블록을 삭제하시겠습니까?')) return;

    fetch('/schedule/api/blocks/' + blockId, { method: 'DELETE' })
    .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    })
    .then(function (data) {
        if (data.success) {
            var el = document.querySelector('[data-block-id="' + blockId + '"]');
            if (el) el.remove();
        }
    })
    .catch(function (err) {
        console.error(err);
        showToast('삭제에 실패했습니다. 다시 시도해주세요.', 'danger');
    });
}

function setButtonLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
        btn.classList.add('btn-loading');
        btn.disabled = true;
    } else {
        btn.classList.remove('btn-loading');
        btn.disabled = false;
    }
}

function generateDraft(e) {
    const categoryId = document.getElementById('draft-category')?.value;
    const startDate = document.getElementById('draft-start-date')?.value;
    const btn = e && e.target ? e.target.closest('button') : null;
    setButtonLoading(btn, true);

    fetch('/schedule/api/draft/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            category_id: categoryId ? parseInt(categoryId) : null,
            start_date: startDate,
        }),
    })
    .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    })
    .then(function (data) {
        if (data.success) {
            var modal = bootstrap.Modal.getInstance(document.getElementById('draftModal'));
            if (modal) modal.hide();
            showToast('초안 ' + data.count + '개 블록이 생성되었습니다.', 'success');
            setTimeout(function () { location.reload(); }, 1200);
        }
    })
    .catch(function (err) {
        console.error(err);
        setButtonLoading(btn, false);
        showToast('초안 생성에 실패했습니다. 다시 시도해주세요.', 'danger');
    });
}

function approveDraft(e) {
    var btn = e && e.target ? e.target.closest('button') : null;
    setButtonLoading(btn, true);
    fetch('/schedule/api/draft/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    })
    .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    })
    .then(function (data) {
        if (data.success) {
            showToast('초안이 승인되었습니다.', 'success');
            setTimeout(function () { location.reload(); }, 800);
        }
    })
    .catch(function (err) {
        console.error(err);
        setButtonLoading(btn, false);
        showToast('승인에 실패했습니다. 다시 시도해주세요.', 'danger');
    });
}

function discardDraft(e) {
    var btn = e && e.target ? e.target.closest('button') : null;
    if (!confirm('초안을 취소하시겠습니까?')) return;
    setButtonLoading(btn, true);
    fetch('/schedule/api/draft/discard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    })
    .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    })
    .then(function (data) {
        if (data.success) {
            showToast('초안이 취소되었습니다.', 'info');
            setTimeout(function () { location.reload(); }, 800);
        }
    })
    .catch(function (err) {
        console.error(err);
        setButtonLoading(btn, false);
        showToast('초안 취소에 실패했습니다. 다시 시도해주세요.', 'danger');
    });
}

function timeToMinutes(timeStr) {
    var parts = timeStr.split(':');
    return parseInt(parts[0]) * 60 + parseInt(parts[1]);
}

function minutesToTimeStr(minutes) {
    var h = Math.floor(minutes / 60);
    var m = minutes % 60;
    return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
}

function addMinutes(timeStr, minutes) {
    const parts = timeStr.split(':');
    const h = parseInt(parts[0]);
    const m = parseInt(parts[1]);
    const total = h * 60 + m + minutes;
    const rh = Math.floor(total / 60);
    const rm = total % 60;
    return String(rh).padStart(2, '0') + ':' + String(rm).padStart(2, '0');
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = 'alert alert-' + type + ' position-fixed bottom-0 end-0 m-3 shadow';
    toast.style.zIndex = '9999';
    toast.style.minWidth = '250px';
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
