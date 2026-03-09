import calendar
from datetime import date, datetime, timedelta

from flask import Blueprint, request, jsonify, render_template, Response

from app.repositories import (
    category_repo,
    schedule_repo,
    settings_repo,
    task_repo,
    user_repo,
)
from app.utils.time_utils import (
    adjust_end_for_breaks,
    generate_time_slots,
    is_break_slot,
    minutes_to_time,
    time_to_minutes,
    work_minutes_in_range,
)

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')

DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']
PRIORITY_ORDER = {'high': 0, 'medium': 1, 'low': 2}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str):
    """Parse a date string (YYYY-MM-DD) or return today."""
    if date_str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    return date.today()


def _build_maps():
    """Build lookup maps for users, tasks, categories."""
    users = user_repo.get_all()
    tasks = task_repo.get_all()
    categories = category_repo.get_all()
    return (
        {u['id']: u for u in users},
        {t['id']: t for t in tasks},
        {c['id']: c for c in categories},
    )


def _enrich_blocks(blocks, users_map, tasks_map, categories_map, color_by):
    """Add display fields (title, names, colors) to raw schedule blocks."""
    enriched = []
    for b in blocks:
        block = dict(b)
        task = tasks_map.get(b.get('task_id'))
        assignee = users_map.get(b.get('assignee_id'))
        category = categories_map.get(task.get('category_id')) if task else None

        block['task_title'] = task['title'] if task else '(삭제된 업무)'
        block['priority'] = task.get('priority', '') if task else ''
        block['assignee_name'] = assignee['name'] if assignee else '(미배정)'
        block['assignee_color'] = assignee['color'] if assignee else '#6c757d'
        block['category_name'] = category['name'] if category else ''
        block['category_color'] = category['color'] if category else '#6c757d'
        block['color'] = block['category_color'] if color_by == 'category' else block['assignee_color']

        enriched.append(block)
    return enriched


def _get_queue_tasks(users_map, categories_map):
    """Get tasks with remaining unscheduled hours for the task queue sidebar."""
    tasks = task_repo.get_all()
    all_blocks = schedule_repo.get_all()

    scheduled_hours = {}
    for b in all_blocks:
        tid = b['task_id']
        duration = time_to_minutes(b['end_time']) - time_to_minutes(b['start_time'])
        scheduled_hours[tid] = scheduled_hours.get(tid, 0) + duration / 60.0

    queue = []
    for t in tasks:
        if t['status'] == 'completed' or t.get('remaining_hours', 0) <= 0:
            continue
        remaining = t.get('remaining_hours', 0) - scheduled_hours.get(t['id'], 0)
        if remaining <= 0:
            continue

        task = dict(t)
        task['remaining_unscheduled_hours'] = round(remaining, 2)
        assignee = users_map.get(t.get('assignee_id'))
        category = categories_map.get(t.get('category_id'))
        task['assignee_name'] = assignee['name'] if assignee else '(미배정)'
        task['assignee_color'] = assignee['color'] if assignee else '#6c757d'
        task['category_name'] = category['name'] if category else ''
        task['category_color'] = category['color'] if category else '#6c757d'
        queue.append(task)

    queue.sort(key=lambda t: (
        t.get('deadline') or '9999-12-31',
        PRIORITY_ORDER.get(t.get('priority', 'low'), 2),
    ))
    return queue


def _check_overlap(assignee_id, date_str, start_time, end_time, exclude_block_id=None):
    """Check if a block would overlap with existing blocks for the same assignee."""
    if not assignee_id:
        return None
    s1 = time_to_minutes(start_time)
    e1 = time_to_minutes(end_time)
    for b in schedule_repo.get_by_date(date_str):
        if b['assignee_id'] != assignee_id:
            continue
        if exclude_block_id and b['id'] == exclude_block_id:
            continue
        if s1 < time_to_minutes(b['end_time']) and time_to_minutes(b['start_time']) < e1:
            return b
    return None


