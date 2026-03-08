import calendar
from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request, jsonify

from app.repositories import (
    category_repo,
    schedule_repo,
    settings_repo,
    task_repo,
    user_repo,
)

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')


def _parse_date(date_str):
    """Parse a date string (YYYY-MM-DD) or return today."""
    if date_str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    return date.today()


def _enrich_blocks(blocks, users_map, tasks_map, categories_map, color_by):
    """Add task title, assignee name/color, category name/color to blocks."""
    enriched = []
    for b in blocks:
        block = dict(b)
        task = tasks_map.get(b.get('task_id'))
        assignee = users_map.get(b.get('assignee_id'))
        category = None
        if task:
            category = categories_map.get(task.get('category_id'))

        block['task_title'] = task['title'] if task else '(삭제된 업무)'
        block['assignee_name'] = assignee['name'] if assignee else '(미배정)'
        block['assignee_color'] = assignee['color'] if assignee else '#6c757d'
        block['category_name'] = category['name'] if category else ''
        block['category_color'] = category['color'] if category else '#6c757d'

        if color_by == 'category':
            block['color'] = block['category_color']
        else:
            block['color'] = block['assignee_color']

        enriched.append(block)
    return enriched


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


def _get_queue_tasks(users_map, categories_map):
    """Get unscheduled tasks for the task queue sidebar."""
    tasks = task_repo.get_all()
    # Find task IDs that already have schedule blocks
    all_blocks = schedule_repo.get_all()
    scheduled_task_ids = {b['task_id'] for b in all_blocks}
    queue = []
    for t in tasks:
        if t['status'] == 'completed' or t.get('remaining_hours', 0) <= 0:
            continue
        if t['id'] in scheduled_task_ids:
            continue
        task = dict(t)
        assignee = users_map.get(t.get('assignee_id'))
        category = categories_map.get(t.get('category_id'))
        task['assignee_name'] = assignee['name'] if assignee else '(미배정)'
        task['assignee_color'] = assignee['color'] if assignee else '#6c757d'
        task['category_name'] = category['name'] if category else ''
        task['category_color'] = category['color'] if category else '#6c757d'
        queue.append(task)
    # Sort: deadline ascending, then priority
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    queue.sort(key=lambda t: (
        t.get('deadline') or '9999-12-31',
        priority_order.get(t.get('priority', 'low'), 2),
    ))
    return queue


def _generate_time_slots(settings):
    """Generate list of time slot strings from work_start to work_end."""
    interval = settings.get('grid_interval_minutes', 15)
    start = datetime.strptime(settings['work_start'], '%H:%M')
    end = datetime.strptime(settings['work_end'], '%H:%M')
    slots = []
    current = start
    while current < end:
        slots.append(current.strftime('%H:%M'))
        current += timedelta(minutes=interval)
    return slots


def _is_break_slot(time_str, settings):
    """Check if a time slot falls within lunch or break periods."""
    lunch_start = settings.get('lunch_start', '12:00')
    lunch_end = settings.get('lunch_end', '13:00')
    if lunch_start <= time_str < lunch_end:
        return True
    for brk in settings.get('breaks', []):
        if brk['start'] <= time_str < brk['end']:
            return True
    return False


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

    time_slots = _generate_time_slots(settings)
    break_slots = {s for s in time_slots if _is_break_slot(s, settings)}

    prev_date = current_date - timedelta(days=1)
    next_date = current_date + timedelta(days=1)

    queue_tasks = _get_queue_tasks(users_map, categories_map)

    return render_template(
        'schedule/day.html',
        current_date=current_date,
        prev_date=prev_date,
        next_date=next_date,
        blocks=enriched,
        time_slots=time_slots,
        break_slots=break_slots,
        settings=settings,
        queue_tasks=queue_tasks,
    )


