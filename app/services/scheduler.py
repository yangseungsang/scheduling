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
        already_scheduled = _calculate_block_hours(confirmed_for_task)
        hours_needed = task['remaining_hours'] - already_scheduled

        if hours_needed <= 0:
            continue

        task_placed_blocks = []

        # Try each day starting from today, up to max_schedule_days
        for day_offset in range(max_days):
            if hours_needed <= 0:
                break

            date_str = (
                datetime.now() + timedelta(days=day_offset)
            ).strftime('%Y-%m-%d')

            assignee_blocks = blocks_by_assignee.get(assignee_id, [])
            slots = _get_available_slots(
                date_str, assignee_id, assignee_blocks, settings
            )

            for slot_start, slot_end in slots:
                if hours_needed <= 0:
                    break

                slot_hours = _time_diff_hours(slot_start, slot_end)
                block_hours = min(slot_hours, hours_needed)

                # Calculate end time for this block
                block_end = _add_hours(slot_start, block_hours)

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
                hours_needed -= block_hours

        if hours_needed > 0:
            unplaced.append({
                'task': task,
                'remaining_unscheduled_hours': hours_needed,
            })

    return {'placed': placed, 'unplaced': unplaced}


def approve_drafts():
    """Approve all draft blocks and update task remaining hours."""
    draft_blocks = [b for b in schedule_repo.get_all() if b.get('is_draft')]

    # Approve in the repo (sets is_draft=False)
    schedule_repo.approve_drafts()

    # Update task remaining_hours for each approved block
    # Group by task to batch updates
    hours_by_task = {}
    for block in draft_blocks:
        block_hours = _time_diff_hours(block['start_time'], block['end_time'])
        hours_by_task.setdefault(block['task_id'], 0)
        hours_by_task[block['task_id']] += block_hours

    for task_id, hours in hours_by_task.items():
        task = task_repo.get_by_id(task_id)
        if not task:
            continue

        new_remaining = max(0, task['remaining_hours'] - hours)
        new_status = 'completed' if new_remaining <= 0 else task['status']

        task_repo.update(
            task_id=task_id,
            title=task['title'],
            description=task.get('description', ''),
            assignee_id=task['assignee_id'],
            category_id=task.get('category_id', ''),
            priority=task['priority'],
            estimated_hours=task['estimated_hours'],
            remaining_hours=new_remaining,
            deadline=task.get('deadline', ''),
            status=new_status,
        )


def discard_drafts():
    """Discard all draft blocks."""
    schedule_repo.delete_drafts()


def _get_available_slots(date_str, assignee_id, existing_blocks, settings):
    """Return list of (start_time, end_time) available slot tuples for a date.

    Generates grid-interval slots within work hours, removes lunch/breaks
    and occupied slots, then merges consecutive slots into contiguous ranges.
    """
    work_start = settings['work_start']
    work_end = settings['work_end']
    lunch_start = settings['lunch_start']
    lunch_end = settings['lunch_end']
    breaks = settings.get('breaks', [])
    interval = settings.get('grid_interval_minutes', 15)

    # Generate all grid slots within work hours
    grid_slots = []
    current = _parse_time(work_start)
    end = _parse_time(work_end)

    while current < end:
        slot_end = current + timedelta(minutes=interval)
        if slot_end > end:
            slot_end = end
        grid_slots.append((_format_time(current), _format_time(slot_end)))
        current = slot_end

    # Remove lunch time slots
    grid_slots = [
        (s, e) for s, e in grid_slots
        if not _overlaps(s, e, lunch_start, lunch_end)
    ]

    # Remove break time slots
    for brk in breaks:
        grid_slots = [
            (s, e) for s, e in grid_slots
            if not _overlaps(s, e, brk['start'], brk['end'])
        ]

    # Remove slots occupied by existing blocks for this assignee on this date
    assignee_day_blocks = [
        b for b in existing_blocks
        if b['date'] == date_str and b['assignee_id'] == assignee_id
    ]
    for block in assignee_day_blocks:
        grid_slots = [
            (s, e) for s, e in grid_slots
            if not _overlaps(s, e, block['start_time'], block['end_time'])
        ]

    # Merge consecutive slots into contiguous ranges
    if not grid_slots:
        return []

    merged = []
    range_start, range_end = grid_slots[0]

    for s, e in grid_slots[1:]:
        if s == range_end:
            range_end = e
        else:
            merged.append((range_start, range_end))
            range_start, range_end = s, e

    merged.append((range_start, range_end))
    return merged


def _calculate_block_hours(blocks):
    """Sum up hours from a list of schedule blocks."""
    total = 0.0
    for b in blocks:
        total += _time_diff_hours(b['start_time'], b['end_time'])
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


def _time_diff_hours(start_str, end_str):
    """Calculate the difference in hours between two 'HH:MM' strings."""
    start = _parse_time(start_str)
    end = _parse_time(end_str)
    delta = (end - start).total_seconds() / 3600
    return max(0.0, delta)


def _add_hours(time_str, hours):
    """Add fractional hours to an 'HH:MM' time string, return 'HH:MM'."""
    dt = _parse_time(time_str)
    dt += timedelta(hours=hours)
    return _format_time(dt)


def _overlaps(s1, e1, s2, e2):
    """Check if time range (s1, e1) overlaps with (s2, e2).

    All arguments are 'HH:MM' strings. Overlap means the intersection
    has positive duration (touching endpoints do not count).
    """
    start1 = _parse_time(s1)
    end1 = _parse_time(e1)
    start2 = _parse_time(s2)
    end2 = _parse_time(e2)
    return start1 < end2 and start2 < end1
