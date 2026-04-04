from datetime import date, datetime, timedelta

from flask import request, jsonify, Response

from schedule.helpers.enrichment import build_maps, enrich_blocks
from schedule.helpers.overlap import check_overlap
from schedule.helpers.time_utils import (
    adjust_end_for_breaks,
    minutes_to_time,
    time_to_minutes,
    work_minutes_in_range,
)
from schedule.models import schedule_block, settings, task
from schedule.routes.calendar_helpers import (
    VALID_BLOCK_STATUSES,
    remove_identifiers_from_other_blocks,
    sync_task_remaining_hours,
    sync_task_status,
)
from schedule.routes.calendar_views import schedule_bp


@schedule_bp.route('/api/blocks', methods=['POST'])
def api_create_block():
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    is_simple = data.get('is_simple', False)

    # Simple block: no task_id required
    if is_simple:
        for field in ('date', 'start_time', 'end_time'):
            if not data.get(field):
                return jsonify({'error': f'{field}은(는) 필수 항목입니다.'}), 400
        block = schedule_block.create(
            task_id=None,
            assignee_ids=[],
            location_id=data.get('location_id', ''),
            version_id=data.get('version_id', ''),
            date=data['date'],
            start_time=data['start_time'],
            end_time=data['end_time'],
            title=data.get('title', ''),
            is_simple=True,
        )
        return jsonify(block), 201

    # Normal block: task_id required
    for field in ('task_id', 'date', 'start_time', 'end_time'):
        if not data.get(field):
            return jsonify({'error': f'{field}은(는) 필수 항목입니다.'}), 400

    t = task.get_by_id(data['task_id'])
    assignee_ids = data.get('assignee_ids', [])
    location_id = data.get('location_id', '')
    version_id = data.get('version_id', '')

    if not assignee_ids and t:
        assignee_ids = t.get('assignee_ids', [])
    if not location_id and t:
        location_id = t.get('location_id', '')
    if not version_id and t:
        version_id = t.get('version_id', '')

    sttngs = settings.get()
    adjusted_end = adjust_end_for_breaks(data['start_time'], data['end_time'], sttngs)

    overlap = check_overlap(assignee_ids, location_id, data['date'], data['start_time'], adjusted_end)
    if overlap:
        return jsonify({'error': '해당 시간에 이미 다른 시험이 배치되어 있습니다.'}), 409

    new_identifier_ids = data.get('identifier_ids')

    block = schedule_block.create(
        task_id=data['task_id'],
        assignee_ids=assignee_ids,
        location_id=location_id,
        version_id=version_id,
        date=data['date'],
        start_time=data['start_time'],
        end_time=adjusted_end,
        is_locked=data.get('is_locked', False),
        identifier_ids=new_identifier_ids,
    )

    # If specific identifiers selected, remove them from other blocks of same task
    if new_identifier_ids and data['task_id']:
        remove_identifiers_from_other_blocks(
            data['task_id'], block['id'], new_identifier_ids, sttngs,
        )

    sync_task_remaining_hours(data['task_id'])
    return jsonify(block), 201


@schedule_bp.route('/api/blocks/<block_id>', methods=['PUT'])
def api_update_block(block_id):
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    allowed = {'date', 'start_time', 'end_time', 'is_locked', 'block_status', 'location_id'}
    updates = {k: v for k, v in data.items() if k in allowed}
    is_resize = data.get('resize', False)
    duration_minutes = data.get('duration_minutes')

    # Recalculate end_time from duration_minutes (used by detail popup)
    if duration_minutes is not None:
        sttngs = settings.get()
        start = block['start_time']
        raw_end = minutes_to_time(time_to_minutes(start) + int(duration_minutes))
        updates['end_time'] = adjust_end_for_breaks(start, raw_end, sttngs)

    if 'start_time' in updates and 'end_time' in updates and not is_resize:
        sttngs = settings.get()
        work_mins = work_minutes_in_range(block['start_time'], block['end_time'], sttngs)
        raw_end = minutes_to_time(time_to_minutes(updates['start_time']) + work_mins)
        updates['end_time'] = adjust_end_for_breaks(updates['start_time'], raw_end, sttngs)

    check_date = updates.get('date', block['date'])
    check_start = updates.get('start_time', block['start_time'])
    check_end = updates.get('end_time', block['end_time'])
    assignee_ids = block.get('assignee_ids', [])
    location_id = updates.get('location_id', block.get('location_id', ''))

    overlap = check_overlap(
        assignee_ids, location_id, check_date, check_start, check_end,
        exclude_block_id=block_id,
    )
    if overlap:
        return jsonify({'error': '해당 시간에 이미 다른 시험이 배치되어 있습니다.'}), 409

    updated = schedule_block.update(block_id, **updates)

    # Resize = real time change, don't recalculate remaining
    # Move = position change, sync remaining
    if block.get('task_id') and not is_resize:
        sync_task_remaining_hours(block['task_id'])

    return jsonify(updated)


@schedule_bp.route('/api/blocks/<block_id>', methods=['DELETE'])
def api_delete_block(block_id):
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    task_id = block.get('task_id')
    is_restore = request.args.get('restore') == '1'
    schedule_block.delete(block_id)
    if task_id:
        sync_task_remaining_hours(task_id)
        if is_restore:
            task.patch(task_id, location_id='')
    return jsonify({'success': True})


@schedule_bp.route('/api/blocks/<block_id>/lock', methods=['PUT'])
def api_toggle_lock(block_id):
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    updated = schedule_block.update(block_id, is_locked=not block.get('is_locked', False))
    return jsonify(updated)


