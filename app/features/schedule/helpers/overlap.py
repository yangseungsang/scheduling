"""스케줄 블록 겹침(overlap) 감지 및 레이아웃 계산 모듈.

같은 장소에서 시간이 겹치는 블록을 감지하고,
겹치는 블록들의 시각적 배치(열 인덱스, 열 수)를 계산한다.

겹침 정책:
    - 장소(location) 기준: 동일 장소에서 같은 시간대에 블록 2개 이상 불가.
    - 담당자(assignee) 기준: 현재는 별도 체크 없음.
      (같은 담당자가 여러 장소에서 동시 진행하는 것을 방지하려면
       assignee 기반 겹침 검사를 추가해야 하지만, 현재 서비스에서는
       장소 충돌 방지만 강제한다.)
    - location_id가 없는 블록은 겹침 검사 대상에서 제외한다.
"""

from app.features.schedule.helpers.time_utils import time_to_minutes
from app.features.schedule.models import schedule_block


def check_overlap(assignee_names, location_id, date_str, start_time, end_time,
                   exclude_block_id=None, exclude_task_id=None):
    """같은 장소에서 시간이 겹치는 블록이 있는지 확인한다.

    장소(location_id)를 기준으로 충돌 여부를 검사한다.
    담당자(assignee_names)는 파라미터로 받지만 현재 충돌 검사에 사용하지 않는다
    (향후 담당자 기반 겹침 검사 추가 시 활용 가능).

    Args:
        assignee_names: 담당자 이름 목록 (현재 겹침 검사에서 미사용, 확장용 예약).
        location_id: 장소 ID. 없으면(빈 문자열/None) 겹침 없음으로 처리.
        date_str: 날짜 문자열 ('YYYY-MM-DD').
        start_time: 시작 시간 ('HH:MM').
        end_time: 종료 시간 ('HH:MM').
        exclude_block_id: 겹침 검사에서 제외할 블록 ID (이동/수정 중인 자기 자신).
        exclude_task_id: 겹침 검사에서 제외할 태스크 ID
                        (같은 태스크의 분할 블록들 간에는 겹침을 허용하지 않지만,
                         큐 복귀 등 특정 상황에서 같은 태스크 블록을 무시할 때 사용).

    Returns:
        dict 또는 None: 겹치는 블록이 있으면 해당 블록 딕셔너리, 없으면 None.
    """
    # location_id가 없는 블록은 장소 미지정으로 간주하여 겹침 검사를 건너뜀
    if not location_id:
        return None
    s1 = time_to_minutes(start_time)
    e1 = time_to_minutes(end_time)
    for b in schedule_block.get_by_date(date_str):
        # 자기 자신 블록은 제외 (이동/리사이즈 시 자기 자신과의 충돌 방지)
        if exclude_block_id and b['id'] == exclude_block_id:
            continue
        # 지정된 태스크의 모든 블록 제외 (같은 태스크 분할 블록 간 제외 시 사용)
        if exclude_task_id and b.get('task_id') == exclude_task_id:
            continue
        # 다른 장소의 블록은 충돌 대상이 아님
        if b.get('location_id') != location_id:
            continue
        s2 = time_to_minutes(b['start_time'])
        e2 = time_to_minutes(b['end_time'])
        # 두 구간이 겹치는 조건: s1 < e2 이면서 s2 < e1
        # (끝 시간이 정확히 같은 경우는 맞닿은 것으로 겹침 아님)
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