def _compute_overlap_layout(blocks):
    """Compute col_index/col_total for overlapping blocks (side-by-side display).

    Greedy column-packing: sort by start, assign to first non-overlapping column.
    """
    if not blocks:
        return blocks

    sorted_blocks = sorted(
        blocks,
        key=lambda b: (time_to_minutes(b['start_time']),
                       -time_to_minutes(b['end_time'])),
    )

    columns = []  # list of (end_min, [block_indices])
    block_col = {}

    for i, b in enumerate(sorted_blocks):
        s = time_to_minutes(b['start_time'])
        placed = False
        for ci, (col_end, indices) in enumerate(columns):
            if col_end <= s:
                columns[ci] = (time_to_minutes(b['end_time']), indices + [i])
                block_col[i] = ci
                placed = True
                break
        if not placed:
            block_col[i] = len(columns)
            columns.append((time_to_minutes(b['end_time']), [i]))

    for i, b in enumerate(sorted_blocks):
        s = time_to_minutes(b['start_time'])
        e = time_to_minutes(b['end_time'])
        max_col = block_col[i] + 1
        for j, b2 in enumerate(sorted_blocks):
            if i == j:
                continue
            s2 = time_to_minutes(b2['start_time'])
            e2 = time_to_minutes(b2['end_time'])
            if s < e2 and s2 < e:
                max_col = max(max_col, block_col[j] + 1)
        b['col_index'] = block_col[i]
        b['col_total'] = max_col

    return sorted_blocks


def _get_break_slots(settings):
    """Return set of time-slot strings that fall in break periods."""
    slots = generate_time_slots(settings)
    return {s for s in slots if is_break_slot(s, settings)}


def _build_month_nav(year, month):
    """Return (prev_month_date, next_month_date) for month navigation."""
    if month == 1:
        prev_date = date(year - 1, 12, 1)
    else:
        prev_date = date(year, month - 1, 1)
    if month == 12:
        next_date = date(year + 1, 1, 1)
    else:
        next_date = date(year, month + 1, 1)
    return prev_date, next_date


def _group_blocks_by_date(enriched):
    """Group enriched blocks into a dict keyed by date string."""
    result = {}
    for b in enriched:
        result.setdefault(b['date'], []).append(b)
    return result


def _build_month_weeks(year, month, blocks_by_date):
    """Build month calendar weeks with block data for template rendering."""
    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append(None)
            else:
                d = date(year, month, day_num)
                week_data.append({
                    'date': d,
                    'day': day_num,
                    'blocks': blocks_by_date.get(d.isoformat(), []),
                })
        weeks.append(week_data)
    return weeks


# ---------------------------------------------------------------------------
# Template rendering routes
# ---------------------------------------------------------------------------

@schedule_bp.route('/')
def day_view():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    users_map, tasks_map, categories_map = _build_maps()

    blocks = schedule_repo.get_by_date(current_date.isoformat())
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )
    enriched = _compute_overlap_layout(enriched)

    return render_template(
        'schedule/day.html',
        current_date=current_date,
        prev_date=current_date - timedelta(days=1),
        next_date=current_date + timedelta(days=1),
        blocks=enriched,
        time_slots=generate_time_slots(settings),
        break_slots=_get_break_slots(settings),
        settings=settings,
        queue_tasks=_get_queue_tasks(users_map, categories_map),
    )


@schedule_bp.route('/week')
def week_view():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    users_map, tasks_map, categories_map = _build_maps()

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_repo.get_by_date_range(
        week_start.isoformat(), week_end.isoformat(),
    )
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )

    blocks_by_date = _group_blocks_by_date(enriched)
    for day_key in blocks_by_date:
        blocks_by_date[day_key] = _compute_overlap_layout(blocks_by_date[day_key])

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
        time_slots=generate_time_slots(settings),
        break_slots=_get_break_slots(settings),
        settings=settings,
        today=date.today(),
        queue_tasks=_get_queue_tasks(users_map, categories_map),
    )


