/* drag_drop.js — SortableJS 기반 스케줄 드래그앤드랍 */

document.addEventListener('DOMContentLoaded', function () {
    initDragDrop();
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

/* 블록 상단/하단 드래그로 소요시간 변경 */
function initBlockResize() {
    document.addEventListener('mousedown', function (e) {
        var handle = e.target.closest('.block-resize-top, .block-resize-bottom');
        if (!handle) return;

        e.preventDefault();
        e.stopPropagation();

        var block = handle.closest('.schedule-block');
        if (!block) return;

        var isBottom = handle.classList.contains('block-resize-bottom');
        var blockId = block.dataset.blockId;
        if (!blockId) return;

        var originalStart = block.dataset.startTime;
        var originalEnd = block.dataset.endTime;
        var date = block.closest('.drop-target')
            ? block.closest('.drop-target').dataset.date
            : null;
        if (!date) return;

        var currentTargetSlot = null;
        block.classList.add('resizing');

        function onMove(me) {
            // 현재 커서 위치의 time-slot 찾기 (핸들 자신은 pointerEvents 잠시 비활성화)
            handle.style.pointerEvents = 'none';
            var el = document.elementFromPoint(me.clientX, me.clientY);
            handle.style.pointerEvents = '';

            var slot = el ? el.closest('.time-slot') : null;

            document.querySelectorAll('.time-slot.resize-target').forEach(function (s) {
                s.classList.remove('resize-target');
            });

            if (!slot || !slot.dataset.time) return;
            slot.classList.add('resize-target');
            currentTargetSlot = slot;
        }

        function onUp() {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);

            block.classList.remove('resizing');
            document.querySelectorAll('.time-slot.resize-target').forEach(function (s) {
                s.classList.remove('resize-target');
            });

            if (!currentTargetSlot || !currentTargetSlot.dataset.time) return;

            var slotTime = currentTargetSlot.dataset.time;
            var newStart = isBottom ? originalStart : slotTime;
            // 하단 핸들: 드롭 슬롯의 다음 슬롯이 end_time (최소 30분 보장)
            var newEnd = isBottom ? addMinutes(slotTime, 30) : originalEnd;

            if (newStart >= newEnd) {
                showToast('시작 시간은 종료 시간보다 빨라야 합니다.', 'warning');
                return;
            }

            // 변경 없으면 무시
            if (newStart === originalStart && newEnd === originalEnd) return;

            showSaveIndicator();
            fetch('/schedule/api/blocks/' + blockId, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    assigned_date: date,
                    start_time: newStart,
                    end_time: newEnd,
                }),
            })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function () {
                hideSaveIndicator();
                // 데이터 속성 업데이트
                block.dataset.startTime = newStart;
                block.dataset.endTime = newEnd;

                // 시간 텍스트 업데이트
                var timeSpan = block.querySelector('.block-time');
                if (timeSpan) timeSpan.textContent = newStart + '-' + newEnd;

                // 상단 핸들로 start_time 변경 시 → 해당 슬롯으로 블록 이동
                if (!isBottom && newStart !== originalStart) {
                    var newSlot = document.querySelector(
                        '.drop-target[data-time="' + newStart + '"][data-date="' + date + '"]'
                    );
                    if (newSlot) newSlot.appendChild(block);
                }
            })
            .catch(function (err) {
                console.error(err);
                hideSaveIndicator();
                showToast('소요시간 변경에 실패했습니다.', 'danger');
            });
        }

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });
}

/* 업무 블록 클릭 시 상세 보기로 이동 */
function initBlockClickNavigation() {
    document.addEventListener('click', function (e) {
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
