import calendar
from datetime import date, datetime, timedelta

from flask import Blueprint, request, jsonify, render_template, Response

from schedule.helpers.enrichment import (
    build_maps,
    build_month_nav,
    build_month_weeks,
    enrich_blocks,
    get_break_slots,
    get_queue_tasks,
    group_blocks_by_date,
    parse_date,
)
from schedule.helpers.overlap import check_overlap, compute_overlap_layout
from schedule.helpers.time_utils import (
    adjust_end_for_breaks,
    generate_time_slots,
    is_break_slot,
    minutes_to_time,
    time_to_minutes,
    work_minutes_in_range,
)
from schedule.models import location, schedule_block, settings, task, version

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')

DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']


def _get_current_version_id():
    vid = request.args.get('version')
    if vid:
        return vid
    active = version.get_active()
    return active[0]['id'] if active else None


def _remove_identifiers_from_other_blocks(task_id, exclude_block_id,
                                          moved_ids, sttngs):
    """Remove moved_ids from other blocks of the same task.

    If a block loses all its identifiers, delete it.
    If it loses some, shrink its duration proportionally.
    """
    t = task.get_by_id(task_id)
    if not t:
        return
    test_list = t.get('test_list', [])
    # Build hours lookup: identifier_id → estimated_hours
    id_hours = {}
    for item in test_list:
        if isinstance(item, dict):
            id_hours[item['id']] = item.get('estimated_hours', 0)

    moved_set = set(moved_ids)
    all_blocks = schedule_block.get_all()
    for b in all_blocks:
        if b.get('task_id') != task_id:
            continue
        if b['id'] == exclude_block_id:
            continue
        block_ids = b.get('identifier_ids')
        if not block_ids:
            # Block covers all identifiers — remove the moved ones
            all_task_ids = [item['id'] if isinstance(item, dict) else item
                           for item in test_list]
            block_ids = all_task_ids

        overlap = [i for i in block_ids if i in moved_set]
        if not overlap:
            continue

        remaining_ids = [i for i in block_ids if i not in moved_set]
        if not remaining_ids:
            # Block lost all identifiers → delete it
            schedule_block.delete(b['id'])
        else:
            # Shrink block duration to match remaining identifiers
            remaining_hours = sum(id_hours.get(i, 0) for i in remaining_ids)
            remaining_min = max(int(remaining_hours * 60), 15)
            new_end_min = time_to_minutes(b['start_time']) + remaining_min
            new_end = minutes_to_time(new_end_min)
            adjusted_end = adjust_end_for_breaks(b['start_time'], new_end, sttngs)
            schedule_block.update(b['id'],
                                 identifier_ids=remaining_ids,
                                 end_time=adjusted_end)


def _sync_task_remaining_hours(task_id):
    if not task_id:
        return
    t = task.get_by_id(task_id)
    if not t:
        return

    # estimated_hours = sum of test_list identifier hours, or task value for simple blocks
    test_list = t.get('test_list', [])
    tl_sum = round(sum(
        item.get('estimated_hours', 0) for item in test_list
        if isinstance(item, dict)
    ), 2)
    est = tl_sum if tl_sum > 0 else t.get('estimated_hours', 0)

    sttngs = settings.get()
    total_min = sum(
        work_minutes_in_range(b['start_time'], b['end_time'], sttngs)
        for b in schedule_block.get_all()
        if b.get('task_id') == task_id
    )
    scheduled_hours = round(total_min / 60.0, 2)
    new_remaining = round(max(est - scheduled_hours, 0), 2)

    patches = {}
    if t.get('estimated_hours', 0) != est:
        patches['estimated_hours'] = est
    if t.get('remaining_hours', 0) != new_remaining:
        patches['remaining_hours'] = new_remaining
    if patches:
        task.patch(task_id, **patches)


