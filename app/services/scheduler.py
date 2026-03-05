from datetime import datetime, timedelta, date


def time_to_minutes(time_str):
    """'HH:MM' 문자열을 자정 기준 분으로 변환."""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m


def minutes_to_time(minutes):
    """분을 'HH:MM' 문자열로 변환."""
    h = minutes // 60
    m = minutes % 60
    return f'{h:02d}:{m:02d}'


def get_available_slots(date_str, work_hours, occupied_slots):
    """
    주어진 날짜의 가용 시간 슬롯 목록을 계산.
    반환: [(start_min, end_min), ...] 형태의 가용 구간 목록
    """
    work_start = time_to_minutes(work_hours['work_start'])
    work_end = time_to_minutes(work_hours['work_end'])
    lunch_start = time_to_minutes(work_hours['lunch_start'])
    lunch_end = time_to_minutes(work_hours['lunch_end'])

    # 기본 가용 구간: 근무 시작~점심 시작, 점심 끝~근무 종료
    base_slots = [
        (work_start, lunch_start),
        (lunch_end, work_end),
    ]

    # 기존 확정 블록으로 인해 점유된 구간 제거
    busy = []
    for block in (occupied_slots or []):
        busy.append((
            time_to_minutes(block['start_time']),
            time_to_minutes(block['end_time'])
        ))

    # 점유 구간을 제외한 실제 가용 구간 계산
    free_slots = []
    for (slot_start, slot_end) in base_slots:
        free = [(slot_start, slot_end)]
        for (b_start, b_end) in busy:
            new_free = []
            for (f_start, f_end) in free:
                if b_end <= f_start or b_start >= f_end:
                    new_free.append((f_start, f_end))
                else:
                    if f_start < b_start:
                        new_free.append((f_start, b_start))
                    if b_end < f_end:
                        new_free.append((b_end, f_end))
            free = new_free
        free_slots.extend(free)

    return free_slots


def schedule_task_in_slots(task_minutes, available_slots):
    """
    업무를 가용 슬롯에 배치. 점심을 걸치는 경우 분할하여 배치.
    반환: [(start_min, end_min), ...] 배치된 블록 목록, 또는 [] (배치 불가)
    """
    remaining = task_minutes
    blocks = []

    for (slot_start, slot_end) in available_slots:
        if remaining <= 0:
            break
        slot_duration = slot_end - slot_start
        use = min(remaining, slot_duration)
        blocks.append((slot_start, slot_start + use))
        remaining -= use

    return blocks if remaining <= 0 else []


def generate_draft(tasks, work_hours, occupied_by_date, start_date, days=14):
    """
    스케줄링 초안 생성 알고리즘.

    Args:
        tasks: 배치할 업무 목록 (각 업무는 dict with id, estimated_minutes, priority)
        work_hours: 근무시간 설정 dict
        occupied_by_date: {date_str: [{'start_time': str, 'end_time': str}]} 기존 확정 블록
        start_date: 시작 날짜 (date 객체)
        days: 최대 배치 일수

    Returns:
        draft_blocks: [{'task_id': int, 'assigned_date': str,
                        'start_time': str, 'end_time': str}, ...]
    """
    priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}

    work_start = time_to_minutes(work_hours['work_start'])
    work_end = time_to_minutes(work_hours['work_end'])
    lunch_start = time_to_minutes(work_hours['lunch_start'])
    lunch_end = time_to_minutes(work_hours['lunch_end'])
    total_work_minutes = (work_end - work_start) - (lunch_end - lunch_start)

    def sort_key(task):
        # 당일 완료 가능 업무 먼저, 같은 조건이면 우선순위 높은 것, 소요시간 짧은 것 우선
        fits_today = 1 if task['estimated_minutes'] <= total_work_minutes else 0
        return (-fits_today, priority_order.get(task['priority'], 2), task['estimated_minutes'])

    sorted_tasks = sorted(tasks, key=sort_key)

    draft_blocks = []
    # 날짜별 초안 블록 추적 (점유 계산에 포함)
    date_slots_used = {}

    for task in sorted_tasks:
        task_minutes = task['estimated_minutes']
        remaining = task_minutes

        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            date_str = current_date.strftime('%Y-%m-%d')

            occupied = list(occupied_by_date.get(date_str, []))
            # 이미 배치된 초안 블록도 점유로 추가
            for (s, e) in date_slots_used.get(date_str, []):
                occupied.append({'start_time': s, 'end_time': e})

            free_slots = get_available_slots(date_str, work_hours, occupied)
            total_free = sum(e - s for s, e in free_slots)

            if total_free <= 0:
                continue

            # 남은 업무를 한 번에 배치 시도
            blocks = schedule_task_in_slots(remaining, free_slots)
            if blocks:
                for (b_start, b_end) in blocks:
                    start_str = minutes_to_time(b_start)
                    end_str = minutes_to_time(b_end)
                    draft_blocks.append({
                        'task_id': task['id'],
                        'assigned_date': date_str,
                        'start_time': start_str,
                        'end_time': end_str,
                    })
                    date_slots_used.setdefault(date_str, []).append((start_str, end_str))
                remaining = 0
                break
            else:
                # 당일에 전부 못 들어가면 가능한 만큼 채우고 나머지는 다음날
                for (slot_start, slot_end) in free_slots:
                    if remaining <= 0:
                        break
                    use = min(remaining, slot_end - slot_start)
                    start_str = minutes_to_time(slot_start)
                    end_str = minutes_to_time(slot_start + use)
                    draft_blocks.append({
                        'task_id': task['id'],
                        'assigned_date': date_str,
                        'start_time': start_str,
                        'end_time': end_str,
                    })
                    date_slots_used.setdefault(date_str, []).append((start_str, end_str))
                    remaining -= use

                if remaining <= 0:
                    break

    return draft_blocks
