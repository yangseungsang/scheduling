"""
캘린더 뷰 라우트 모듈.

일간(day), 주간(week), 월간(month) 시간표 뷰를 렌더링하는 라우트와
각 뷰에 대응하는 JSON API 엔드포인트를 제공한다.
"""

import calendar
from datetime import date, timedelta

from flask import Blueprint, request, jsonify, render_template

from app.features.schedule.helpers.enrichment import (
    build_maps,
    build_month_nav,
    build_month_weeks,
    enrich_blocks,
    get_break_slots,
    get_queue_tasks,
    group_blocks_by_date,
    parse_date,
)
from app.features.schedule.helpers.overlap import compute_overlap_layout
from app.features.schedule.helpers.time_utils import generate_time_slots, is_break_slot
from app.features.schedule.models import location, schedule_block, settings, version
from app.features.schedule.routes.calendar_helpers import DAY_NAMES

# 스케줄 관련 모든 캘린더 뷰가 등록되는 블루프린트
schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')


def _prepare_view_context():
    """일간/주간/월간 뷰에서 공통으로 필요한 컨텍스트 데이터를 구성한다.

    Returns:
        dict: 다음 키를 포함하는 딕셔너리
            - sttngs: 시스템 설정 (근무 시간, 휴식 시간 등)
            - users_map: 사용자 ID → 사용자 정보 맵
            - tasks_map: 태스크 ID → 태스크 정보 맵
            - locations_map: 장소 ID → 장소 정보 맵
            - locations_list: 전체 장소 목록
            - time_slots: 시간표에 표시할 시간 슬롯 리스트
            - break_slots: 휴식 시간 슬롯 리스트
            - queue_tasks: 미배치 큐에 표시할 태스크 리스트
            - versions: 전체 버전 목록
    """
    sttngs = settings.get()
    users_map, tasks_map, locations_map = build_maps()
    versions = version.get_all()
    return {
        'sttngs': sttngs,
        'users_map': users_map,
        'tasks_map': tasks_map,
        'locations_map': locations_map,
        'locations_list': location.get_all(),
        'time_slots': generate_time_slots(sttngs),
        'break_slots': get_break_slots(sttngs),
        'queue_tasks': get_queue_tasks(users_map, locations_map),
        'versions': versions,
    }


def _enrich(blocks, ctx):
    """블록 리스트에 사용자명, 태스크명, 장소명, 색상 등 표시 정보를 추가한다.

    Args:
        blocks (list): 원본 스케줄 블록 리스트
        ctx (dict): _prepare_view_context()가 반환한 컨텍스트

    Returns:
        list: 표시 정보가 추가된 블록 리스트
    """
    return enrich_blocks(
        blocks,
        ctx['users_map'],
        ctx['tasks_map'],
        ctx['locations_map'],
        ctx['sttngs'].get('block_color_by', 'assignee'),
    )


@schedule_bp.route('/')
def day_view():
    """일간 시간표 뷰를 렌더링한다.

    Query Parameters:
        date (str, optional): 조회할 날짜 (YYYY-MM-DD). 미지정 시 오늘 날짜.

    Returns:
        렌더링된 일간 뷰 HTML
    """
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()

    blocks = schedule_block.get_by_date(current_date.isoformat())
    enriched = _enrich(blocks, ctx)

    # 장소별로 블록을 그룹화하여 컬럼 레이아웃 구성
    blocks_by_location = {}
    for loc in ctx['locations_list']:
        loc_blocks = [b for b in enriched if b.get('location_id') == loc['id']]
        # 같은 장소 내에서 시간이 겹치는 블록의 위치(컬럼)를 계산
        blocks_by_location[loc['id']] = compute_overlap_layout(loc_blocks)
    # 장소가 지정되지 않은 블록 처리
    no_loc_blocks = [b for b in enriched if not b.get('location_id')]
    if no_loc_blocks:
        blocks_by_location[''] = compute_overlap_layout(no_loc_blocks)

    # 일간 뷰는 5분 간격 슬롯 사용
    day_sttngs = dict(ctx['sttngs'])
    day_sttngs['grid_interval_minutes'] = 5
    day_time_slots = generate_time_slots(day_sttngs)

    return render_template(
        'schedule/views/day.html',
        current_date=current_date,
        prev_date=current_date - timedelta(days=1),
        next_date=current_date + timedelta(days=1),
        blocks=enriched,
        blocks_by_location=blocks_by_location,
        locations=ctx['locations_list'],
        time_slots=day_time_slots,
        break_slots=[s for s in day_time_slots if is_break_slot(s, ctx['sttngs'])],
        settings=ctx['sttngs'],
        queue_tasks=ctx['queue_tasks'],
        versions=ctx['versions'],
    )


@schedule_bp.route('/week')
def week_view():
    """주간 시간표 뷰를 렌더링한다.

    Query Parameters:
        date (str, optional): 기준 날짜 (YYYY-MM-DD). 해당 날짜가 속한 주를 표시.

    Returns:
        렌더링된 주간 뷰 HTML
    """
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()

    # 해당 주의 월요일(시작)과 일요일(끝) 계산
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_block.get_by_date_range(
        week_start.isoformat(), week_end.isoformat(),
    )
    enriched = _enrich(blocks, ctx)

    # 날짜별로 블록을 그룹화 (키: ISO 날짜 문자열)
    blocks_by_date = group_blocks_by_date(enriched)

    return render_template(
        'schedule/views/week.html',
        current_date=current_date,
        week_start=week_start,
        week_end=week_end,
        week_days=[week_start + timedelta(days=i) for i in range(5)],
        day_names=DAY_NAMES,
        prev_date=current_date - timedelta(weeks=1),
        next_date=current_date + timedelta(weeks=1),
        blocks_by_date=blocks_by_date,
        time_slots=ctx['time_slots'],
        break_slots=ctx['break_slots'],
        settings=ctx['sttngs'],
        today=date.today(),
        locations=ctx['locations_list'],
        queue_tasks=ctx['queue_tasks'],
        versions=ctx['versions'],
    )


