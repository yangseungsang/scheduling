from datetime import datetime, timedelta

from schedule.models import task as task_model
from schedule.models import schedule_block, settings

PRIORITY_ORDER = {'high': 0, 'medium': 1, 'low': 2}


def generate_draft_schedule(version_id, start_date=None, end_date=None,
                            include_existing=False):
    """Generate a draft schedule for tasks in the given version.

    Args:
        version_id: Software version to schedule.
        start_date: First date (YYYY-MM-DD). Defaults to today.
        end_date: Last date (YYYY-MM-DD). Defaults to start_date + max_schedule_days.
        include_existing: If True, reschedule already-placed (non-locked) blocks too.
    """
    sttngs = settings.get()

    if start_date:
        first_day = datetime.strptime(start_date, '%Y-%m-%d')
    else:
        first_day = datetime.now()

    if end_date:
        last_day = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        max_days = sttngs.get('max_schedule_days', 14)
        last_day = first_day + timedelta(days=max_days - 1)

    # Build list of workdays (exclude weekends)
    workdays = []
    d = first_day
    while d <= last_day:
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            workdays.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)

    if not workdays:
        return {'placed': [], 'unplaced': [], 'workdays': 0}

    # 1. Get schedulable tasks for this version
    tasks = [
        t for t in task_model.get_all()
        if t.get('version_id') == version_id
        and t['status'] != 'completed'
        and t.get('remaining_hours', 0) > 0
    ]

    tasks.sort(key=lambda t: t.get('procedure_id', ''))

    # 2. Handle existing blocks
    schedule_block.delete_drafts()

    if include_existing:
        # Remove non-locked blocks in date range for this version (reschedule them)
        all_current = schedule_block.get_all()
        for b in all_current:
            if (b.get('version_id') == version_id
                    and not b.get('is_locked')
                    and not b.get('is_draft')
                    and b['date'] >= workdays[0]
                    and b['date'] <= workdays[-1]):
                schedule_block.delete(b['id'])

    confirmed_blocks = [b for b in schedule_block.get_all() if not b.get('is_draft')]
    all_blocks = list(confirmed_blocks)

    placed = []
    unplaced = []

    daily_work_hours = _daily_available_hours(sttngs)

    for task in tasks:
        hours_needed = task['remaining_hours']

        if hours_needed > daily_work_hours:
            unplaced.append({
                'task': task,
                'remaining_unscheduled_hours': hours_needed,
                'reason': f'소요시간({int(hours_needed * 60)}분)이 일일 가용시간({int(daily_work_hours * 60)}분)을 초과합니다.',
            })
            continue

        confirmed_for_task = [b for b in confirmed_blocks if b['task_id'] == task['id']]
        already_scheduled = _calculate_work_hours(confirmed_for_task, sttngs)
        if already_scheduled >= hours_needed:
            continue

        task_placed = False

        for date_str in workdays:
            slot = _find_slot_for_task(date_str, task, hours_needed, all_blocks, sttngs)
            if slot:
                start_time, end_time = slot
                block = schedule_block.create(
                    task_id=task['id'],
                    assignee_ids=task['assignee_ids'],
                    location_id=task['location_id'],
                    version_id=version_id,
                    date=date_str,
                    start_time=start_time,
                    end_time=end_time,
                    is_draft=True,
                    is_locked=False,
                    origin='auto',
                )
                placed.append(block)
                all_blocks.append(block)
                task_placed = True
                break

        if not task_placed:
            unplaced.append({
                'task': task,
                'remaining_unscheduled_hours': hours_needed,
            })

    return {'placed': placed, 'unplaced': unplaced, 'workdays': len(workdays)}


def _find_slot_for_task(date_str, task, hours_needed, all_blocks, sttngs):
    actual_start = sttngs.get('actual_work_start', '08:30')
    actual_end = sttngs.get('actual_work_end', '16:30')

    # Only check location conflicts -- assignee overlap is allowed
    location_occupied = []
    if task['location_id']:
        for b in all_blocks:
            if b['date'] != date_str:
                continue
            if b.get('location_id') == task['location_id']:
                location_occupied.append((_parse_time(b['start_time']), _parse_time(b['end_time'])))

    location_occupied.sort()

    free = _get_free_ranges(actual_start, actual_end, location_occupied)

    for free_start_str, free_end_str in free:
        available_hours = _work_hours_in_range(free_start_str, free_end_str, sttngs)
        if available_hours >= hours_needed:
            end_time = _compute_end_for_work_hours(free_start_str, hours_needed, sttngs)
            return (free_start_str, end_time)

    return None


