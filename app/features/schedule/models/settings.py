"""
설정 관리 모듈.

시간표 표시 및 근무 시간 관련 전역 설정을 관리한다.
설정은 JSON 파일(settings.json)에 단일 객체로 저장되며,
다른 모델과 달리 BaseRepository를 상속하지 않고 독립적으로 동작한다.
"""

from app.features.schedule.store import read_json, write_json

# 설정 파일명
FILENAME = 'settings.json'

# 기본 설정값 (settings.json이 없거나 비어 있을 때 사용)
DEFAULTS = {
    'work_start': '08:00',           # 시간표 표시 시작 시간
    'work_end': '17:00',             # 시간표 표시 종료 시간
    'actual_work_start': '08:30',    # 실제 업무 시작 시간
    'actual_work_end': '16:30',      # 실제 업무 종료 시간
    'lunch_start': '12:00',          # 점심 시간 시작
    'lunch_end': '13:00',            # 점심 시간 종료
    'breaks': [                      # 정규 휴식 시간 목록
        {'start': '09:45', 'end': '10:00'},
        {'start': '14:45', 'end': '15:00'},
    ],
    'grid_interval_minutes': 15,     # 시간표 격자 간격(분)
    'max_schedule_days': 14,         # 시간표에 표시할 최대 일수
    'block_color_by': 'assignee',    # 블록 색상 기준 ('assignee' 또는 'location')
}


def get():
    """현재 설정을 조회한다.

    settings.json 파일이 없거나 비어 있으면
    기본 설정(DEFAULTS)을 파일에 저장한 뒤 반환한다.

    Returns:
        dict: 설정 데이터
    """
    settings = read_json(FILENAME)
    if not settings:
        # 설정 파일이 없으면 기본값으로 초기화
        settings = DEFAULTS.copy()
        write_json(FILENAME, settings)
    return settings


def update(data):
    """설정을 부분 업데이트한다.

    기존 설정에 전달된 data를 병합(덮어쓰기)하여 저장한다.

    Args:
        data: 업데이트할 설정 키-값 쌍 (dict)

    Returns:
        dict: 업데이트된 전체 설정
    """
    settings = get()
    # 기존 설정에 새 값을 병합 (전달된 키만 덮어씀)
    settings.update(data)
    write_json(FILENAME, settings)
    return settings