@schedule_bp.route('/month')
def month_view():
    """월간 시간표 뷰를 렌더링한다.

    Query Parameters:
        date (str, optional): 기준 날짜 (YYYY-MM-DD). 해당 월 전체를 표시.

    Returns:
        렌더링된 월간 뷰 HTML
    """
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    # monthrange는 (요일, 마지막 날짜) 튜플을 반환
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_block.get_by_date_range(
        first_day.isoformat(), last_day.isoformat(),
    )
    enriched = _enrich(blocks, ctx)

    blocks_by_date = group_blocks_by_date(enriched)
    # 이전 달, 다음 달 네비게이션 날짜 계산
    prev_date, next_date = build_month_nav(year, month)

    return render_template(
        'schedule/views/month.html',
        current_date=current_date,
        year=year,
        month=month,
        weeks=build_month_weeks(year, month, blocks_by_date),
        day_names=DAY_NAMES,
        prev_date=prev_date,
        next_date=next_date,
        today=date.today(),
        settings=ctx['sttngs'],
        locations=ctx['locations_list'],
        queue_tasks=ctx['queue_tasks'],
        versions=ctx['versions'],
    )


@schedule_bp.route('/api/day')
def api_day_data():
    """일간 시간표 데이터를 JSON으로 반환하는 API.

    프론트엔드에서 softReload (AJAX 갱신) 시 호출된다.

    Query Parameters:
        date (str, optional): 조회할 날짜 (YYYY-MM-DD)

    Returns:
        JSON: 블록 목록, 시간 슬롯, 설정, 큐 태스크 등을 포함하는 응답
    """
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()
    sttngs = ctx['sttngs']

    blocks = schedule_block.get_by_date(current_date.isoformat())
    enriched = _enrich(blocks, ctx)

    time_slots = ctx['time_slots']
    return jsonify({
        'current_date': current_date.isoformat(),
        'prev_date': (current_date - timedelta(days=1)).isoformat(),
        'next_date': (current_date + timedelta(days=1)).isoformat(),
        'blocks': enriched,
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, sttngs)],
        'settings': sttngs,
        'queue_tasks': ctx['queue_tasks'],
    })


@schedule_bp.route('/api/week')
def api_week_data():
    """주간 시간표 데이터를 JSON으로 반환하는 API.

    Query Parameters:
        date (str, optional): 기준 날짜 (YYYY-MM-DD)

    Returns:
        JSON: 날짜별 블록, 주간 날짜 배열, 시간 슬롯, 설정 등
    """
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()
    sttngs = ctx['sttngs']

    # 해당 주의 월요일~일요일 범위 계산
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_block.get_by_date_range(week_start.isoformat(), week_end.isoformat())
    enriched = _enrich(blocks, ctx)

    time_slots = ctx['time_slots']
    return jsonify({
        'current_date': current_date.isoformat(),
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'week_days': [(week_start + timedelta(days=i)).isoformat() for i in range(5)],
        'day_names': DAY_NAMES,
        'prev_date': (current_date - timedelta(weeks=1)).isoformat(),
        'next_date': (current_date + timedelta(weeks=1)).isoformat(),
        'blocks_by_date': group_blocks_by_date(enriched),
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, sttngs)],
        'settings': sttngs,
        'today': date.today().isoformat(),
        'queue_tasks': ctx['queue_tasks'],
    })


@schedule_bp.route('/api/month')
def api_month_data():
    """월간 시간표 데이터를 JSON으로 반환하는 API.

    Query Parameters:
        date (str, optional): 기준 날짜 (YYYY-MM-DD)

    Returns:
        JSON: 주 단위로 구성된 블록 데이터, 네비게이션 날짜, 설정 등
    """
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_block.get_by_date_range(first_day.isoformat(), last_day.isoformat())
    enriched = _enrich(blocks, ctx)

    blocks_by_date = group_blocks_by_date(enriched)
    prev_date, next_date = build_month_nav(year, month)

    # 달력 형태로 주 단위 배열 구성 (월요일 시작)
    weeks = []
    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdayscalendar(year, month):
        week_data = []
        for day_num in week:
            if day_num == 0:
                # 해당 월에 속하지 않는 날(빈 칸)
                week_data.append(None)
            else:
                d = date(year, month, day_num)
                week_data.append({
                    'date': d.isoformat(),
                    'day': day_num,
                    'blocks': blocks_by_date.get(d.isoformat(), []),
                })
        weeks.append(week_data)

    return jsonify({
        'current_date': current_date.isoformat(),
        'year': year,
        'month': month,
        'weeks': weeks,
        'day_names': DAY_NAMES,
        'prev_date': prev_date.isoformat(),
        'next_date': next_date.isoformat(),
        'today': date.today().isoformat(),
        'settings': ctx['sttngs'],
        'queue_tasks': ctx['queue_tasks'],
    })
