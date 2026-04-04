import calendar as cal_module
import hashlib
from datetime import date

from schedule.helpers.time_utils import (
    generate_time_slots,
    is_break_slot,
    work_minutes_in_range,
)
from schedule.models import (
    location,
    schedule_block,
    settings,
    task,
    user,
)


def _section_color(section_name):
    """Generate a consistent HSL color from section_name for visual grouping."""
    if not section_name:
        return '#94a3b8'
    h = int(hashlib.md5(section_name.encode()).hexdigest()[:8], 16)
    hue = h % 360
    return f'hsl({hue}, 55%, 45%)'


def build_maps():
    users = user.get_all()
    tasks = task.get_all()
    locations = location.get_all()
    return (
        {u['id']: u for u in users},
        {t['id']: t for t in tasks},
        {loc['id']: loc for loc in locations},
    )


def enrich_blocks(blocks, users_map, tasks_map, locations_map, color_by):
    enriched = []
    for b in blocks:
        block = dict(b)
        t = tasks_map.get(b.get('task_id'))
        loc = locations_map.get(b.get('location_id'))

        assignee_ids = b.get('assignee_ids', [])
        assignee_names = []
        assignee_colors = []
        for uid in assignee_ids:
            u = users_map.get(uid)
            if u:
                assignee_names.append(u['name'])
                assignee_colors.append(u['color'])

        is_simple = b.get('is_simple', False)
        block['procedure_id'] = t.get('procedure_id', '') if t else ''
        block['section_name'] = t.get('section_name', '') if t else ''
        if is_simple:
            block['task_title'] = b.get('title', '(블록)')
            block['section_name'] = b.get('title', '')
            block['procedure_id'] = ''
        else:
            block['task_title'] = t.get('section_name') or t.get('procedure_id', '(삭제됨)') if t else '(삭제됨)'
        block['assignee_names'] = assignee_names
        block['assignee_name'] = ', '.join(assignee_names) if assignee_names else '(미배정)'
        block['assignee_color'] = assignee_colors[0] if assignee_colors else '#6c757d'
        block['location_name'] = loc['name'] if loc else ''
        block['location_color'] = loc['color'] if loc else '#6c757d'
        block['color'] = block['location_color'] if color_by == 'location' else block['assignee_color']
        block['block_status'] = b.get('block_status', 'pending')
        block['memo'] = t.get('memo', '') if t else b.get('memo', '')
        block['identifier_ids'] = b.get('identifier_ids')
        block['is_simple'] = b.get('is_simple', False)
        block['title'] = b.get('title', '')
        block['section_color'] = _section_color(block['section_name'])
        total_ids = len(t.get('test_list', [])) if t else 0
        block_ids = b.get('identifier_ids')
        block['total_identifier_count'] = total_ids
        block['block_identifier_count'] = len(block_ids) if block_ids else total_ids
        block['is_split'] = block_ids is not None and total_ids > 0 and len(block_ids) < total_ids

        # estimated_hours for this block: if split, sum only assigned identifiers
        if block_ids and t:
            id_set = set(block_ids)
            block['estimated_hours'] = round(sum(
                item.get('estimated_hours', 0)
                for item in t.get('test_list', [])
                if isinstance(item, dict) and item.get('id') in id_set
            ), 2)
        else:
            block['estimated_hours'] = t.get('estimated_hours', 0) if t else 0

        enriched.append(block)
    return enriched


def get_queue_tasks(users_map, locations_map, version_id):
    tasks = task.get_all()
    if version_id:
        tasks = [t for t in tasks if t.get('version_id') == version_id]
    all_blocks = schedule_block.get_all()
    sttngs = settings.get()

    scheduled_hours = {}
    for b in all_blocks:
        tid = b.get('task_id')
        if not tid:
            continue
        work_min = work_minutes_in_range(b['start_time'], b['end_time'], sttngs)
        scheduled_hours[tid] = scheduled_hours.get(tid, 0) + work_min / 60.0

    queue = []
    for t in tasks:
        if t['status'] == 'completed':
            continue
        est = t.get('estimated_hours', 0)
        if est <= 0:
            continue
        remaining = est - scheduled_hours.get(t['id'], 0)
        if remaining <= 0:
            continue

        task_item = dict(t)
        task_item['remaining_unscheduled_hours'] = round(remaining, 2)
        task_item['section_color'] = _section_color(t.get('section_name', ''))

        assignee_ids = t.get('assignee_ids', [])
        assignee_names = [users_map[uid]['name'] for uid in assignee_ids if uid in users_map]
        assignee_colors = [users_map[uid]['color'] for uid in assignee_ids if uid in users_map]

        task_item['assignee_name'] = ', '.join(assignee_names) if assignee_names else '(미배정)'
        task_item['assignee_color'] = assignee_colors[0] if assignee_colors else '#6c757d'

        loc = locations_map.get(t.get('location_id'))
        task_item['location_name'] = loc['name'] if loc else ''
        task_item['location_color'] = loc['color'] if loc else '#6c757d'

        queue.append(task_item)

    queue.sort(key=lambda t: t.get('section_name', '') or t.get('procedure_id', ''))
    return queue


def get_break_slots(sttngs):
    slots = generate_time_slots(sttngs)
    return {s for s in slots if is_break_slot(s, sttngs)}


def build_month_nav(year, month):
    if month == 1:
        prev_date = date(year - 1, 12, 1)
    else:
        prev_date = date(year, month - 1, 1)
    if month == 12:
        next_date = date(year + 1, 1, 1)
    else:
        next_date = date(year, month + 1, 1)
    return prev_date, next_date


def group_blocks_by_date(enriched):
    result = {}
    for b in enriched:
        result.setdefault(b['date'], []).append(b)
    return result


def build_month_weeks(year, month, blocks_by_date):
    calendar = cal_module.Calendar(firstweekday=0)
    weeks = []
    for week in calendar.monthdayscalendar(year, month):
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


def parse_date(date_str):
    from datetime import datetime
    if date_str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    return date.today()
