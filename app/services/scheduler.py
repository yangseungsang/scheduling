from datetime import datetime, timedelta

from app.repositories import task_repo, schedule_repo, settings_repo, user_repo

PRIORITY_ORDER = {'high': 0, 'medium': 1, 'low': 2}


def generate_draft_schedule():
    """Generate a draft schedule for all incomplete tasks.

    Returns dict with 'placed' (list of created blocks) and
    'unplaced' (list of tasks that could not be fully scheduled).
    """
    settings = settings_repo.get()
    today = datetime.now().strftime('%Y-%m-%d')
    max_days = settings.get('max_schedule_days', 14)

    # 1. Get schedulable tasks
    tasks = [
        t for t in task_repo.get_all()
        if t['status'] != 'completed' and t.get('remaining_hours', 0) > 0
    ]

    # 2. Sort: deadline ascending, then priority (high > medium > low)
    tasks.sort(key=lambda t: (
        t.get('deadline') or '9999-12-31',
        PRIORITY_ORDER.get(t.get('priority', 'low'), 2),
    ))

    # 3. Delete existing drafts
    schedule_repo.delete_drafts()

    # 4. Get confirmed blocks (non-draft) — these must not be overlapped
    confirmed_blocks = [b for b in schedule_repo.get_all() if not b.get('is_draft')]

    # Track all blocks per assignee (confirmed + newly placed drafts)
    # Key: assignee_id, Value: list of block dicts
    blocks_by_assignee = {}
    for b in confirmed_blocks:
        blocks_by_assignee.setdefault(b['assignee_id'], []).append(b)

    placed = []
    unplaced = []

    # 5. Place blocks for each task
    for task in tasks:
        assignee_id = task['assignee_id']

        # Hours already covered by confirmed blocks for this task
        confirmed_for_task = [
            b for b in confirmed_blocks if b['task_id'] == task['id']
        ]
        already_scheduled = _calculate_work_hours(confirmed_for_task, settings)
        hours_needed = task['remaining_hours'] - already_scheduled

        if hours_needed <= 0:
            continue

        # Try each day starting from today, up to max_schedule_days
        for day_offset in range(max_days):
            if hours_needed <= 0:
                break

            date_str = (
                datetime.now() + timedelta(days=day_offset)
            ).strftime('%Y-%m-%d')

            assignee_blocks = blocks_by_assignee.get(assignee_id, [])
            slots = _get_available_work_slots(
                date_str, assignee_id, assignee_blocks, settings
            )

            for slot_start, slot_end, work_hours in slots:
                if hours_needed <= 0:
                    break

                if hours_needed >= work_hours:
                    # Use the entire slot
                    block_end = slot_end
                    used_hours = work_hours
                else:
                    # Partially fill — compute end time for needed work hours
                    block_end = _compute_end_for_work_hours(
                        slot_start, hours_needed, settings
                    )
                    used_hours = hours_needed

                block = schedule_repo.create(
                    task_id=task['id'],
                    assignee_id=assignee_id,
                    date=date_str,
                    start_time=slot_start,
                    end_time=block_end,
                    is_draft=True,
                    is_locked=False,
                    origin='auto',
                )

                placed.append(block)
                blocks_by_assignee.setdefault(assignee_id, []).append(block)
                hours_needed -= used_hours

        if hours_needed > 0:
            unplaced.append({
                'task': task,
                'remaining_unscheduled_hours': hours_needed,
            })

    return {'placed': placed, 'unplaced': unplaced}


def approve_drafts():
    """Approve all draft blocks and update task remaining hours."""
    settings = settings_repo.get()
    draft_blocks = [b for b in schedule_repo.get_all() if b.get('is_draft')]

    # Approve in the repo (sets is_draft=False)
    schedule_repo.approve_drafts()

    # Update task remaining_hours — use work hours (excluding breaks)
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
    """Discard all draft blocks."""
    schedule_repo.delete_drafts()


def _get_break_periods(settings):
    """Return sorted list of (start_str, end_str) for lunch + breaks."""
    periods = [(settings['lunch_start'], settings['lunch_end'])]
    for brk in settings.get('breaks', []):
        periods.append((brk['start'], brk['end']))
    periods.sort()
    return periods


def _work_hours_in_range(start_str, end_str, settings):
    """Calculate actual work hours in a time range, excluding breaks."""
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
    """Compute end time that provides exactly work_hours of actual work from start_str.

    Walks forward from start, skipping break periods.
    """
    breaks = _get_break_periods(settings)
    work_end = settings.get('work_end', '18:00')
    current = _parse_time(start_str)
    remaining_min = work_hours * 60.0
    end_limit = _parse_time(work_end)
    interval = settings.get('grid_interval_minutes', 15)

    while remaining_min > 0 and current < end_limit:
        # Check if we're inside a break
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

        # Find next break start
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
            # Jump to end of the break
            for bs, be in breaks:
                if _parse_time(bs) == next_break_start:
                    current = _parse_time(be)
                    break

    # Snap to grid
    result_min = int((current - datetime(1900, 1, 1)).total_seconds() / 60)
    snapped = ((result_min + interval - 1) // interval) * interval
    result = datetime(1900, 1, 1) + timedelta(minutes=snapped)
    if result > end_limit:
        result = end_limit
    return _format_time(result)


def _get_available_work_slots(date_str, assignee_id, existing_blocks, settings):
    """Return list of (start_time, end_time, work_hours) tuples.

    Unlike the old version, slots span across breaks (not split by them).
    Only existing assigned blocks cause splits.
    """
    work_start = settings['work_start']
    work_end = settings['work_end']
    interval = settings.get('grid_interval_minutes', 15)

    # Get occupied time ranges for this assignee on this date
    occupied = []
    for b in existing_blocks:
        if b['date'] == date_str and b['assignee_id'] == assignee_id:
            occupied.append((_parse_time(b['start_time']), _parse_time(b['end_time'])))
    occupied.sort()

    # Build free ranges (not split by breaks, only by occupied blocks)
    free = []
    current = _parse_time(work_start)
    end = _parse_time(work_end)

    for occ_start, occ_end in occupied:
        if current < occ_start:
            free.append((_format_time(current), _format_time(occ_start)))
        current = max(current, occ_end)

    if current < end:
        free.append((_format_time(current), _format_time(end)))

    # Calculate actual work hours for each free range
    result = []
    for s, e in free:
        wh = _work_hours_in_range(s, e, settings)
        if wh > 0:
            result.append((s, e, round(wh, 4)))

    return result


def _calculate_work_hours(blocks, settings):
    """Sum up actual work hours from a list of schedule blocks (excluding breaks)."""
    total = 0.0
    for b in blocks:
        total += _work_hours_in_range(b['start_time'], b['end_time'], settings)
    return total


# ---------------------------------------------------------------------------
# Time utility helpers
# ---------------------------------------------------------------------------

def _parse_time(time_str):
    """Parse 'HH:MM' string to a datetime (date part is arbitrary)."""
    return datetime.strptime(time_str, '%H:%M')


def _format_time(dt):
    """Format a datetime to 'HH:MM' string."""
    return dt.strftime('%H:%M')


