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


def _sync_task_remaining_hours(task_id):
    sttngs = settings.get()
    total_min = sum(
        work_minutes_in_range(b['start_time'], b['end_time'], sttngs)
        for b in schedule_block.get_all()
        if b['task_id'] == task_id
    )
    scheduled_hours = round(total_min / 60.0, 2)
    t = task.get_by_id(task_id)
    if t:
        est = t.get('estimated_hours', 0)
        new_remaining = round(max(est - scheduled_hours, 0), 2)
        if t.get('remaining_hours', 0) != new_remaining:
            task.patch(task_id, remaining_hours=new_remaining)


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

    if is_resize and block.get('task_id'):
        # Resize changes the test duration — update estimated_hours to match total scheduled
        sttngs = settings.get()
        total_min = sum(
            work_minutes_in_range(b['start_time'], b['end_time'], sttngs)
            for b in schedule_block.get_all()
            if b['task_id'] == block['task_id']
        )
        new_est = round(total_min / 60.0, 2)
        task.patch(block['task_id'], estimated_hours=new_est, remaining_hours=0)

    return jsonify(updated)


@schedule_bp.route('/api/blocks/<block_id>', methods=['DELETE'])
def api_delete_block(block_id):
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    task_id = block.get('task_id')
    schedule_block.delete(block_id)
    if task_id:
        _sync_task_remaining_hours(task_id)
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
    return jsonify(updated)


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


@schedule_bp.route('/api/draft/generate', methods=['POST'])
def api_draft_generate():
    from schedule.services.scheduler import generate_draft_schedule
    version_id = _get_current_version_id()
    if not version_id:
        return jsonify({'error': '버전을 선택해주세요.'}), 400
    data = request.get_json() or {}
    result = generate_draft_schedule(
        version_id=version_id,
        start_date=data.get('start_date'),
        end_date=data.get('end_date'),
        include_existing=data.get('include_existing', False),
    )
    return jsonify({
        'placed_count': len(result['placed']),
        'workdays': result.get('workdays', 0),
        'unplaced': [
            {
                'task_id': u['task']['id'],
                'procedure_id': u['task'].get('procedure_id', ''),
                'remaining_hours': u['remaining_unscheduled_hours'],
                'reason': u.get('reason', ''),
            }
            for u in result['unplaced']
        ],
    })


@schedule_bp.route('/api/draft/approve', methods=['POST'])
def api_draft_approve():
    from schedule.services.scheduler import approve_drafts
    approve_drafts()
    return jsonify({'success': True})


@schedule_bp.route('/api/draft/discard', methods=['POST'])
def api_draft_discard():
    from schedule.services.scheduler import discard_drafts
    discard_drafts()
    return jsonify({'success': True})