@schedule_bp.route('/')
def day_view():
    current_date = parse_date(request.args.get('date'))
    sttngs = settings.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = build_maps()

    blocks = schedule_block.get_by_date(current_date.isoformat())
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        sttngs.get('block_color_by', 'assignee'),
    )
    # Group blocks by location for column layout
    locations_list = location.get_all()
    blocks_by_location = {}
    for loc in locations_list:
        loc_blocks = [b for b in enriched if b.get('location_id') == loc['id']]
        blocks_by_location[loc['id']] = compute_overlap_layout(loc_blocks)
    # Blocks without location
    no_loc_blocks = [b for b in enriched if not b.get('location_id')]
    if no_loc_blocks:
        blocks_by_location[''] = compute_overlap_layout(no_loc_blocks)

    return render_template(
        'schedule/day.html',
        current_date=current_date,
        prev_date=current_date - timedelta(days=1),
        next_date=current_date + timedelta(days=1),
        blocks=enriched,
        blocks_by_location=blocks_by_location,
        locations=locations_list,
        time_slots=generate_time_slots(sttngs),
        break_slots=get_break_slots(sttngs),
        settings=sttngs,
        queue_tasks=get_queue_tasks(users_map, locations_map, version_id),
        versions=version.get_all(),
        current_version_id=version_id or '',
    )


@schedule_bp.route('/week')
def week_view():
    current_date = parse_date(request.args.get('date'))
    sttngs = settings.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = build_maps()

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_block.get_by_date_range(
        week_start.isoformat(), week_end.isoformat(),
    )
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        sttngs.get('block_color_by', 'assignee'),
    )

    blocks_by_date = group_blocks_by_date(enriched)

    return render_template(
        'schedule/week.html',
        current_date=current_date,
        week_start=week_start,
        week_end=week_end,
        week_days=[week_start + timedelta(days=i) for i in range(7)],
        day_names=DAY_NAMES,
        prev_date=current_date - timedelta(weeks=1),
        next_date=current_date + timedelta(weeks=1),
        blocks_by_date=blocks_by_date,
        time_slots=generate_time_slots(sttngs),
        break_slots=get_break_slots(sttngs),
        settings=sttngs,
        today=date.today(),
        locations=location.get_all(),
        queue_tasks=get_queue_tasks(users_map, locations_map, version_id),
        versions=version.get_all(),
        current_version_id=version_id or '',
    )


@schedule_bp.route('/month')
def month_view():
    current_date = parse_date(request.args.get('date'))
    sttngs = settings.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = build_maps()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_block.get_by_date_range(
        first_day.isoformat(), last_day.isoformat(),
    )
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        sttngs.get('block_color_by', 'assignee'),
    )

    blocks_by_date = group_blocks_by_date(enriched)
    prev_date, next_date = build_month_nav(year, month)

    return render_template(
        'schedule/month.html',
        current_date=current_date,
        year=year,
        month=month,
        weeks=build_month_weeks(year, month, blocks_by_date),
        day_names=DAY_NAMES,
        prev_date=prev_date,
        next_date=next_date,
        today=date.today(),
        settings=sttngs,
        locations=location.get_all(),
        queue_tasks=get_queue_tasks(users_map, locations_map, version_id),
        versions=version.get_all(),
        current_version_id=version_id or '',
    )


@schedule_bp.route('/api/day')
def api_day_data():
    current_date = parse_date(request.args.get('date'))
    sttngs = settings.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = build_maps()

    blocks = schedule_block.get_by_date(current_date.isoformat())
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        sttngs.get('block_color_by', 'assignee'),
    )

    time_slots = generate_time_slots(sttngs)
    return jsonify({
        'current_date': current_date.isoformat(),
        'prev_date': (current_date - timedelta(days=1)).isoformat(),
        'next_date': (current_date + timedelta(days=1)).isoformat(),
        'blocks': enriched,
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, sttngs)],
        'settings': sttngs,
        'queue_tasks': get_queue_tasks(users_map, locations_map, version_id),
    })