@schedule_bp.route('/month')
def month_view():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    users_map, tasks_map, categories_map = _build_maps()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_repo.get_by_date_range(
        first_day.isoformat(), last_day.isoformat(),
    )
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )

    blocks_by_date = _group_blocks_by_date(enriched)
    prev_date, next_date = _build_month_nav(year, month)

    return render_template(
        'schedule/month.html',
        current_date=current_date,
        year=year,
        month=month,
        weeks=_build_month_weeks(year, month, blocks_by_date),
        day_names=DAY_NAMES,
        prev_date=prev_date,
        next_date=next_date,
        today=date.today(),
        settings=settings,
        queue_tasks=_get_queue_tasks(users_map, categories_map),
    )


# ---------------------------------------------------------------------------
# View data API endpoints
# ---------------------------------------------------------------------------

@schedule_bp.route('/api/day')
def api_day_data():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    users_map, tasks_map, categories_map = _build_maps()

    blocks = schedule_repo.get_by_date(current_date.isoformat())
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )

    time_slots = generate_time_slots(settings)
    return jsonify({
        'current_date': current_date.isoformat(),
        'prev_date': (current_date - timedelta(days=1)).isoformat(),
        'next_date': (current_date + timedelta(days=1)).isoformat(),
        'blocks': enriched,
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, settings)],
        'settings': settings,
        'queue_tasks': _get_queue_tasks(users_map, categories_map),
    })


@schedule_bp.route('/api/week')
def api_week_data():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    users_map, tasks_map, categories_map = _build_maps()

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_repo.get_by_date_range(week_start.isoformat(), week_end.isoformat())
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )

    time_slots = generate_time_slots(settings)
    return jsonify({
        'current_date': current_date.isoformat(),
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'week_days': [(week_start + timedelta(days=i)).isoformat() for i in range(7)],
        'day_names': DAY_NAMES,
        'prev_date': (current_date - timedelta(weeks=1)).isoformat(),
        'next_date': (current_date + timedelta(weeks=1)).isoformat(),
        'blocks_by_date': _group_blocks_by_date(enriched),
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, settings)],
        'settings': settings,
        'today': date.today().isoformat(),
        'queue_tasks': _get_queue_tasks(users_map, categories_map),
    })


@schedule_bp.route('/api/month')
def api_month_data():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    users_map, tasks_map, categories_map = _build_maps()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_repo.get_by_date_range(first_day.isoformat(), last_day.isoformat())
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )

    blocks_by_date = _group_blocks_by_date(enriched)
    prev_date, next_date = _build_month_nav(year, month)

    # API returns date as iso string instead of date object
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
        'settings': settings,
        'queue_tasks': _get_queue_tasks(users_map, categories_map),
    })


# ---------------------------------------------------------------------------
# Block CRUD API
# ---------------------------------------------------------------------------

@schedule_bp.route('/api/blocks', methods=['POST'])
def api_create_block():
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    for field in ('task_id', 'date', 'start_time', 'end_time'):
        if not data.get(field):
            return jsonify({'error': f'{field}은(는) 필수 항목입니다.'}), 400

    assignee_id = data.get('assignee_id', '')
    if not assignee_id:
        task = task_repo.get_by_id(data['task_id'])
        if task:
            assignee_id = task.get('assignee_id', '')

    settings = settings_repo.get()
    adjusted_end = adjust_end_for_breaks(data['start_time'], data['end_time'], settings)

    overlap = _check_overlap(assignee_id, data['date'], data['start_time'], adjusted_end)
    if overlap:
        return jsonify({'error': '해당 시간에 이미 다른 업무가 배치되어 있습니다.'}), 409

    block = schedule_repo.create(
        task_id=data['task_id'],
        assignee_id=assignee_id,
        date=data['date'],
        start_time=data['start_time'],
        end_time=adjusted_end,
        is_draft=data.get('is_draft', False),
        is_locked=data.get('is_locked', False),
        origin=data.get('origin', 'manual'),
    )
    return jsonify(block), 201


