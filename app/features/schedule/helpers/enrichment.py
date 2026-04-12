"""스케줄 블록 보강(enrichment) 및 큐/월간뷰 구성 헬퍼 모듈.

시간표에 표시할 블록 데이터를 태스크·사용자·장소 정보로 보강하고,
미배치 태스크 큐, 월간 달력 구조 등을 생성하는 유틸리티 함수를 제공한다.
"""

import calendar as cal_module
import hashlib
from datetime import date

from app.features.schedule.helpers.time_utils import (
    generate_time_slots,
    is_break_slot,
    work_minutes_in_range,
)
from app.features.schedule.models import (
    location,
    schedule_block,
    settings,
    task,
    user,
)


def _section_color(section_name):
    """장절명(section_name)에서 일관된 HSL 색상을 생성한다.

    같은 장절명은 항상 같은 색상을 반환하므로 시각적 그룹핑에 활용된다.

    Args:
        section_name: 장절명 문자열. None 또는 빈 문자열이면 기본 회색 반환.

    Returns:
        HSL 색상 문자열 (예: 'hsl(120, 55%, 45%)') 또는 기본 회색 '#94a3b8'.
    """
    if not section_name:
        return '#94a3b8'
    # MD5 해시의 앞 8자를 정수로 변환하여 색상 hue 값(0~359)을 결정
    h = int(hashlib.md5(section_name.encode()).hexdigest()[:8], 16)
    hue = h % 360
    return f'hsl({hue}, 55%, 45%)'


def build_maps():
    """사용자·태스크·장소 데이터를 조회 키→객체 딕셔너리로 변환한다.

    시간표 렌더링 시 반복적인 조회를 피하기 위해 미리 맵을 구성한다.
    담당자 참조는 이름 기반이므로 users_map은 이름을 키로 사용한다.

    Returns:
        tuple: (users_map, tasks_map, locations_map)
            - users_map: {user_name: user_dict}
            - tasks_map: {task_id: task_dict}
            - locations_map: {location_id: location_dict}
    """
    users = user.get_all()
    tasks = task.get_all()
    locations = location.get_all()
    return (
        {u['name']: u for u in users},
        {t['id']: t for t in tasks},
        {loc['id']: loc for loc in locations},
    )