@schedule_bp.route('/week')
def week_view():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    users_map, tasks_map, categories_map = _build_maps()

    # Monday of the current week
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)
    week_days = [week_start + timedelta(days=i) for i in range(7)]

    blocks = schedule_repo.get_by_date_range(
        week_start.isoformat(), week_end.isoformat(),
    )
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )

    # Group blocks by (date, time_slot)
    blocks_by_date = {}
    for b in enriched:
        blocks_by_date.setdefault(b['date'], []).append(b)

    time_slots = _generate_time_slots(settings)
    break_slots = {s for s in time_slots if _is_break_slot(s, settings)}

    prev_week = current_date - timedelta(weeks=1)
    next_week = current_date + timedelta(weeks=1)

    day_names = ['월', '화', '수', '목', '금', '토', '일']

    queue_tasks = _get_queue_tasks(users_map, categories_map)

    return render_template(
        'schedule/week.html',
        current_date=current_date,
        week_start=week_start,
        week_end=week_end,
        week_days=week_days,
        day_names=day_names,
        prev_date=prev_week,
        next_date=next_week,
        blocks_by_date=blocks_by_date,
        time_slots=time_slots,
        break_slots=break_slots,
        settings=settings,
        today=date.today(),
        queue_tasks=queue_tasks,
    )


@schedule_bp.route('/month')
def month_view():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    users_map, tasks_map, categories_map = _build_maps()

    year = current_date.year
    month = current_date.month

    cal = calendar.Calendar(firstweekday=0)  # Monday first
    month_days = cal.monthdayscalendar(year, month)

    # Date range for the month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_repo.get_by_date_range(
        first_day.isoformat(), last_day.isoformat(),
    )
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, categories_map,
        settings.get('block_color_by', 'assignee'),
    )

    # Group blocks by date
    blocks_by_date = {}
    for b in enriched:
        blocks_by_date.setdefault(b['date'], []).append(b)

    # Build calendar weeks with date objects
    weeks = []
    for week in month_days:
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append(None)
            else:
                d = date(year, month, day_num)
                day_blocks = blocks_by_date.get(d.isoformat(), [])
                week_data.append({
                    'date': d,
                    'day': day_num,
                    'blocks': day_blocks,
                })
        weeks.append(week_data)

    # Previous/next month
    if month == 1:
        prev_month_date = date(year - 1, 12, 1)
    else:
        prev_month_date = date(year, month - 1, 1)
    if month == 12:
        next_month_date = date(year + 1, 1, 1)
    else:
        next_month_date = date(year, month + 1, 1)

    day_names = ['월', '화', '수', '목', '금', '토', '일']

    queue_tasks = _get_queue_tasks(users_map, categories_map)

    return render_template(
        'schedule/month.html',
        current_date=current_date,
        year=year,
        month=month,
        weeks=weeks,
        day_names=day_names,
        prev_date=prev_month_date,
        next_date=next_month_date,
        today=date.today(),
        settings=settings,
        queue_tasks=queue_tasks,
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@schedule_bp.route('/api/blocks', methods=['POST'])
def api_create_block():
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    required = ['task_id', 'date', 'start_time', 'end_time']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field}은(는) 필수 항목입니다.'}), 400

    # If no assignee_id, use the task's assignee
    assignee_id = data.get('assignee_id', '')
    if not assignee_id:
        task = task_repo.get_by_id(data['task_id'])
        if task:
            assignee_id = task.get('assignee_id', '')

    block = schedule_repo.create(
        task_id=data['task_id'],
        assignee_id=assignee_id,
        date=data['date'],
        start_time=data['start_time'],
        end_time=data['end_time'],
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

    allowed = ['date', 'start_time', 'end_time', 'is_draft', 'is_locked']
    updates = {k: v for k, v in data.items() if k in allowed}

    updated = schedule_repo.update(block_id, **updates)
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

    new_locked = not block.get('is_locked', False)
    updated = schedule_repo.update(block_id, is_locked=new_locked)
    return jsonify(updated)


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
