def time_to_minutes(t):
    """Convert 'HH:MM' to total minutes."""
    parts = t.split(':')
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(m):
    """Convert total minutes to 'HH:MM'."""
    return f'{m // 60:02d}:{m % 60:02d}'


def get_break_periods(settings):
    """Return sorted list of (start_min, end_min) for lunch + breaks."""
    periods = []
    lunch_s = settings.get('lunch_start', '12:00')
    lunch_e = settings.get('lunch_end', '13:00')
    periods.append((time_to_minutes(lunch_s), time_to_minutes(lunch_e)))
    for brk in settings.get('breaks', []):
        periods.append((time_to_minutes(brk['start']), time_to_minutes(brk['end'])))
    periods.sort()
    return periods


def adjust_end_for_breaks(start_time, end_time, settings):
    """Adjust end_time so that actual work duration is preserved.

    For each break period that falls within [start_time, end_time],
    the end_time is pushed forward by the break's duration.
    This is applied iteratively since pushing end_time may expose
    additional breaks.
    """
    work_end = time_to_minutes(settings.get('work_end', '18:00'))
    start_min = time_to_minutes(start_time)
    end_min = time_to_minutes(end_time)
    work_duration = end_min - start_min
    if work_duration <= 0:
        return end_time

    breaks = get_break_periods(settings)

    current = start_min
    remaining_work = work_duration

    while remaining_work > 0:
        next_break = None
        for bs, be in breaks:
            if be <= current:
                continue
            if bs <= current:
                current = be
                continue
            next_break = (bs, be)
            break

        if next_break is None:
            current += remaining_work
            remaining_work = 0
        else:
            bs, be = next_break
            available = bs - current
            if available >= remaining_work:
                current += remaining_work
                remaining_work = 0
            else:
                remaining_work -= available
                current = be

    if current > work_end:
        current = work_end

    return minutes_to_time(current)


def work_minutes_in_range(start_time, end_time, settings):
    """Calculate actual work minutes in a time range, excluding breaks."""
    breaks = get_break_periods(settings)
    start_min = time_to_minutes(start_time)
    end_min = time_to_minutes(end_time)
    total = end_min - start_min
    for bs, be in breaks:
        overlap_start = max(start_min, bs)
        overlap_end = min(end_min, be)
        if overlap_start < overlap_end:
            total -= (overlap_end - overlap_start)
    return max(0, total)


def generate_time_slots(settings):
    """Generate list of time slot strings from work_start to work_end."""
    from datetime import datetime, timedelta
    interval = settings.get('grid_interval_minutes', 15)
    start = datetime.strptime(settings['work_start'], '%H:%M')
    end = datetime.strptime(settings['work_end'], '%H:%M')
    slots = []
    current = start
    while current < end:
        slots.append(current.strftime('%H:%M'))
        current += timedelta(minutes=interval)
    return slots


def is_break_slot(time_str, settings):
    """Check if a time slot falls within lunch or break periods."""
    lunch_start = settings.get('lunch_start', '12:00')
    lunch_end = settings.get('lunch_end', '13:00')
    if lunch_start <= time_str < lunch_end:
        return True
    for brk in settings.get('breaks', []):
        if brk['start'] <= time_str < brk['end']:
            return True
    return False