@schedule_bp.route('/api/blocks/<block_id>/status', methods=['PUT'])
def api_update_block_status(block_id):
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if not data or 'block_status' not in data:
        return jsonify({'error': '상태 값이 필요합니다.'}), 400
    status = data['block_status']
    if status not in VALID_BLOCK_STATUSES:
        return jsonify({'error': '유효하지 않은 상태입니다.'}), 400
    updated = schedule_block.update(block_id, block_status=status)

    # Sync task status based on all blocks for this task
    task_id = block.get('task_id')
    if task_id:
        sync_task_status(task_id)

    return jsonify(updated)


@schedule_bp.route('/api/simple-blocks', methods=['POST'])
def api_create_simple_block():
    """Create a simple block (non-test) that appears in the queue."""
    data = request.get_json()
    if not data or not data.get('title', '').strip():
        return jsonify({'error': '제목을 입력해주세요.'}), 400
    title = data['title'].strip()
    minutes = int(data.get('estimated_minutes', 60))
    hours = round(minutes / 60.0, 4)
    version_id = data.get('version_id', '')
    t = task.create(
        procedure_id='BLK-' + str(int(__import__('time').time()))[-6:],
        version_id=version_id,
        assignee_ids=[],
        location_id='',
        section_name=title,
        procedure_owner='',
        test_list=[],
        estimated_hours=hours,
        memo='',
    )
    # Mark as simple block
    task.patch(t['id'], is_simple=True)
    return jsonify(t), 201


@schedule_bp.route('/api/blocks/<block_id>/memo', methods=['PUT'])
def api_update_block_memo(block_id):
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if data is None:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    memo = data.get('memo', '')
    updated = schedule_block.update(block_id, memo=memo)
    # Sync memo to task (keyed by procedure_id)
    if block.get('task_id'):
        task.patch(block['task_id'], memo=memo)
    return jsonify(updated)


@schedule_bp.route('/api/export')
def api_export():
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    fmt = request.args.get('format', 'csv')

    if not start_date or not end_date:
        return jsonify({'error': 'start_date와 end_date는 필수입니다.'}), 400

    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': '날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)'}), 400

    users_map, tasks_map, locations_map = build_maps()
    sttngs = settings.get()
    blocks = schedule_block.get_by_date_range(start_date, end_date)
    enriched = enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        sttngs.get('block_color_by', 'assignee'),
    )
    enriched.sort(key=lambda b: (b.get('date', ''), b.get('start_time', '')))

    from schedule.services.export import export_xlsx, export_csv

    if fmt == 'xlsx':
        try:
            data = export_xlsx(enriched, start_date, end_date)
            return Response(
                data,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': f'attachment; filename="schedule_{start_date}_{end_date}.xlsx"'},
            )
        except ImportError:
            fmt = 'csv'

    return Response(
        export_csv(enriched),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="schedule_{start_date}_{end_date}.csv"'},
    )


@schedule_bp.route('/api/blocks/by-task/<task_id>')
def api_blocks_by_task(task_id):
    """Return all blocks for a task, with their identifier_ids."""
    blocks = [b for b in schedule_block.get_all() if b.get('task_id') == task_id]
    return jsonify({'blocks': blocks})


@schedule_bp.route('/api/blocks/shift', methods=['POST'])
def api_shift_blocks():
    """Shift all blocks on or after from_date by +1 or -1 day, skipping weekends."""
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    from_date = data.get('from_date', '')
    direction = data.get('direction', 1)
    version_id = data.get('version_id', '')

    if not from_date:
        return jsonify({'error': 'from_date는 필수입니다.'}), 400

    all_blocks = schedule_block.get_all()
    shifted = 0
    for b in all_blocks:
        if b['date'] < from_date:
            continue
        if version_id and b.get('version_id') != version_id:
            continue
        if b.get('is_locked'):
            continue

        d = date.fromisoformat(b['date'])
        d += timedelta(days=direction)
        # Skip weekends
        if direction > 0:
            while d.weekday() >= 5:  # 5=Sat, 6=Sun
                d += timedelta(days=1)
        else:
            while d.weekday() >= 5:
                d -= timedelta(days=1)

        schedule_block.update(b['id'], date=d.isoformat())
        shifted += 1

    return jsonify({'success': True, 'shifted_count': shifted})


@schedule_bp.route('/api/blocks/<block_id>/split', methods=['POST'])
def api_split_block(block_id):
    """Split a block: keep selected identifiers in this block,
    the rest go back to queue (unscheduled)."""
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404

    data = request.get_json()
    keep_ids = data.get('keep_identifier_ids', [])
    if not keep_ids:
        return jsonify({'error': '유지할 식별자를 선택해주세요.'}), 400

    task_id = block.get('task_id')
    if not task_id:
        return jsonify({'error': '간단 블록은 분리할 수 없습니다.'}), 400

    t = task.get_by_id(task_id)
    if not t:
        return jsonify({'error': '연결된 시험 항목을 찾을 수 없습니다.'}), 404

    # Calculate new duration based on kept identifiers
    sttngs = settings.get()
    test_list = t.get('test_list', [])
    keep_set = set(keep_ids)
    keep_hours = sum(
        item.get('estimated_hours', 0)
        for item in test_list
        if isinstance(item, dict) and item.get('id') in keep_set
    )

    # Update block: set identifier_ids and adjust time
    keep_min = max(int(keep_hours * 60), 15) if keep_hours > 0 else 15
    new_end_min = time_to_minutes(block['start_time']) + keep_min
    new_end = minutes_to_time(new_end_min)
    adjusted_end = adjust_end_for_breaks(block['start_time'], new_end, sttngs)
    schedule_block.update(block_id, identifier_ids=keep_ids, end_time=adjusted_end)

    return jsonify({'success': True})