def _get_free_ranges(work_start, work_end, occupied):
    current = _parse_time(work_start)
    end = _parse_time(work_end)
    free = []

    merged = _merge_ranges(occupied)

    for occ_start, occ_end in merged:
        if current < occ_start:
            free.append((_format_time(current), _format_time(occ_start)))
        current = max(current, occ_end)

    if current < end:
        free.append((_format_time(current), _format_time(end)))

    return free


def _merge_ranges(ranges):
    if not ranges:
        return []
    sorted_ranges = sorted(ranges)
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _daily_available_hours(sttngs):
    actual_start = sttngs.get('actual_work_start', '08:30')
    actual_end = sttngs.get('actual_work_end', '16:30')
    return _work_hours_in_range(actual_start, actual_end, sttngs)


def approve_drafts():
    sttngs = settings.get()
    draft_blocks = [b for b in schedule_block.get_all() if b.get('is_draft')]

    schedule_block.approve_drafts()

    hours_by_task = {}
    for block in draft_blocks:
        work_hours = _work_hours_in_range(block['start_time'], block['end_time'], sttngs)
        hours_by_task.setdefault(block['task_id'], 0)
        hours_by_task[block['task_id']] += work_hours

    for task_id, hours in hours_by_task.items():
        task = task_model.get_by_id(task_id)
        if not task:
            continue
        new_remaining = max(0, task['remaining_hours'] - hours)
        new_status = 'completed' if new_remaining <= 0 else task['status']
        task_model.patch(
            task_id,
            remaining_hours=round(new_remaining, 2),
            status=new_status,
        )


def discard_drafts():
    schedule_block.delete_drafts()


def _get_break_periods(sttngs):
    periods = [(sttngs['lunch_start'], sttngs['lunch_end'])]
    for brk in sttngs.get('breaks', []):
        periods.append((brk['start'], brk['end']))
    periods.sort()
    return periods


def _work_hours_in_range(start_str, end_str, sttngs):
    start = _parse_time(start_str)
    end = _parse_time(end_str)
    total_min = (end - start).total_seconds() / 60.0
    for bs, be in _get_break_periods(sttngs):
        b_start = _parse_time(bs)
        b_end = _parse_time(be)
        ov_start = max(start, b_start)
        ov_end = min(end, b_end)
        if ov_start < ov_end:
            total_min -= (ov_end - ov_start).total_seconds() / 60.0
    return max(0.0, total_min / 60.0)


def _compute_end_for_work_hours(start_str, work_hours, sttngs):
    breaks = _get_break_periods(sttngs)
    work_end = sttngs.get('actual_work_end', '16:30')
    current = _parse_time(start_str)
    remaining_min = work_hours * 60.0
    end_limit = _parse_time(work_end)
    interval = sttngs.get('grid_interval_minutes', 15)

    while remaining_min > 0 and current < end_limit:
        in_break = False
        for bs, be in breaks:
            b_start = _parse_time(bs)
            b_end = _parse_time(be)
            if b_start <= current < b_end:
                current = b_end
                in_break = True
                break
        if in_break:
            continue

        next_break_start = end_limit
        for bs, be in breaks:
            b_start = _parse_time(bs)
            if b_start > current and b_start < next_break_start:
                next_break_start = b_start

        available_min = (next_break_start - current).total_seconds() / 60.0
        if available_min >= remaining_min:
            current += timedelta(minutes=remaining_min)
            remaining_min = 0
        else:
            remaining_min -= available_min
            for bs, be in breaks:
                if _parse_time(bs) == next_break_start:
                    current = _parse_time(be)
                    break

    result_min = int((current - datetime(1900, 1, 1)).total_seconds() / 60)
    snapped = ((result_min + interval - 1) // interval) * interval
    result = datetime(1900, 1, 1) + timedelta(minutes=snapped)
    if result > end_limit:
        result = end_limit
    return _format_time(result)


def _calculate_work_hours(blocks, sttngs):
    total = 0.0
    for b in blocks:
        total += _work_hours_in_range(b['start_time'], b['end_time'], sttngs)
    return total


def _parse_time(time_str):
    return datetime.strptime(time_str, '%H:%M')


def _format_time(dt):
    return dt.strftime('%H:%M')
