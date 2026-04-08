"""스케줄 블록 겹침(overlap) 감지 및 레이아웃 계산 모듈.

같은 장소에서 시간이 겹치는 블록을 감지하고,
겹치는 블록들의 시각적 배치(열 인덱스, 열 수)를 계산한다.
"""

from app.features.schedule.helpers.time_utils import time_to_minutes
from app.features.schedule.models import schedule_block


def check_overlap(assignee_ids, location_id, date_str, start_time, end_time,
                   exclude_block_id=None, exclude_task_id=None):
    """같은 장소에서 시간이 겹치는 블록이 있는지 확인한다.

    담당자(assignee) 간의 동시간대 배치는 허용하며,
    같은 장소(location)에서의 시간 겹침만 검사한다.

    Args:
        assignee_ids: 담당자 ID 목록 (현재 겹침 검사에서 미사용).
        location_id: 장소 ID. 없으면 겹침 없음으로 처리.
        date_str: 날짜 문자열 ('YYYY-MM-DD').
        start_time: 시작 시간 ('HH:MM').
        end_time: 종료 시간 ('HH:MM').
        exclude_block_id: 겹침 검사에서 제외할 블록 ID (자기 자신 등).
        exclude_task_id: 겹침 검사에서 제외할 태스크 ID (같은 태스크의 분할 블록용).

    Returns:
        dict 또는 None: 겹치는 블록이 있으면 해당 블록 딕셔너리, 없으면 None.
    """
    if not location_id:
        return None
    s1 = time_to_minutes(start_time)
    e1 = time_to_minutes(end_time)
    for b in schedule_block.get_by_date(date_str):
        # 자기 자신 또는 지정된 태스크의 블록은 제외
        if exclude_block_id and b['id'] == exclude_block_id:
            continue
        if exclude_task_id and b.get('task_id') == exclude_task_id:
            continue
        # 다른 장소의 블록은 무시
        if b.get('location_id') != location_id:
            continue
        s2 = time_to_minutes(b['start_time'])
        e2 = time_to_minutes(b['end_time'])
        # 두 시간 구간이 겹치는지 확인 (s1 < e2 && s2 < e1)
        if s1 < e2 and s2 < e1:
            return b
    return None


def compute_overlap_layout(blocks):
    """겹치는 블록들의 시각적 레이아웃(열 배치)을 계산한다.

    시간이 겹치는 블록들을 나란히 표시하기 위해 각 블록에
    col_index(열 위치)와 col_total(총 열 수)을 할당한다.

    알고리즘:
        1. 블록을 시작 시간 오름차순, 종료 시간 내림차순으로 정렬
        2. 그리디 방식으로 각 블록을 빈 열에 배치
        3. 각 블록과 겹치는 블록들의 최대 열 수를 계산하여 col_total 설정

    Args:
        blocks: 스케줄 블록 딕셔너리 목록.

    Returns:
        list: col_index, col_total 필드가 추가된 정렬된 블록 목록.
              빈 목록이 입력되면 그대로 반환.
    """
    if not blocks:
        return blocks

    # 시작 시간 오름차순, 같으면 종료 시간 내림차순(긴 블록 우선)으로 정렬
    sorted_blocks = sorted(
        blocks,
        key=lambda b: (time_to_minutes(b['start_time']),
                       -time_to_minutes(b['end_time'])),
    )

    # 열(column) 배치: 각 열의 (종료시간, 해당 열에 속한 블록 인덱스 목록)
    columns = []
    block_col = {}  # 블록 인덱스 → 열 인덱스 매핑
    for i, b in enumerate(sorted_blocks):
        s = time_to_minutes(b['start_time'])
        placed = False
        for ci, (col_end, indices) in enumerate(columns):
            # 이 열의 마지막 블록이 끝난 이후이면 같은 열에 배치 가능
            if col_end <= s:
                columns[ci] = (time_to_minutes(b['end_time']), indices + [i])
                block_col[i] = ci
                placed = True
                break
        if not placed:
            # 기존 열에 배치 불가 → 새 열 생성
            block_col[i] = len(columns)
            columns.append((time_to_minutes(b['end_time']), [i]))

    # 각 블록의 col_total 계산: 자신과 겹치는 모든 블록의 열 수 중 최대값
    for i, b in enumerate(sorted_blocks):
        s = time_to_minutes(b['start_time'])
        e = time_to_minutes(b['end_time'])
        max_col = block_col[i] + 1
        for j, b2 in enumerate(sorted_blocks):
            if i == j:
                continue
            s2 = time_to_minutes(b2['start_time'])
            e2 = time_to_minutes(b2['end_time'])
            # 시간이 겹치는 블록의 열 인덱스도 고려하여 최대 열 수 산출
            if s < e2 and s2 < e:
                max_col = max(max_col, block_col[j] + 1)
        b['col_index'] = block_col[i]
        b['col_total'] = max_col
    return sorted_blocks
