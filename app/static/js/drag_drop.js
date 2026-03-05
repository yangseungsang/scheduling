/* drag_drop.js — SortableJS 기반 스케줄 드래그앤드랍 */

document.addEventListener('DOMContentLoaded', function () {
    initDragDrop();
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
                    fetch('/schedule/api/blocks/' + existingBlockId, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            assigned_date: date,
                            start_time: startTime,
                            end_time: endTime,
                        }),
                    })
                    .then(r => r.json())
                    .catch(console.error);
                } else {
                    // 미배치 업무를 슬롯에 드롭 → POST
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
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            evt.item.dataset.blockId = data.block_id;
                            evt.item.classList.add('schedule-block');

                            const timeSpan = document.createElement('span');
                            timeSpan.className = 'text-muted ms-1 small';
                            timeSpan.textContent = startTime + '-' + endTime;
                            evt.item.appendChild(timeSpan);

                            const removeBtn = document.createElement('button');
                            removeBtn.className = 'btn btn-sm btn-link text-danger p-0 float-end';
                            removeBtn.innerHTML = '<i class="bi bi-x"></i>';
                            removeBtn.onclick = function(e) { removeBlock(data.block_id, e); };
                            evt.item.appendChild(removeBtn);
                        }
                    })
                    .catch(console.error);
                }
            },
            onUpdate: function (evt) {
                // 같은 슬롯 내 순서 변경 시 무시 (슬롯 간 이동은 onAdd에서 처리)
            },
        });
    });
}

function removeBlock(blockId, event) {
    event.stopPropagation();
    if (!confirm('이 스케줄 블록을 삭제하시겠습니까?')) return;

    fetch('/schedule/api/blocks/' + blockId, { method: 'DELETE' })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const el = document.querySelector('[data-block-id="' + blockId + '"]');
            if (el) el.remove();
        }
    })
    .catch(console.error);
}

function generateDraft() {
    const categoryId = document.getElementById('draft-category')?.value;
    const startDate = document.getElementById('draft-start-date')?.value;

    fetch('/schedule/api/draft/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            category_id: categoryId ? parseInt(categoryId) : null,
            start_date: startDate,
        }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('draftModal'));
            if (modal) modal.hide();
            showToast('초안 ' + data.count + '개 블록이 생성되었습니다.', 'success');
            setTimeout(() => location.reload(), 1200);
        }
    })
    .catch(console.error);
}

function approveDraft() {
    fetch('/schedule/api/draft/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('초안이 승인되었습니다.', 'success');
            setTimeout(() => location.reload(), 800);
        }
    })
    .catch(console.error);
}

function discardDraft() {
    if (!confirm('초안을 취소하시겠습니까?')) return;
    fetch('/schedule/api/draft/discard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('초안이 취소되었습니다.', 'info');
            setTimeout(() => location.reload(), 800);
        }
    })
    .catch(console.error);
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
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