def enrich_blocks(blocks, users_map, tasks_map, locations_map, color_by):
    """스케줄 블록 목록에 표시용 부가 정보를 추가한다.

    각 블록에 태스크명, 담당자명, 장소명, 색상, 분할 상태, 예상 시간 등
    UI 렌더링에 필요한 필드를 덧붙인다.

    Args:
        blocks: 원본 스케줄 블록 딕셔너리 목록.
        users_map: {user_id: user_dict} 매핑.
        tasks_map: {task_id: task_dict} 매핑.
        locations_map: {location_id: location_dict} 매핑.
        color_by: 블록 색상 기준. 'location'이면 장소 색상, 그 외에는 담당자 색상.

    Returns:
        list: 보강된 블록 딕셔너리 목록.
    """
    # 전체 블록을 태스크별로 그룹핑 (현재 뷰뿐 아니라 전체 스케줄 대상)
    all_blocks = schedule_block.get_all()
    all_blocks_by_task = {}
    for ab in all_blocks:
        tid = ab.get('task_id')
        if tid:
            all_blocks_by_task.setdefault(tid, []).append(ab)

    enriched = []
    for b in blocks:
        block = dict(b)  # 원본 변경 방지를 위해 복사
        t = tasks_map.get(b.get('task_id'))
        loc = locations_map.get(b.get('location_id'))

        # 담당자(assignee) 이름과 색상 목록 구성 (값 자체가 이름)
        raw_assignee_names = b.get('assignee_names', [])
        assignee_name_list = []
        assignee_colors = []
        for name in raw_assignee_names:
            u = users_map.get(name)
            if u:
                assignee_name_list.append(u['name'])
                assignee_colors.append(u['color'])
            else:
                # users.json에 없는 이름도 그대로 표시 (색상만 기본값)
                assignee_name_list.append(name)
                assignee_colors.append('#6c757d')

        is_simple = b.get('is_simple', False)
        block['doc_id'] = t.get('doc_id', '') if t else ''
        block['doc_name'] = t.get('doc_name', '') if t else ''
        if is_simple:
            # 단순 블록(태스크 없이 직접 생성된 블록)은 블록 자체의 title 사용
            block['task_title'] = b.get('title', '(블록)')
            block['doc_name'] = b.get('title', '')
            block['doc_id'] = ''
        else:
            # 일반 블록: 문서명 우선, 없으면 문서 ID, 태스크 삭제 시 '(삭제됨)'
            block['task_title'] = t.get('doc_name') or str(t.get('doc_id', '(삭제됨)')) if t else '(삭제됨)'
        block['assignee_names'] = assignee_name_list
        block['assignee_name'] = ', '.join(assignee_name_list) if assignee_name_list else '(미배정)'
        # 첫 번째 담당자의 색상을 대표 색상으로 사용
        block['assignee_color'] = assignee_colors[0] if assignee_colors else '#6c757d'
        block['location_name'] = loc['name'] if loc else ''
        block['location_color'] = loc['color'] if loc else '#6c757d'
        # color_by 설정에 따라 블록 표시 색상 결정
        block['color'] = block['location_color'] if color_by == 'location' else block['assignee_color']
        block['block_status'] = b.get('block_status', 'pending')
        block['memo'] = t.get('memo', '') if t else b.get('memo', '')
        block['identifier_ids'] = b.get('identifier_ids')
        block['is_simple'] = b.get('is_simple', False)
        block['title'] = b.get('title', '')
        block['section_color'] = _section_color(block['doc_name'])

        # 식별자(identifier) 수 계산: 전체 vs 이 블록에 할당된 수
        total_ids = len(t.get('identifiers', [])) if t else 0
        block_ids = b.get('identifier_ids')
        block['total_identifier_count'] = total_ids
        block['block_identifier_count'] = len(block_ids) if block_ids else total_ids
        # 블록이 분할(split)되었는지 판단: identifier_ids가 명시적이고 전체보다 적을 때
        block['is_split'] = block_ids is not None and total_ids > 0 and len(block_ids) < total_ids

        # 분할 상태 결정: 나머지 식별자가 다른 블록에 배치되었는지 확인
        if block['is_split'] and t:
            # 태스크의 전체 식별자 ID 집합
            all_task_ids = set(item['id'] if isinstance(item, dict) else item
                              for item in t.get('identifiers', []))
            # 이 태스크의 모든 블록에서 배치된 식별자 ID 수집
            placed_ids = set()
            for tb in all_blocks_by_task.get(b.get('task_id'), []):
                for iid in (tb.get('identifier_ids') or all_task_ids):
                    placed_ids.add(iid)
            unplaced = all_task_ids - placed_ids
            # 미배치 식별자가 있으면 'partial', 모두 배치되면 'split'
            block['split_status'] = 'partial' if unplaced else 'split'
        else:
            block['split_status'] = ''

        # 이 블록의 예상 소요 시간(분) 계산
        if block_ids and t:
            # 분할 블록: 할당된 식별자들의 시간만 합산
            id_set = set(block_ids)
            block['estimated_minutes'] = sum(
                item.get('estimated_minutes', 0)
                for item in t.get('identifiers', [])
                if isinstance(item, dict) and item.get('id') in id_set
            )
        else:
            # 전체 블록: 태스크의 전체 예상 시간 사용
            block['estimated_minutes'] = t.get('estimated_minutes', 0) if t else 0

        enriched.append(block)
    return enriched


def get_queue_tasks(users_map, locations_map, version_id=None):
    """미배치(큐) 태스크 목록을 생성한다.

    완료되지 않았고, 아직 시간표에 전부 배치되지 않은 태스크를 찾아
    UI 표시용 정보를 추가하여 반환한다.

    Args:
        users_map: {user_id: user_dict} 매핑.
        locations_map: {location_id: location_dict} 매핑.
        version_id: 버전 ID로 필터링 (현재 미사용, 향후 확장용).

    Returns:
        list: 큐에 표시할 태스크 딕셔너리 목록 (장절명/절차ID 순 정렬).
    """
    tasks = task.get_all()
    all_blocks = schedule_block.get_all()
    sttngs = settings.get()

    # 태스크별 배치된 블록 목록 구성
    task_blocks = {}  # tid → list of blocks
    for b in all_blocks:
        tid = b.get('task_id')
        if not tid:
            continue
        task_blocks.setdefault(tid, []).append(b)

    queue = []
    for t in tasks:
        # 완료된 태스크는 큐에서 제외
        if t['status'] == 'completed':
            continue
        est = t.get('estimated_minutes', 0)
        # 예상 시간이 0 이하인 태스크는 제외
        if est <= 0:
            continue

        blocks = task_blocks.get(t['id'], [])

        # 분할되지 않은 전체 블록(identifier_ids=None)이 있으면 이미 배치 완료
        has_full_block = any(b.get('identifier_ids') is None for b in blocks)
        if has_full_block:
            continue

        # 분할 블록의 경우: 미배치 식별자 확인
        all_ids = [item['id'] if isinstance(item, dict) else item
                   for item in t.get('identifiers', [])]

        if not all_ids:
            # 식별자가 없는 태스크(예: 단순 블록): 블록이 하나라도 있으면 제외
            if blocks:
                continue
            remaining = est
        else:
            # 이미 배치된 식별자 ID 수집
            scheduled_ids = set()
            for b in blocks:
                bids = b.get('identifier_ids') or []
                for bid in bids:
                    scheduled_ids.add(bid)

            # 미배치 식별자 필터링
            unscheduled_ids = [i for i in all_ids if i not in scheduled_ids]
            if not unscheduled_ids:
                continue

            # 미배치 식별자들의 예상 시간 합산
            remaining = sum(
                item.get('estimated_minutes', 0)
                for item in t.get('identifiers', [])
                if isinstance(item, dict) and item.get('id') in set(unscheduled_ids)
            )

        if remaining <= 0:
            continue

        task_item = dict(t)
        task_item['remaining_unscheduled_minutes'] = remaining
        task_item['section_color'] = _section_color(t.get('doc_name', ''))

        # 담당자 이름/색상 추가 (값 자체가 이름)
        raw_assignee_names = t.get('assignee_names', [])
        resolved_names = []
        resolved_colors = []
        for name in raw_assignee_names:
            u = users_map.get(name)
            if u:
                resolved_names.append(u['name'])
                resolved_colors.append(u['color'])
            else:
                resolved_names.append(name)
                resolved_colors.append('#6c757d')

        task_item['assignee_name'] = ', '.join(resolved_names) if resolved_names else '(미배정)'
        task_item['assignee_color'] = resolved_colors[0] if resolved_colors else '#6c757d'

        # 장소 정보 추가
        loc = locations_map.get(t.get('location_id'))
        task_item['location_name'] = loc['name'] if loc else ''
        task_item['location_color'] = loc['color'] if loc else '#6c757d'

        queue.append(task_item)

    # 문서명 → 문서ID 순으로 정렬
    queue.sort(key=lambda t: t.get('doc_name', '') or str(t.get('doc_id', '')))
    return queue


