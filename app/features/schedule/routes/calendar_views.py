import calendar
from datetime import date, timedelta

from flask import Blueprint, request, jsonify, render_template

from app.features.schedule.helpers.enrichment import (
    build_maps,
    build_month_nav,
    build_month_weeks,
    enrich_blocks,
    get_break_slots,
    get_queue_tasks,
    group_blocks_by_date,
    parse_date,
)
from app.features.schedule.helpers.overlap import compute_overlap_layout
from app.features.schedule.helpers.time_utils import generate_time_slots, is_break_slot
from app.features.schedule.models import location, schedule_block, settings, version
from app.features.schedule.routes.calendar_helpers import DAY_NAMES

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')


def _prepare_view_context():
    """Build the common context shared by day/week/month views."""
    sttngs = settings.get()
    users_map, tasks_map, locations_map = build_maps()
    versions = version.get_all()
    return {
        'sttngs': sttngs,
        'users_map': users_map,
        'tasks_map': tasks_map,
        'locations_map': locations_map,
        'locations_list': location.get_all(),
        'time_slots': generate_time_slots(sttngs),
        'break_slots': get_break_slots(sttngs),
        'queue_tasks': get_queue_tasks(users_map, locations_map),
        'versions': versions,
    }


def _enrich(blocks, ctx):
    """Enrich blocks using maps from the view context."""
    return enrich_blocks(
        blocks,
        ctx['users_map'],
        ctx['tasks_map'],
        ctx['locations_map'],
        ctx['sttngs'].get('block_color_by', 'assignee'),
    )


@schedule_bp.route('/')
def day_view():
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()

    blocks = schedule_block.get_by_date(current_date.isoformat())
    enriched = _enrich(blocks, ctx)

    # Group blocks by location for column layout
    blocks_by_location = {}
    for loc in ctx['locations_list']:
        loc_blocks = [b for b in enriched if b.get('location_id') == loc['id']]
        blocks_by_location[loc['id']] = compute_overlap_layout(loc_blocks)
    # Blocks without location
    no_loc_blocks = [b for b in enriched if not b.get('location_id')]
    if no_loc_blocks:
        blocks_by_location[''] = compute_overlap_layout(no_loc_blocks)

    return render_template(
        'schedule/views/day.html',
        current_date=current_date,
        prev_date=current_date - timedelta(days=1),
        next_date=current_date + timedelta(days=1),
        blocks=enriched,
        blocks_by_location=blocks_by_location,
        locations=ctx['locations_list'],
        time_slots=ctx['time_slots'],
        break_slots=ctx['break_slots'],
        settings=ctx['sttngs'],
        queue_tasks=ctx['queue_tasks'],
        versions=ctx['versions'],
    )


@schedule_bp.route('/week')
def week_view():
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_block.get_by_date_range(
        week_start.isoformat(), week_end.isoformat(),
    )
    enriched = _enrich(blocks, ctx)

    blocks_by_date = group_blocks_by_date(enriched)

    return render_template(
        'schedule/views/week.html',
        current_date=current_date,
        week_start=week_start,
        week_end=week_end,
        week_days=[week_start + timedelta(days=i) for i in range(7)],
        day_names=DAY_NAMES,
        prev_date=current_date - timedelta(weeks=1),
        next_date=current_date + timedelta(weeks=1),
        blocks_by_date=blocks_by_date,
        time_slots=ctx['time_slots'],
        break_slots=ctx['break_slots'],
        settings=ctx['sttngs'],
        today=date.today(),
        locations=ctx['locations_list'],
        queue_tasks=ctx['queue_tasks'],
        versions=ctx['versions'],
    )


@schedule_bp.route('/month')
def month_view():
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_block.get_by_date_range(
        first_day.isoformat(), last_day.isoformat(),
    )
    enriched = _enrich(blocks, ctx)

    blocks_by_date = group_blocks_by_date(enriched)
    prev_date, next_date = build_month_nav(year, month)

    return render_template(
        'schedule/views/month.html',
        current_date=current_date,
        year=year,
        month=month,
        weeks=build_month_weeks(year, month, blocks_by_date),
        day_names=DAY_NAMES,
        prev_date=prev_date,
        next_date=next_date,
        today=date.today(),
        settings=ctx['sttngs'],
        locations=ctx['locations_list'],
        queue_tasks=ctx['queue_tasks'],
        versions=ctx['versions'],
    )


@schedule_bp.route('/api/day')
def api_day_data():
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()
    sttngs = ctx['sttngs']

    blocks = schedule_block.get_by_date(current_date.isoformat())
    enriched = _enrich(blocks, ctx)

    time_slots = ctx['time_slots']
    return jsonify({
        'current_date': current_date.isoformat(),
        'prev_date': (current_date - timedelta(days=1)).isoformat(),
        'next_date': (current_date + timedelta(days=1)).isoformat(),
        'blocks': enriched,
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, sttngs)],
        'settings': sttngs,
        'queue_tasks': ctx['queue_tasks'],
    })


@schedule_bp.route('/api/week')
def api_week_data():
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()
    sttngs = ctx['sttngs']

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_block.get_by_date_range(week_start.isoformat(), week_end.isoformat())
    enriched = _enrich(blocks, ctx)

    time_slots = ctx['time_slots']
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
        'queue_tasks': ctx['queue_tasks'],
    })


@schedule_bp.route('/api/month')
def api_month_data():
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_block.get_by_date_range(first_day.isoformat(), last_day.isoformat())
    enriched = _enrich(blocks, ctx)

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
        'settings': ctx['sttngs'],
        'queue_tasks': ctx['queue_tasks'],
    })
