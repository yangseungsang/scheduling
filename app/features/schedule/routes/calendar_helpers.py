"""
캘린더 헬퍼 모듈.

스케줄 블록과 태스크 간의 데이터 동기화 로직을 담당한다.
식별자 이동 시 다른 블록에서의 제거, 태스크 잔여 시간 재계산,
태스크 상태 자동 갱신 등의 기능을 제공한다.
"""

from app.features.schedule.helpers.time_utils import (
    adjust_end_for_breaks,
    minutes_to_time,
    time_to_minutes,
    work_minutes_in_range,
)
from app.features.schedule.models import schedule_block, settings, task

# 요일 이름 (월요일 시작, 주간/월간 뷰 헤더에 사용)
DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']

# 블록에 허용되는 상태 값 집합
VALID_BLOCK_STATUSES = {'pending', 'in_progress', 'completed', 'cancelled'}


def remove_identifiers_from_other_blocks(task_id, exclude_block_id,
                                         moved_ids, sttngs):
    """이동된 식별자를 동일 태스크의 다른 블록에서 제거한다.

    식별자를 특정 블록에 배치할 때, 같은 태스크의 다른 블록에서
    해당 식별자를 빼야 중복 배치를 방지할 수 있다.
    식별자가 모두 제거된 블록은 삭제되고,
    일부만 제거된 블록은 남은 식별자의 시간에 맞게 종료 시간이 축소된다.

    Args:
        task_id (str): 대상 태스크 ID
        exclude_block_id (str): 식별자를 받은 블록 ID (이 블록은 건너뜀)
        moved_ids (list): 이동된 식별자 ID 리스트
        sttngs (dict): 시스템 설정 (휴식 시간 정보 등)
    """
    t = task.get_by_id(task_id)
    if not t:
        return
    test_list = t.get('identifiers', [])
    # 식별자 ID → 예상 소요 시간(분) 매핑 구성
    id_minutes = {}
    for item in test_list:
        if isinstance(item, dict):
            id_minutes[item['id']] = item.get('estimated_minutes', 0)

    moved_set = set(moved_ids)
    all_blocks = schedule_block.get_all()
    for b in all_blocks:
        # 다른 태스크의 블록은 건너뜀
        if b.get('task_id') != task_id:
            continue
        # 식별자를 받은 블록 자체는 건너뜀
        if b['id'] == exclude_block_id:
            continue
        block_ids = b.get('identifier_ids')
        if not block_ids:
            # identifier_ids가 None이면 전체 태스크 식별자를 커버하는 블록
            all_task_ids = [item['id'] if isinstance(item, dict) else item
                           for item in test_list]
            block_ids = all_task_ids

        # 이 블록에서 이동 대상인 식별자 찾기
        overlap = [i for i in block_ids if i in moved_set]
        if not overlap:
            continue

        remaining_ids = [i for i in block_ids if i not in moved_set]
        if not remaining_ids:
            # 모든 식별자가 이동됨 → 블록 삭제
            schedule_block.delete(b['id'])
        else:
            # 남은 식별자의 총 시간에 맞게 블록 종료 시간 축소 (최소 15분 보장)
            remaining_min = max(sum(id_minutes.get(i, 0) for i in remaining_ids), 15)
            new_end_min = time_to_minutes(b['start_time']) + remaining_min
            new_end = minutes_to_time(new_end_min)
            adjusted_end = adjust_end_for_breaks(b['start_time'], new_end, sttngs)
            schedule_block.update(b['id'],
                                 identifier_ids=remaining_ids,
                                 end_time=adjusted_end)


def sync_task_remaining_minutes(task_id):
    """태스크의 잔여 시간(remaining_minutes)을 블록 배치 현황에 맞게 재계산한다.

    모든 블록의 실 작업 시간 합계를 예상 시간에서 빼서 잔여 시간을 구한다.
    예상 시간은 identifiers 식별자 시간의 합이 우선이며,
    식별자가 없으면 태스크의 estimated_minutes를 사용한다.

    Args:
        task_id (str): 동기화할 태스크 ID (None이면 무시)
    """
    if not task_id:
        return
    t = task.get_by_id(task_id)
    if not t:
        return

    # 예상 시간 = 식별자별 시간 합계 (없으면 태스크 직접 입력값)
    test_list = t.get('identifiers', [])
    tl_sum = sum(
        item.get('estimated_minutes', 0) for item in test_list
        if isinstance(item, dict)
    )
    est = tl_sum if tl_sum > 0 else t.get('estimated_minutes', 0)

    sttngs = settings.get()
    # 해당 태스크의 모든 블록에서 실 작업 시간(휴식 제외) + 초과 시간 합산
    total_min = sum(
        work_minutes_in_range(b['start_time'], b['end_time'], sttngs)
        + b.get('overflow_minutes', 0)
        for b in schedule_block.get_all()
        if b.get('task_id') == task_id
    )
    # 잔여 시간은 0 미만이 될 수 없음
    new_remaining = max(est - total_min, 0)

    # 변경된 값만 패치 (불필요한 쓰기 방지)
    patches = {}
    if t.get('estimated_minutes', 0) != est:
        patches['estimated_minutes'] = est
    if t.get('remaining_minutes', 0) != new_remaining:
        patches['remaining_minutes'] = new_remaining
    if patches:
        task.patch(task_id, **patches)


def sync_task_status(task_id):
    """블록 상태를 기반으로 태스크의 전체 상태를 자동 갱신한다.

    규칙:
    - 모든 블록이 completed → 태스크도 completed
    - 하나라도 in_progress이거나 completed가 섞여 있으면 → in_progress
    - 그 외에는 기존 태스크 상태 유지

    Args:
        task_id (str): 동기화할 태스크 ID
    """
    from app.features.schedule.models import task as task_model
    t = task_model.get_by_id(task_id)
    if not t:
        return
    blocks = [b for b in schedule_block.get_all()
              if b.get('task_id') == task_id]
    if not blocks:
        return
    statuses = [b.get('block_status', 'pending') for b in blocks]
    if all(s == 'completed' for s in statuses):
        new_status = 'completed'
    elif any(s == 'in_progress' for s in statuses):
        new_status = 'in_progress'
    elif any(s == 'completed' for s in statuses):
        # 일부만 완료된 경우도 진행 중으로 처리
        new_status = 'in_progress'
    else:
        new_status = t['status']
    if new_status != t['status']:
        task_model.patch(task_id, status=new_status)