@schedule_bp.route('/api/week')
def api_week_data():
    current_date = parse_date(request.args.get('date'))
    sttngs = settings.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = build_maps()

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_block.get_by_date_range(week_start.isoformat(), week_end.isoformat())
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        sttngs.get('block_color_by', 'assignee'),
    )

    time_slots = generate_time_slots(sttngs)
    return jsonify({
        'current_date': current_date.isoformat(),
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'week_days': [(week_start + timedelta(days=i)).isoformat() for i in range(7)],
        'day_names': DAY_NAMES,
        'prev_date': (current_date - timedelta(weeks=1)).isoformat(),
        'next_date': (current_date + timedelta(weeks=1)).isoformat(),
        'blocks_by_date': group_blocks_by_date(enriched),
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, sttngs)],
        'settings': sttngs,
        'today': date.today().isoformat(),
        'queue_tasks': get_queue_tasks(users_map, locations_map, version_id),
    })


@schedule_bp.route('/api/month')
def api_month_data():
    current_date = parse_date(request.args.get('date'))
    sttngs = settings.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = build_maps()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_block.get_by_date_range(first_day.isoformat(), last_day.isoformat())
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        sttngs.get('block_color_by', 'assignee'),
    )

    blocks_by_date = group_blocks_by_date(enriched)
    prev_date, next_date = build_month_nav(year, month)

    weeks = []
    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdayscalendar(year, month):
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append(None)
            else:
                d = date(year, month, day_num)
                week_data.append({
                    'date': d.isoformat(),
                    'day': day_num,
                    'blocks': blocks_by_date.get(d.isoformat(), []),
                })
        weeks.append(week_data)

    return jsonify({
        'current_date': current_date.isoformat(),
        'year': year,
        'month': month,
        'weeks': weeks,
        'day_names': DAY_NAMES,
        'prev_date': prev_date.isoformat(),
        'next_date': next_date.isoformat(),
        'today': date.today().isoformat(),
        'settings': sttngs,
        'queue_tasks': get_queue_tasks(users_map, locations_map, version_id),
    })


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
            origin=data.get('origin', 'manual'),
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
        is_draft=data.get('is_draft', False),
        is_locked=data.get('is_locked', False),
        origin=data.get('origin', 'manual'),
        identifier_ids=new_identifier_ids,
    )

    # If specific identifiers selected, remove them from other blocks of same task
    if new_identifier_ids and data['task_id']:
        _remove_identifiers_from_other_blocks(
            data['task_id'], block['id'], new_identifier_ids, sttngs,
        )

    _sync_task_remaining_hours(data['task_id'])
    return jsonify(block), 201


@schedule_bp.route('/api/blocks/<block_id>', methods=['PUT'])
def api_update_block(block_id):
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    allowed = {'date', 'start_time', 'end_time', 'is_draft', 'is_locked', 'block_status', 'location_id'}
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
        _sync_task_remaining_hours(block['task_id'])

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
        _sync_task_remaining_hours(task_id)
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


VALID_BLOCK_STATUSES = {'pending', 'in_progress', 'completed', 'cancelled'}


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
        _sync_task_status(task_id)

    return jsonify(updated)


def _sync_task_status(task_id):
    """Update task status based on its schedule blocks' statuses."""
    from schedule.models import task as task_model
    t = task_model.get_by_id(task_id)
    if not t:
        return
    blocks = [b for b in schedule_block.get_all()
              if b.get('task_id') == task_id and not b.get('is_draft')]
    if not blocks:
        return
    statuses = [b.get('block_status', 'pending') for b in blocks]
    if all(s == 'completed' for s in statuses):
        new_status = 'completed'
    elif any(s == 'in_progress' for s in statuses):
        new_status = 'in_progress'
    elif any(s == 'completed' for s in statuses):
        new_status = 'in_progress'
    else:
        new_status = t['status']
    if new_status != t['status']:
        task_model.patch(task_id, status=new_status)


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
