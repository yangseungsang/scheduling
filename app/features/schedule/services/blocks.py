"""스케줄 블록 변경 유스케이스.

HTTP 라우트가 요청/응답 처리에 집중할 수 있도록 블록 생성, 이동, 회수에
필요한 도메인 규칙을 이 모듈에 모은다.
"""

from datetime import date as date_cls, timedelta

from app.features.schedule.helpers.overlap import check_overlap
from app.features.schedule.helpers.time_utils import (
    adjust_end_for_breaks,
    minutes_to_time,
    time_to_minutes,
    work_minutes_in_range,
)
from app.features.schedule.models import schedule_block, settings, task
from app.features.schedule.routes.calendar_helpers import (
    remove_identifiers_from_other_blocks,
    sync_task_remaining_minutes,
)

BLOCK_OVERLAP_MESSAGE = '해당 시간에 이미 다른 시험이 배치되어 있습니다.'
CONTINUATION_FAILED_TEMPLATE = (
    '{date} {start}~{end} 시간대에 다른 시험이 있어 배치하지 못했습니다. '
    '초과분({minutes}분)은 줄어듭니다.'
)


class BlockServiceError(Exception):
    """블록 유스케이스 처리 중 API 응답으로 변환 가능한 오류."""

    status_code = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class BlockNotFoundError(BlockServiceError):
    status_code = 404


class BlockConflictError(BlockServiceError):
    status_code = 409


def _require_fields(data, fields):
    for field in fields:
        if not data.get(field):
            raise BlockServiceError(f'{field}은(는) 필수 항목입니다.')


def _work_bounds(sttngs):
    work_start = sttngs.get('actual_work_start') or sttngs.get('work_start', '08:30')
    work_end = sttngs.get('actual_work_end') or sttngs.get('work_end', '17:00')
    return work_start, work_end


def _next_workday(current_date):
    current_date += timedelta(days=1)
    while current_date.weekday() >= 5:
        current_date += timedelta(days=1)
    return current_date


def _continuation_failed_message(date, start, end, minutes):
    return CONTINUATION_FAILED_TEMPLATE.format(
        date=date,
        start=start,
        end=end,
        minutes=minutes,
    )


def _resolve_assignment(data, task_dict):
    """요청값을 우선하고, 없으면 태스크 기본 담당자/장소를 사용한다."""
    assignee_names = data.get('assignee_names', [])
    location_id = data.get('location_id', '')
    if not assignee_names and task_dict:
        assignee_names = task_dict.get('assignee_names', [])
    if not location_id and task_dict:
        location_id = task_dict.get('location_id', '')
    return assignee_names, location_id


def _split_overflow(end_time, sttngs):
    """근무 종료 초과분을 분리한다."""
    _, work_end = _work_bounds(sttngs)
    if time_to_minutes(end_time) <= time_to_minutes(work_end):
        return end_time, 0
    return work_end, work_minutes_in_range(work_end, end_time, sttngs)


def _apply_overflow_continuations(
    *,
    task_id,
    assignee_names,
    location_id,
    start_date,
    overflow_minutes,
    identifier_ids,
    sttngs,
):
    if overflow_minutes <= 0 or not task_id:
        return [], None
    return _build_continuations(
        task_id=task_id,
        assignee_names=assignee_names,
        location_id=location_id,
        start_date=start_date,
        remaining_overflow=overflow_minutes,
        identifier_ids=identifier_ids,
        sttngs=sttngs,
    )


def _build_continuations(
    *,
    task_id,
    assignee_names,
    location_id,
    start_date,
    remaining_overflow,
    identifier_ids,
    sttngs,
):
    """근무 종료 초과분을 다음 근무일 블록들로 생성한다."""
    work_start, work_end = _work_bounds(sttngs)
    work_start_min = time_to_minutes(work_start)
    day_work_min = work_minutes_in_range(work_start, work_end, sttngs)
    current_date = date_cls.fromisoformat(start_date)
    continuations = []

    while remaining_overflow > 0:
        current_date = _next_workday(current_date)
        next_date = current_date.isoformat()
        place_min = min(remaining_overflow, day_work_min)
        cont_start = work_start
        cont_raw_end = minutes_to_time(work_start_min + place_min)
        cont_end = adjust_end_for_breaks(cont_start, cont_raw_end, sttngs)

        if check_overlap(assignee_names, location_id, next_date, cont_start, cont_end):
            return continuations, _continuation_failed_message(
                next_date,
                cont_start,
                cont_end,
                remaining_overflow,
            )

        continuations.append(
            schedule_block.create(
                task_id=task_id,
                assignee_names=assignee_names,
                location_id=location_id,
                date=next_date,
                start_time=cont_start,
                end_time=cont_end,
                identifier_ids=identifier_ids,
            )
        )
        remaining_overflow -= place_min

    return continuations, None


def _result(block, continuations=None, failed_msg=None):
    result = dict(block)
    continuations = continuations or []
    if continuations:
        result['continuation'] = continuations[-1]
        result['continuations'] = continuations
    if failed_msg:
        result['continuation_failed'] = failed_msg
    return result


def _reset_unscheduled_overflow(block, overflow_minutes, continuations):
    if overflow_minutes <= 0 or continuations:
        return
    schedule_block.update(block['id'], overflow_minutes=0)
    block['overflow_minutes'] = 0


