import calendar as cal_module
import hashlib
from datetime import date

from app.features.schedule.helpers.time_utils import (
    generate_time_slots,
    is_break_slot,
    work_minutes_in_range,
)
from app.features.schedule.models import (
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
    # Pre-compute: all blocks per task (across entire schedule, not just current view)
    all_blocks = schedule_block.get_all()
    all_blocks_by_task = {}
    for ab in all_blocks:
        tid = ab.get('task_id')
        if tid:
            all_blocks_by_task.setdefault(tid, []).append(ab)

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

        # Determine split status: are the remaining identifiers placed elsewhere?
        if block['is_split'] and t:
            all_task_ids = set(item['id'] if isinstance(item, dict) else item
                              for item in t.get('test_list', []))
            placed_ids = set()
            for tb in all_blocks_by_task.get(b.get('task_id'), []):
                for iid in (tb.get('identifier_ids') or all_task_ids):
                    placed_ids.add(iid)
            unplaced = all_task_ids - placed_ids
            block['split_status'] = 'partial' if unplaced else 'split'
        else:
            block['split_status'] = ''

        # estimated_minutes for this block: if split, sum only assigned identifiers
        if block_ids and t:
            id_set = set(block_ids)
            block['estimated_minutes'] = sum(
                item.get('estimated_minutes', 0)
                for item in t.get('test_list', [])
                if isinstance(item, dict) and item.get('id') in id_set
            )
        else:
            block['estimated_minutes'] = t.get('estimated_minutes', 0) if t else 0

        enriched.append(block)
    return enriched


def get_queue_tasks(users_map, locations_map, version_id=None):
    tasks = task.get_all()
    all_blocks = schedule_block.get_all()
    sttngs = settings.get()

    # Build per-task block info
    task_blocks = {}  # tid → list of blocks
    for b in all_blocks:
        tid = b.get('task_id')
        if not tid:
            continue
        task_blocks.setdefault(tid, []).append(b)

    queue = []
    for t in tasks:
        if t['status'] == 'completed':
            continue
        est = t.get('estimated_minutes', 0)
        if est <= 0:
            continue

        blocks = task_blocks.get(t['id'], [])

        # If any block covers the whole task (not split), it's fully placed
        has_full_block = any(b.get('identifier_ids') is None for b in blocks)
        if has_full_block:
            continue

        # For split blocks, check which identifiers are still unscheduled
        all_ids = [item['id'] if isinstance(item, dict) else item
                   for item in t.get('test_list', [])]

        if not all_ids:
            # Task with no identifiers (e.g. simple block): show if no blocks remain
            if blocks:
                continue
            remaining = est
        else:
            scheduled_ids = set()
            for b in blocks:
                bids = b.get('identifier_ids') or []
                for bid in bids:
                    scheduled_ids.add(bid)

            unscheduled_ids = [i for i in all_ids if i not in scheduled_ids]
            if not unscheduled_ids:
                continue

            # Calculate remaining from unscheduled identifiers
            remaining = sum(
                item.get('estimated_minutes', 0)
                for item in t.get('test_list', [])
                if isinstance(item, dict) and item.get('id') in set(unscheduled_ids)
            )

        if remaining <= 0:
            continue

        task_item = dict(t)
        task_item['remaining_unscheduled_minutes'] = remaining
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
