"""
캘린더 뷰 라우트 모듈.

일간(day), 주간(week), 월간(month) 시간표 뷰를 렌더링하는 라우트와
각 뷰에 대응하는 JSON API 엔드포인트를 제공한다.
"""

import calendar
from datetime import date, timedelta

from flask import Blueprint, current_app, request, jsonify, render_template

from app.features.schedule.services.presentation import (
    build_day_payload,
    build_location_options,
    build_month_nav,
    build_month_weeks,
    build_queue_procedures,
    build_ui_blocks,
    compute_overlap_layout,
    get_break_slots,
    group_blocks_by_date,
    parse_date,
    schedule_settings,
)
from app.features.schedule.services.time import generate_time_slots, is_break_slot
from app.repositories import JsonDomainRepository

# 스케줄 관련 모든 캘린더 뷰가 등록되는 블루프린트
schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')
DAY_NAMES = ['월', '화', '수', '목', '금']


def _prepare_view_context():
    """Load the domain sections required by schedule views."""
    repository = JsonDomainRepository(current_app.config['DOMAIN_DATA_DIR'])
    operations = repository.load_operations()
    procedures = operations.test_procedures
    schedule = operations.schedule
    executions = operations.executions
    sttngs = schedule_settings(repository.load_settings())
    return {
        'procedures': procedures,
        'schedule': schedule,
        'executions': executions,
        'sttngs': sttngs,
        'locations_list': build_location_options(procedures, schedule),
        'time_slots': generate_time_slots(sttngs),
        'break_slots': get_break_slots(sttngs),
        'queue_procedures': build_queue_procedures(procedures, schedule, executions),
    }

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
    enriched = build_ui_blocks(
        ctx['procedures'], ctx['schedule'], ctx['executions'],
        current_date.isoformat(),
        current_date.isoformat(),
        ctx['sttngs'],
    )

    blocks_by_location = {}
    for loc in ctx['locations_list']:
        loc_blocks = [b for b in enriched if b.get('location_name') == loc['id']]
        blocks_by_location[loc['id']] = compute_overlap_layout(loc_blocks)
    no_loc_blocks = [b for b in enriched if not b.get('location_name')]
    if no_loc_blocks:
        blocks_by_location[''] = compute_overlap_layout(no_loc_blocks)

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
        queue_procedures=ctx['queue_procedures'],
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
    # 해당 주의 월요일(시작)과 일요일(끝) 계산
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)
    ctx = _prepare_view_context()
    enriched = build_ui_blocks(
        ctx['procedures'], ctx['schedule'], ctx['executions'],
        week_start.isoformat(),
        week_end.isoformat(),
        ctx['sttngs'],
    )
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
        queue_procedures=ctx['queue_procedures'],
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
    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    # monthrange는 (요일, 마지막 날짜) 튜플을 반환
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    ctx = _prepare_view_context()
    enriched = build_ui_blocks(
        ctx['procedures'], ctx['schedule'], ctx['executions'],
        first_day.isoformat(),
        last_day.isoformat(),
        ctx['sttngs'],
    )
    blocks_by_date = group_blocks_by_date(enriched)
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
        queue_procedures=ctx['queue_procedures'],
    )


@schedule_bp.route('/api/day')
def api_day_data():
    """일간 시간표 데이터를 JSON으로 반환하는 API.

    프론트엔드에서 softReload (AJAX 갱신) 시 호출된다.

    Query Parameters:
        date (str, optional): 조회할 날짜 (YYYY-MM-DD)

    Returns:
        JSON: 블록 목록, 시간 슬롯, 설정, 큐 시험 절차서 등을 포함하는 응답
    """
    current_date = parse_date(request.args.get('date'))
    ctx = _prepare_view_context()
    payload = build_day_payload(
        ctx['procedures'], ctx['schedule'], ctx['executions'],
        current_date.isoformat(),
        ctx['sttngs'],
        ctx['time_slots'],
        [slot for slot in ctx['time_slots'] if is_break_slot(slot, ctx['sttngs'])],
    )
    payload.update({
        'current_date': current_date.isoformat(),
        'prev_date': (current_date - timedelta(days=1)).isoformat(),
        'next_date': (current_date + timedelta(days=1)).isoformat(),
    })
    return jsonify(payload)


@schedule_bp.route('/api/week')
def api_week_data():
    """주간 시간표 데이터를 JSON으로 반환하는 API.

    Query Parameters:
        date (str, optional): 기준 날짜 (YYYY-MM-DD)

    Returns:
        JSON: 날짜별 블록, 주간 날짜 배열, 시간 슬롯, 설정 등
    """
    current_date = parse_date(request.args.get('date'))

    # 해당 주의 월요일~일요일 범위 계산
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)
    ctx = _prepare_view_context()
    enriched = build_ui_blocks(
        ctx['procedures'], ctx['schedule'], ctx['executions'],
        week_start.isoformat(),
        week_end.isoformat(),
        ctx['sttngs'],
    )
    return jsonify({
        'current_date': current_date.isoformat(),
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'week_days': [(week_start + timedelta(days=i)).isoformat() for i in range(5)],
        'day_names': DAY_NAMES,
        'prev_date': (current_date - timedelta(weeks=1)).isoformat(),
        'next_date': (current_date + timedelta(weeks=1)).isoformat(),
        'blocks_by_date': group_blocks_by_date(enriched),
        'time_slots': ctx['time_slots'],
        'break_slots': [s for s in ctx['time_slots'] if is_break_slot(s, ctx['sttngs'])],
        'settings': ctx['sttngs'],
        'today': date.today().isoformat(),
        'queue_procedures': ctx['queue_procedures'],
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
    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    ctx = _prepare_view_context()
    enriched = build_ui_blocks(
        ctx['procedures'], ctx['schedule'], ctx['executions'],
        first_day.isoformat(),
        last_day.isoformat(),
        ctx['sttngs'],
    )
    blocks_by_date = group_blocks_by_date(enriched)
    prev_date, next_date = build_month_nav(year, month)
    weeks = []
    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdayscalendar(year, month):
        week_data = []
        for day_num in week:
            if day_num == 0:
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
        'queue_procedures': ctx['queue_procedures'],
    })
