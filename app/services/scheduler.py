from datetime import datetime, timedelta

from app.repositories import task_repo, schedule_repo, settings_repo

PRIORITY_ORDER = {'high': 0, 'medium': 1, 'low': 2}


def generate_draft_schedule(version_id):
    settings = settings_repo.get()
    max_days = settings.get('max_schedule_days', 14)

    tasks = [
        t for t in task_repo.get_all()
        if t.get('version_id') == version_id
        and t['status'] != 'completed'
        and t.get('remaining_hours', 0) > 0
    ]

    tasks.sort(key=lambda t: (
        t.get('deadline') or '9999-12-31',
        t.get('procedure_id', ''),
    ))

    schedule_repo.delete_drafts()

    confirmed_blocks = [b for b in schedule_repo.get_all() if not b.get('is_draft')]
    all_blocks = list(confirmed_blocks)

    placed = []
    unplaced = []

    daily_work_hours = _daily_available_hours(settings)

    for task in tasks:
        hours_needed = task['remaining_hours']

        if hours_needed > daily_work_hours:
            unplaced.append({
                'task': task,
                'remaining_unscheduled_hours': hours_needed,
                'reason': f'소요시간({hours_needed}h)이 일일 가용시간({daily_work_hours}h)을 초과합니다.',
            })
            continue

        confirmed_for_task = [b for b in confirmed_blocks if b['task_id'] == task['id']]
        already_scheduled = _calculate_work_hours(confirmed_for_task, settings)
        if already_scheduled >= hours_needed:
            continue

        task_placed = False

        for day_offset in range(max_days):
            date_str = (datetime.now() + timedelta(days=day_offset)).strftime('%Y-%m-%d')

            slot = _find_slot_for_task(date_str, task, hours_needed, all_blocks, settings)
            if slot:
                start_time, end_time = slot
                block = schedule_repo.create(
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

    return {'placed': placed, 'unplaced': unplaced}


def _find_slot_for_task(date_str, task, hours_needed, all_blocks, settings):
    actual_start = settings.get('actual_work_start', '08:30')
    actual_end = settings.get('actual_work_end', '16:30')

    assignee_occupied = []
    for b in all_blocks:
        if b['date'] != date_str:
            continue
        block_assignees = b.get('assignee_ids', [])
        if any(a in block_assignees for a in task['assignee_ids']):
            assignee_occupied.append((_parse_time(b['start_time']), _parse_time(b['end_time'])))

    location_occupied = []
    for b in all_blocks:
        if b['date'] != date_str:
            continue
        if b.get('location_id') == task['location_id'] and task['location_id']:
            location_occupied.append((_parse_time(b['start_time']), _parse_time(b['end_time'])))

    all_occupied = assignee_occupied + location_occupied
    all_occupied.sort()

    free = _get_free_ranges(actual_start, actual_end, all_occupied)

    for free_start_str, free_end_str in free:
        available_hours = _work_hours_in_range(free_start_str, free_end_str, settings)
        if available_hours >= hours_needed:
            end_time = _compute_end_for_work_hours(free_start_str, hours_needed, settings)
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


def _daily_available_hours(settings):
    actual_start = settings.get('actual_work_start', '08:30')
    actual_end = settings.get('actual_work_end', '16:30')
    return _work_hours_in_range(actual_start, actual_end, settings)


def approve_drafts():
    settings = settings_repo.get()
    draft_blocks = [b for b in schedule_repo.get_all() if b.get('is_draft')]

    schedule_repo.approve_drafts()

    hours_by_task = {}
    for block in draft_blocks:
        work_hours = _work_hours_in_range(block['start_time'], block['end_time'], settings)
        hours_by_task.setdefault(block['task_id'], 0)
        hours_by_task[block['task_id']] += work_hours

    for task_id, hours in hours_by_task.items():
        task = task_repo.get_by_id(task_id)
        if not task:
            continue
        new_remaining = max(0, task['remaining_hours'] - hours)
        new_status = 'completed' if new_remaining <= 0 else task['status']
        task_repo.patch(
            task_id,
            remaining_hours=round(new_remaining, 2),
            status=new_status,
        )


def discard_drafts():
    schedule_repo.delete_drafts()


def _get_break_periods(settings):
    periods = [(settings['lunch_start'], settings['lunch_end'])]
    for brk in settings.get('breaks', []):
        periods.append((brk['start'], brk['end']))
    periods.sort()
    return periods


def _work_hours_in_range(start_str, end_str, settings):
    start = _parse_time(start_str)
    end = _parse_time(end_str)
    total_min = (end - start).total_seconds() / 60.0
    for bs, be in _get_break_periods(settings):
        b_start = _parse_time(bs)
        b_end = _parse_time(be)
        ov_start = max(start, b_start)
        ov_end = min(end, b_end)
        if ov_start < ov_end:
            total_min -= (ov_end - ov_start).total_seconds() / 60.0
    return max(0.0, total_min / 60.0)


def _compute_end_for_work_hours(start_str, work_hours, settings):
    breaks = _get_break_periods(settings)
    work_end = settings.get('actual_work_end', '16:30')
    current = _parse_time(start_str)
    remaining_min = work_hours * 60.0
    end_limit = _parse_time(work_end)
    interval = settings.get('grid_interval_minutes', 15)

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


def _calculate_work_hours(blocks, settings):
    total = 0.0
    for b in blocks:
        total += _work_hours_in_range(b['start_time'], b['end_time'], settings)
    return total


def _parse_time(time_str):
    return datetime.strptime(time_str, '%H:%M')


def _format_time(dt):
    return dt.strftime('%H:%M')
