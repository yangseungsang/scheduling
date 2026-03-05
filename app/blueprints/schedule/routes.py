import calendar
from datetime import date, timedelta, datetime
from flask import render_template, request, redirect, url_for, jsonify, flash
from app.blueprints.schedule import schedule_bp
from app.repositories import schedule_repo, task_repo, category_repo, settings_repo
from app.services.scheduler import generate_draft


@schedule_bp.route('/')
def day_view():
    date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    category_id = request.args.get('category_id', type=int)
    current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    prev_date = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
    next_date = (current_date + timedelta(days=1)).strftime('%Y-%m-%d')

    blocks = schedule_repo.get_blocks_for_date(date_str)
    unscheduled = task_repo.get_unscheduled_tasks(category_id=category_id)
    categories = category_repo.get_all_categories()
    work_hours = settings_repo.get_work_hours()

    return render_template('schedule/day.html',
                           blocks=blocks, unscheduled=unscheduled,
                           categories=categories, work_hours=work_hours,
                           current_date=date_str, prev_date=prev_date,
                           next_date=next_date, selected_category=category_id)


@schedule_bp.route('/week')
def week_view():
    date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    category_id = request.args.get('category_id', type=int)
    current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)
    prev_week = (week_start - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (week_start + timedelta(days=7)).strftime('%Y-%m-%d')

    blocks = schedule_repo.get_blocks_for_week(
        week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d'))
    categories = category_repo.get_all_categories()
    work_hours = settings_repo.get_work_hours()
    week_days = [week_start + timedelta(days=i) for i in range(7)]

    blocks_by_date = {}
    for block in blocks:
        d = block['assigned_date']
        if d not in blocks_by_date:
            blocks_by_date[d] = []
        blocks_by_date[d].append(dict(block))

    return render_template('schedule/week.html',
                           blocks_by_date=blocks_by_date, week_days=week_days,
                           categories=categories, work_hours=work_hours,
                           prev_week=prev_week, next_week=next_week,
                           selected_category=category_id)


@schedule_bp.route('/month')
def month_view():
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    category_id = request.args.get('category_id', type=int)

    blocks = schedule_repo.get_blocks_for_month(year, month)
    categories = category_repo.get_all_categories()

    blocks_by_date = {}
    for block in blocks:
        d = block['assigned_date']
        if d not in blocks_by_date:
            blocks_by_date[d] = []
        blocks_by_date[d].append(dict(block))

    cal = calendar.monthcalendar(year, month)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template('schedule/month.html',
                           blocks_by_date=blocks_by_date, cal=cal,
                           year=year, month=month, today=today,
                           categories=categories, selected_category=category_id,
                           prev_month=prev_month, prev_year=prev_year,
                           next_month=next_month, next_year=next_year)


# --- API Endpoints ---

@schedule_bp.route('/api/blocks', methods=['POST'])
def api_create_block():
    data = request.json or {}
    if not data.get('task_id') or not data.get('assigned_date'):
        return jsonify({'success': False, 'error': 'task_id and assigned_date required'}), 400
    block_id = schedule_repo.create_block(
        task_id=data['task_id'],
        assigned_date=data['assigned_date'],
        start_time=data['start_time'],
        end_time=data['end_time'],
        is_draft=data.get('is_draft', False),
    )
    return jsonify({'success': True, 'block_id': block_id})


@schedule_bp.route('/api/blocks/<int:block_id>', methods=['PUT'])
def api_update_block(block_id):
    data = request.json or {}
    if not data.get('assigned_date'):
        return jsonify({'success': False, 'error': 'assigned_date required'}), 400
    schedule_repo.update_block(
        block_id=block_id,
        assigned_date=data['assigned_date'],
        start_time=data['start_time'],
        end_time=data['end_time'],
    )
    return jsonify({'success': True})


@schedule_bp.route('/api/blocks/<int:block_id>', methods=['DELETE'])
def api_delete_block(block_id):
    schedule_repo.delete_block(block_id)
    return jsonify({'success': True})


@schedule_bp.route('/api/draft/generate', methods=['POST'])
def api_generate_draft():
    data = request.json or {}
    category_id = data.get('category_id')
    start_date_str = data.get('start_date', date.today().strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

    work_hours = settings_repo.get_work_hours()
    tasks = task_repo.get_unscheduled_tasks(category_id=category_id)
    tasks_list = [dict(t) for t in tasks]

    end_date_str = (start_date + timedelta(days=14)).strftime('%Y-%m-%d')
    existing = schedule_repo.get_blocks_for_week(start_date_str, end_date_str)
    occupied_by_date = {}
    for block in existing:
        if not block['is_draft']:
            d = block['assigned_date']
            occupied_by_date.setdefault(d, []).append({
                'start_time': block['start_time'],
                'end_time': block['end_time']
            })

    draft_blocks = generate_draft(tasks_list, work_hours, occupied_by_date, start_date)

    schedule_repo.discard_draft_blocks(category_id=category_id)
    for b in draft_blocks:
        schedule_repo.create_block(
            task_id=b['task_id'],
            assigned_date=b['assigned_date'],
            start_time=b['start_time'],
            end_time=b['end_time'],
            is_draft=True,
        )

    scheduled_ids = {b['task_id'] for b in draft_blocks}
    unscheduled_ids = [t['id'] for t in tasks_list if t['id'] not in scheduled_ids]
    return jsonify({
        'success': True,
        'count': len(draft_blocks),
        'blocks': draft_blocks,
        'unscheduled_task_ids': unscheduled_ids,
    })


@schedule_bp.route('/api/draft/approve', methods=['POST'])
def api_approve_draft():
    data = request.json or {}
    category_id = data.get('category_id')
    schedule_repo.approve_draft_blocks(category_id=category_id)
    return jsonify({'success': True})


@schedule_bp.route('/api/draft/discard', methods=['POST'])
def api_discard_draft():
    data = request.json or {}
    category_id = data.get('category_id')
    schedule_repo.discard_draft_blocks(category_id=category_id)
    return jsonify({'success': True})