def get_break_slots(sttngs):
    """설정에 따른 휴식 시간 슬롯 집합을 반환한다.

    Args:
        sttngs: 설정 딕셔너리 (work_start, work_end, lunch_start 등 포함).

    Returns:
        set: 휴식 시간에 해당하는 시간 문자열('HH:MM') 집합.
    """
    slots = generate_time_slots(sttngs)
    return {s for s in slots if is_break_slot(s, sttngs)}


def build_month_nav(year, month):
    """월간뷰에서 이전/다음 월의 첫째 날 date 객체를 반환한다.

    Args:
        year: 현재 연도 (int).
        month: 현재 월 (int, 1~12).

    Returns:
        tuple: (prev_date, next_date) — 이전 월과 다음 월의 1일 date 객체.
    """
    if month == 1:
        prev_date = date(year - 1, 12, 1)
    else:
        prev_date = date(year, month - 1, 1)
    if month == 12:
        next_date = date(year + 1, 1, 1)
    else:
        next_date = date(year, month + 1, 1)
    return prev_date, next_date


def group_blocks_by_date(enriched):
    """보강된 블록 목록을 날짜별로 그룹핑한다.

    Args:
        enriched: enrich_blocks()로 보강된 블록 딕셔너리 목록.

    Returns:
        dict: {날짜문자열('YYYY-MM-DD'): [블록 딕셔너리 목록]}.
    """
    result = {}
    for b in enriched:
        result.setdefault(b['date'], []).append(b)
    return result


def build_month_weeks(year, month, blocks_by_date):
    """월간 달력 데이터 구조를 생성한다.

    Python calendar 모듈을 이용하여 해당 월의 주별 데이터를 구성하고,
    각 날짜에 해당하는 블록 목록을 포함시킨다.

    Args:
        year: 연도 (int).
        month: 월 (int, 1~12).
        blocks_by_date: {날짜문자열: [블록 목록]} 딕셔너리.

    Returns:
        list: 주 단위 리스트. 각 주는 7개 요소(월~일)로 구성.
              해당 월이 아닌 날은 None, 해당 월 날짜는
              {'date': date, 'day': int, 'blocks': list} 형태.
    """
    calendar = cal_module.Calendar(firstweekday=0)  # 월요일 시작
    weeks = []
    for week in calendar.monthdayscalendar(year, month):
        week_data = []
        for day_num in week:
            if day_num == 0:
                # 이전/다음 월에 해당하는 빈 셀
                week_data.append(None)
            else:
                d = date(year, month, day_num)
                week_data.append({
                    'date': d,
                    'day': day_num,
                    'blocks': blocks_by_date.get(d.isoformat(), []),
                })
        weeks.append(week_data)
    return weeks


def parse_date(date_str):
    """날짜 문자열을 date 객체로 파싱한다.

    Args:
        date_str: 'YYYY-MM-DD' 형식의 날짜 문자열. None이거나 파싱 실패 시 오늘 날짜.

    Returns:
        date: 파싱된 날짜 객체 또는 오늘 날짜.
    """
    from datetime import datetime
    if date_str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    return date.today()
