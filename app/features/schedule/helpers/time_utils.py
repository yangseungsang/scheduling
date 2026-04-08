"""시간 관련 유틸리티 모듈.

시간 문자열 ↔ 분 단위 변환, 휴식 시간 처리, 실제 근무 시간 계산,
시간 슬롯 생성 등 스케줄 시간 관리에 필요한 핵심 함수를 제공한다.
"""


def time_to_minutes(t):
    """'HH:MM' 형식의 시간 문자열을 분 단위 정수로 변환한다.

    Args:
        t: 시간 문자열 (예: '09:30').

    Returns:
        int: 자정부터의 총 분 수 (예: 570).
    """
    parts = t.split(':')
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(m):
    """분 단위 정수를 'HH:MM' 형식의 시간 문자열로 변환한다.

    Args:
        m: 자정부터의 총 분 수 (int).

    Returns:
        str: 시간 문자열 (예: '09:30').
    """
    return f'{m // 60:02d}:{m % 60:02d}'


def get_break_periods(settings):
    """설정에서 점심·휴식 시간 구간 목록을 추출한다.

    점심 시간과 추가 휴식 시간을 모두 포함하여
    (시작분, 종료분) 튜플 목록으로 반환한다.

    Args:
        settings: 설정 딕셔너리. lunch_start, lunch_end, breaks 키 포함.

    Returns:
        list: [(start_min, end_min), ...] 형태의 정렬된 휴식 구간 목록.
    """
    periods = []
    # 점심 시간 추가
    lunch_s = settings.get('lunch_start', '12:00')
    lunch_e = settings.get('lunch_end', '13:00')
    periods.append((time_to_minutes(lunch_s), time_to_minutes(lunch_e)))
    # 추가 휴식 시간 추가
    for brk in settings.get('breaks', []):
        periods.append((time_to_minutes(brk['start']), time_to_minutes(brk['end'])))
    periods.sort()
    return periods


def adjust_end_for_breaks(start_time, end_time, settings):
    """휴식 시간을 고려하여 종료 시간을 조정한다.

    시작~종료 사이의 순수 작업 시간(work_duration)을 보존하면서,
    중간에 끼는 휴식 시간만큼 종료 시간을 뒤로 밀어준다.
    반복적으로 적용하여 밀린 종료 시간에 새로 포함되는 휴식도 처리한다.

    Args:
        start_time: 시작 시간 ('HH:MM').
        end_time: 원래 종료 시간 ('HH:MM'). 휴식 미포함 기준.
        settings: 설정 딕셔너리 (work_end, lunch_start 등 포함).

    Returns:
        str: 휴식 시간이 반영된 조정 종료 시간 ('HH:MM').
    """
    work_end = time_to_minutes(settings.get('work_end', '18:00'))
    start_min = time_to_minutes(start_time)
    end_min = time_to_minutes(end_time)
    work_duration = end_min - start_min  # 보존해야 할 순수 작업 시간
    if work_duration <= 0:
        return end_time

    breaks = get_break_periods(settings)

    current = start_min       # 현재 시간 포인터
    remaining_work = work_duration  # 남은 작업 시간

    while remaining_work > 0:
        # 현재 시간 이후의 가장 가까운 휴식 구간 찾기
        next_break = None
        for bs, be in breaks:
            if be <= current:
                # 이미 지난 휴식은 건너뜀
                continue
            if bs <= current:
                # 현재 시간이 휴식 구간 안이면 휴식 끝으로 점프
                current = be
                continue
            next_break = (bs, be)
            break

        if next_break is None:
            # 더 이상 휴식이 없으면 남은 시간만큼 직진
            current += remaining_work
            remaining_work = 0
        else:
            bs, be = next_break
            available = bs - current  # 다음 휴식까지 가용 작업 시간
            if available >= remaining_work:
                # 가용 시간이 충분하면 작업 완료
                current += remaining_work
                remaining_work = 0
            else:
                # 가용 시간을 소진하고 휴식 뒤로 이동
                remaining_work -= available
                current = be

    # 근무 종료 시간을 초과하지 않도록 제한
    if current > work_end:
        current = work_end

    return minutes_to_time(current)


def work_minutes_in_range(start_time, end_time, settings):
    """시간 범위 내의 실제 근무 시간(분)을 계산한다.

    전체 시간 범위에서 휴식 시간과 겹치는 부분을 차감한다.

    Args:
        start_time: 시작 시간 ('HH:MM').
        end_time: 종료 시간 ('HH:MM').
        settings: 설정 딕셔너리.

    Returns:
        int: 실제 근무 시간(분). 음수가 되면 0 반환.
    """
    breaks = get_break_periods(settings)
    start_min = time_to_minutes(start_time)
    end_min = time_to_minutes(end_time)
    total = end_min - start_min
    for bs, be in breaks:
        # 휴식 구간과 주어진 범위의 겹침 구간 계산
        overlap_start = max(start_min, bs)
        overlap_end = min(end_min, be)
        if overlap_start < overlap_end:
            total -= (overlap_end - overlap_start)
    return max(0, total)


def generate_time_slots(settings):
    """설정의 근무 시간 범위에서 시간 슬롯 목록을 생성한다.

    work_start부터 work_end 직전까지 grid_interval_minutes 간격으로
    시간 문자열 목록을 만든다.

    Args:
        settings: 설정 딕셔너리. work_start, work_end,
                  grid_interval_minutes(기본 15분) 키 포함.

    Returns:
        list: 시간 슬롯 문자열 목록 (예: ['09:00', '09:15', '09:30', ...]).
    """
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
    """주어진 시간 슬롯이 휴식 시간(점심 또는 추가 휴식)에 해당하는지 확인한다.

    Args:
        time_str: 시간 문자열 ('HH:MM').
        settings: 설정 딕셔너리.

    Returns:
        bool: 휴식 시간이면 True, 아니면 False.
    """
    # 점심 시간 확인
    lunch_start = settings.get('lunch_start', '12:00')
    lunch_end = settings.get('lunch_end', '13:00')
    if lunch_start <= time_str < lunch_end:
        return True
    # 추가 휴식 시간 확인
    for brk in settings.get('breaks', []):
        if brk['start'] <= time_str < brk['end']:
            return True
    return False