@schedule_bp.route('/api/blocks/<block_id>', methods=['PUT'])
def api_update_block(block_id):
    block = schedule_repo.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    allowed = {'date', 'start_time', 'end_time', 'is_draft', 'is_locked'}
    updates = {k: v for k, v in data.items() if k in allowed}
    is_resize = data.get('resize', False)

    # Preserve original work duration on move (not resize)
    if 'start_time' in updates and 'end_time' in updates and not is_resize:
        settings = settings_repo.get()
        work_mins = work_minutes_in_range(block['start_time'], block['end_time'], settings)
        raw_end = minutes_to_time(time_to_minutes(updates['start_time']) + work_mins)
        updates['end_time'] = adjust_end_for_breaks(updates['start_time'], raw_end, settings)

    # Overlap check
    check_date = updates.get('date', block['date'])
    check_start = updates.get('start_time', block['start_time'])
    check_end = updates.get('end_time', block['end_time'])
    overlap = _check_overlap(
        block['assignee_id'], check_date, check_start, check_end,
        exclude_block_id=block_id,
    )
    if overlap:
        return jsonify({'error': '해당 시간에 이미 다른 업무가 배치되어 있습니다.'}), 409

    updated = schedule_repo.update(block_id, **updates)

    # On resize, sync task remaining_hours with total scheduled time
    if is_resize and block.get('task_id'):
        _sync_task_remaining_hours(block['task_id'])

    return jsonify(updated)


@schedule_bp.route('/api/blocks/<block_id>', methods=['DELETE'])
def api_delete_block(block_id):
    block = schedule_repo.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    schedule_repo.delete(block_id)
    return jsonify({'success': True})


@schedule_bp.route('/api/blocks/<block_id>/lock', methods=['PUT'])
def api_toggle_lock(block_id):
    block = schedule_repo.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    updated = schedule_repo.update(block_id, is_locked=not block.get('is_locked', False))
    return jsonify(updated)


def _sync_task_remaining_hours(task_id):
    """Set task remaining_hours to match total scheduled block time."""
    total_min = sum(
        time_to_minutes(b['end_time']) - time_to_minutes(b['start_time'])
        for b in schedule_repo.get_all()
        if b['task_id'] == task_id
    )
    total_hours = round(total_min / 60.0, 2)
    task = task_repo.get_by_id(task_id)
    if task and task.get('remaining_hours', 0) != total_hours:
        task_repo.patch(task_id, remaining_hours=total_hours)


# ---------------------------------------------------------------------------
# Export API
# ---------------------------------------------------------------------------

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

    users_map, tasks_map, categories_map = _build_maps()
    settings = settings_repo.get()
    blocks = schedule_repo.get_by_date_range(start_date, end_date)
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )
    enriched.sort(key=lambda b: (b.get('date', ''), b.get('start_time', '')))

    from app.services.export import export_xlsx, export_csv

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


# ---------------------------------------------------------------------------
# Draft scheduling API
# ---------------------------------------------------------------------------

@schedule_bp.route('/api/draft/generate', methods=['POST'])
def api_draft_generate():
    from app.services.scheduler import generate_draft_schedule
    result = generate_draft_schedule()
    return jsonify({
        'placed_count': len(result['placed']),
        'unplaced': [
            {
                'task_id': u['task']['id'],
                'task_title': u['task']['title'],
                'remaining_hours': u['remaining_unscheduled_hours'],
            }
            for u in result['unplaced']
        ],
    })


@schedule_bp.route('/api/draft/approve', methods=['POST'])
def api_draft_approve():
    from app.services.scheduler import approve_drafts
    approve_drafts()
    return jsonify({'success': True})


@schedule_bp.route('/api/draft/discard', methods=['POST'])
def api_draft_discard():
    from app.services.scheduler import discard_drafts
    discard_drafts()
    return jsonify({'success': True})