def create_block(data):
    """새 스케줄 블록을 생성하고 표시 갱신에 필요한 결과를 반환한다."""
    if data.get('is_simple', False):
        _require_fields(data, ('date', 'start_time', 'end_time'))
        return _result(
            schedule_block.create(
                task_id=None,
                assignee_names=[],
                location_id=data.get('location_id', ''),
                date=data['date'],
                start_time=data['start_time'],
                end_time=data['end_time'],
                title=data.get('title', ''),
                is_simple=True,
            )
        )

    _require_fields(data, ('task_id', 'date', 'start_time', 'end_time'))

    task_id = data['task_id']
    task_dict = task.get_by_id(task_id)
    assignee_names, location_id = _resolve_assignment(data, task_dict)

    sttngs = settings.get()
    adjusted_end = adjust_end_for_breaks(data['start_time'], data['end_time'], sttngs)
    if check_overlap(
        assignee_names, location_id, data['date'], data['start_time'], adjusted_end
    ):
        raise BlockConflictError(BLOCK_OVERLAP_MESSAGE)

    adjusted_end, overflow_minutes = _split_overflow(adjusted_end, sttngs)

    identifier_ids = data.get('identifier_ids')
    block = schedule_block.create(
        task_id=task_id,
        assignee_names=assignee_names,
        location_id=location_id,
        date=data['date'],
        start_time=data['start_time'],
        end_time=adjusted_end,
        is_locked=data.get('is_locked', False),
        identifier_ids=identifier_ids,
        overflow_minutes=overflow_minutes,
    )

    if location_id:
        refreshed = task.get_by_id(task_id)
        if refreshed and not refreshed.get('location_id'):
            task.patch(task_id, location_id=location_id)

    if identifier_ids:
        remove_identifiers_from_other_blocks(task_id, block['id'], identifier_ids, sttngs)

    continuations, failed_msg = _apply_overflow_continuations(
        task_id=task_id,
        assignee_names=assignee_names,
        location_id=location_id,
        start_date=data['date'],
        overflow_minutes=overflow_minutes,
        identifier_ids=identifier_ids,
        sttngs=sttngs,
    )
    _reset_unscheduled_overflow(block, overflow_minutes, continuations)

    sync_task_remaining_minutes(task_id)
    return _result(block, continuations, failed_msg)


def update_block(block_id, data):
    """기존 블록 이동/리사이즈/상세 수정을 처리한다."""
    block = schedule_block.get_by_id(block_id)
    if not block:
        raise BlockNotFoundError('블록을 찾을 수 없습니다.')
    if not data:
        raise BlockServiceError('요청 데이터가 없습니다.')

    allowed = {
        'date',
        'start_time',
        'end_time',
        'is_locked',
        'block_status',
        'location_id',
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    sttngs = settings.get()

    duration_minutes = data.get('duration_minutes')
    if duration_minutes is not None:
        start = block['start_time']
        raw_end = minutes_to_time(time_to_minutes(start) + int(duration_minutes))
        updates['end_time'] = adjust_end_for_breaks(start, raw_end, sttngs)

    if 'start_time' in updates and 'end_time' in updates and not data.get('resize', False):
        work_mins = work_minutes_in_range(block['start_time'], block['end_time'], sttngs)
        raw_end = minutes_to_time(time_to_minutes(updates['start_time']) + work_mins)
        updates['end_time'] = adjust_end_for_breaks(updates['start_time'], raw_end, sttngs)

    check_date = updates.get('date', block['date'])
    check_start = updates.get('start_time', block['start_time'])
    check_end = updates.get('end_time', block['end_time'])
    assignee_names = block.get('assignee_names', [])
    location_id = updates.get('location_id', block.get('location_id', ''))

    if check_overlap(
        assignee_names,
        location_id,
        check_date,
        check_start,
        check_end,
        exclude_block_id=block_id,
    ):
        raise BlockConflictError(BLOCK_OVERLAP_MESSAGE)

    clamped_end, overflow_minutes = _split_overflow(check_end, sttngs)
    if overflow_minutes > 0:
        updates['end_time'] = clamped_end

    continuations, failed_msg = _apply_overflow_continuations(
        task_id=block.get('task_id'),
        assignee_names=block.get('assignee_names', []),
        location_id=location_id,
        start_date=updates.get('date', block['date']),
        overflow_minutes=overflow_minutes,
        identifier_ids=block.get('identifier_ids'),
        sttngs=sttngs,
    )

    if overflow_minutes > 0 and not continuations:
        updates['overflow_minutes'] = 0

    updated = schedule_block.update(block_id, **updates)
    if 'location_id' in updates and updates['location_id'] and block.get('task_id'):
        task.patch(block['task_id'], location_id=updates['location_id'])

    if block.get('task_id'):
        sync_task_remaining_minutes(block['task_id'])

    return _result(updated, continuations, failed_msg)


def delete_block(block_id, restore_mode=None):
    """블록을 삭제하거나 태스크 전체 블록을 큐로 복원한다."""
    block = schedule_block.get_by_id(block_id)
    if not block:
        raise BlockNotFoundError('블록을 찾을 수 없습니다.')

    task_id = block.get('task_id')
    is_restore = restore_mode in ('1', 'task', 'all')
    deleted_count = 0
    if restore_mode in ('task', 'all') and task_id:
        for candidate in list(schedule_block.get_all()):
            if candidate.get('task_id') == task_id:
                schedule_block.delete(candidate['id'])
                deleted_count += 1
    else:
        schedule_block.delete(block_id)
        deleted_count = 1

    if task_id:
        sync_task_remaining_minutes(task_id)
        if is_restore:
            task.patch(task_id, location_id='')

    return {'success': True, 'deleted_count': deleted_count}
