"""
캘린더 API 라우트 모듈.

스케줄 블록의 생성, 수정, 삭제, 잠금, 상태 변경, 분리, 일괄 이동 등
블록 관련 REST API 엔드포인트와 내보내기(CSV/XLSX) 기능을 제공한다.
"""

from datetime import date, datetime, timedelta

from flask import request, jsonify, Response

from app.features.schedule.helpers.enrichment import build_maps, enrich_blocks
from app.features.schedule.helpers.overlap import check_overlap
from app.features.schedule.helpers.time_utils import (
    adjust_end_for_breaks,
    minutes_to_time,
    time_to_minutes,
    work_minutes_in_range,
)
from app.features.schedule.models import schedule_block, settings, task
from app.features.schedule.routes.calendar_helpers import (
    VALID_BLOCK_STATUSES,
    remove_identifiers_from_other_blocks,
    sync_task_remaining_minutes,
    sync_task_status,
)
from app.features.schedule.routes.calendar_views import schedule_bp


@schedule_bp.route('/api/blocks', methods=['POST'])
def api_create_block():
    """새로운 스케줄 블록을 생성한다.

    일반 블록(태스크 연결)과 간단 블록(제목만 있는 비시험 블록)을 모두 처리한다.

    Request Body (JSON):
        - is_simple (bool, optional): True이면 간단 블록으로 생성
        - task_id (str): 연결할 태스크 ID (일반 블록 필수)
        - date (str): 배치 날짜 (YYYY-MM-DD, 필수)
        - start_time (str): 시작 시간 (HH:MM, 필수)
        - end_time (str): 종료 시간 (HH:MM, 필수)
        - assignee_names (list, optional): 담당자 ID 리스트
        - location_id (str, optional): 시험 장소 ID
        - identifier_ids (list, optional): 배치할 식별자 ID 리스트
        - overflow_minutes (int, optional): 초과 배치 시간(분)
        - is_locked (bool, optional): 잠금 여부
        - title (str, optional): 간단 블록 제목

    Returns:
        JSON: 생성된 블록 데이터 (201) 또는 에러 (400/409)
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    is_simple = data.get('is_simple', False)

    # 간단 블록: task_id 없이 제목, 날짜, 시간만으로 생성
    if is_simple:
        for field in ('date', 'start_time', 'end_time'):
            if not data.get(field):
                return jsonify({'error': f'{field}은(는) 필수 항목입니다.'}), 400
        block = schedule_block.create(
            task_id=None,
            assignee_names=[],
            location_id=data.get('location_id', ''),
            date=data['date'],
            start_time=data['start_time'],
            end_time=data['end_time'],
            title=data.get('title', ''),
            is_simple=True,
        )
        return jsonify(block), 201

    # 일반 블록: task_id가 필수
    for field in ('task_id', 'date', 'start_time', 'end_time'):
        if not data.get(field):
            return jsonify({'error': f'{field}은(는) 필수 항목입니다.'}), 400

    t = task.get_by_id(data['task_id'])
    assignee_names = data.get('assignee_names', [])
    location_id = data.get('location_id', '')

    # 담당자/장소가 미지정이면 태스크의 기본값 사용
    if not assignee_names and t:
        assignee_names = t.get('assignee_names', [])
    if not location_id and t:
        location_id = t.get('location_id', '')

    sttngs = settings.get()
    # 휴식 시간을 건너뛰도록 종료 시간 보정
    adjusted_end = adjust_end_for_breaks(data['start_time'], data['end_time'], sttngs)

    # 담당자 및 장소 기준 시간 겹침 검사
    overlap = check_overlap(assignee_names, location_id, data['date'], data['start_time'], adjusted_end)
    if overlap:
        return jsonify({'error': '해당 시간에 이미 다른 시험이 배치되어 있습니다.'}), 409

    new_identifier_ids = data.get('identifier_ids')

    # 초과 배치 시간(분) 계산: actual_work_end 기준, 순수 작업 시간으로 산출
    work_end_str = sttngs.get('actual_work_end') or sttngs.get('work_end', '17:00')
    work_end_min = time_to_minutes(work_end_str)
    adjusted_end_min = time_to_minutes(adjusted_end)
    if adjusted_end_min > work_end_min:
        # 초과분의 순수 작업 시간만 계산 (휴식 제외)
        overflow_minutes = work_minutes_in_range(
            work_end_str, adjusted_end, sttngs)
        adjusted_end = work_end_str
    else:
        overflow_minutes = 0

    block = schedule_block.create(
        task_id=data['task_id'],
        assignee_names=assignee_names,
        location_id=location_id,
        date=data['date'],
        start_time=data['start_time'],
        end_time=adjusted_end,
        is_locked=data.get('is_locked', False),
        identifier_ids=new_identifier_ids,
        overflow_minutes=overflow_minutes,
    )

    # 특정 식별자만 선택하여 배치한 경우, 다른 블록에서 해당 식별자를 제거
    if new_identifier_ids and data['task_id']:
        remove_identifiers_from_other_blocks(
            data['task_id'], block['id'], new_identifier_ids, sttngs,
        )

    # 초과 시간이 있으면 다음 근무일에 연속 블록 자동 생성 (연쇄 넘김)
    continuations = []
    remaining_overflow = overflow_minutes
    failed_msg = None
    if remaining_overflow > 0 and data['task_id']:
        from datetime import date as date_cls, timedelta
        work_start = sttngs.get('actual_work_start') or sttngs.get('work_start', '08:30')
        work_start_min = time_to_minutes(work_start)
        day_work_min = work_minutes_in_range(work_start, work_end_str, sttngs)
        current_date = date_cls.fromisoformat(data['date'])

        while remaining_overflow > 0:
            # 다음 근무일 계산
            current_date += timedelta(days=1)
            while current_date.weekday() >= 5:
                current_date += timedelta(days=1)
            next_date = current_date.isoformat()

            # 이번 날에 배치할 시간 결정
            place_min = min(remaining_overflow, day_work_min)
            cont_start = work_start
            cont_raw_end = minutes_to_time(work_start_min + place_min)
            cont_end = adjust_end_for_breaks(cont_start, cont_raw_end, sttngs)

            # 겹침 검사
            cont_overlap = check_overlap(
                assignee_names, location_id, next_date, cont_start, cont_end,
            )
            if cont_overlap:
                failed_msg = (
                    next_date + ' ' + cont_start + '~' + cont_end +
                    ' 시간대에 다른 시험이 있어 배치하지 못했습니다. '
                    '초과분(' + str(remaining_overflow) + '분)은 줄어듭니다.'
                )
                break

            cont_block = schedule_block.create(
                task_id=data['task_id'],
                assignee_names=assignee_names,
                location_id=location_id,
                date=next_date,
                start_time=cont_start,
                end_time=cont_end,
                identifier_ids=new_identifier_ids,
            )
            continuations.append(cont_block)
            remaining_overflow -= place_min

    # continuation 전부 실패 시 overflow_minutes를 0으로 리셋
    if overflow_minutes > 0 and not continuations:
        schedule_block.update(block['id'], overflow_minutes=0)
        block['overflow_minutes'] = 0

    # 태스크의 잔여 시간을 블록 배치 현황에 맞게 동기화
    sync_task_remaining_minutes(data['task_id'])

    result = dict(block)
    if continuations:
        result['continuation'] = continuations[-1]  # 마지막 블록 (프론트 호환)
        result['continuations'] = continuations
    if failed_msg:
        result['continuation_failed'] = failed_msg
    return jsonify(result), 201


@schedule_bp.route('/api/blocks/<block_id>', methods=['PUT'])
def api_update_block(block_id):
    """기존 스케줄 블록을 수정한다.

    이동(드래그), 리사이즈, 상세 팝업 수정 등에서 호출된다.

    Args:
        block_id (str): 수정할 블록 ID

    Request Body (JSON):
        - date (str, optional): 변경할 날짜
        - start_time (str, optional): 변경할 시작 시간
        - end_time (str, optional): 변경할 종료 시간
        - is_locked (bool, optional): 잠금 상태
        - block_status (str, optional): 블록 상태
        - location_id (str, optional): 장소 ID
        - resize (bool, optional): 리사이즈 작업 여부
        - duration_minutes (int, optional): 상세 팝업에서 지정한 소요 시간(분)

    Returns:
        JSON: 수정된 블록 데이터 또는 에러 (404/409)
    """
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    # 수정 가능한 필드만 필터링
    allowed = {'date', 'start_time', 'end_time', 'is_locked', 'block_status', 'location_id'}
    updates = {k: v for k, v in data.items() if k in allowed}
    is_resize = data.get('resize', False)
    duration_minutes = data.get('duration_minutes')

    # 상세 팝업에서 소요 시간(분)을 직접 지정한 경우 종료 시간 재계산
    if duration_minutes is not None:
        sttngs = settings.get()
        start = block['start_time']
        raw_end = minutes_to_time(time_to_minutes(start) + int(duration_minutes))
        updates['end_time'] = adjust_end_for_breaks(start, raw_end, sttngs)

    # 이동(드래그)인 경우: 원래 작업 시간(분)을 유지하면서 새 시작 시간에 맞게 종료 시간 재계산
    if 'start_time' in updates and 'end_time' in updates and not is_resize:
        sttngs = settings.get()
        # 원래 블록의 실 작업 시간(휴식 제외)을 계산
        work_mins = work_minutes_in_range(block['start_time'], block['end_time'], sttngs)
        raw_end = minutes_to_time(time_to_minutes(updates['start_time']) + work_mins)
        updates['end_time'] = adjust_end_for_breaks(updates['start_time'], raw_end, sttngs)

    # 겹침 검사용 데이터 준비 (변경된 값 우선, 없으면 기존 블록 값)
    check_date = updates.get('date', block['date'])
    check_start = updates.get('start_time', block['start_time'])
    check_end = updates.get('end_time', block['end_time'])
    assignee_names = block.get('assignee_names', [])
    location_id = updates.get('location_id', block.get('location_id', ''))

    # 자기 자신은 제외하고 겹침 검사
    overlap = check_overlap(
        assignee_names, location_id, check_date, check_start, check_end,
        exclude_block_id=block_id,
    )
    if overlap:
        return jsonify({'error': '해당 시간에 이미 다른 시험이 배치되어 있습니다.'}), 409

    # 근무 종료 시간 초과 시 클램핑 + 다음날 자동 넘김
    sttngs = sttngs if 'sttngs' in dir() else settings.get()
    work_end_str = sttngs.get('actual_work_end') or sttngs.get('work_end', '17:00')
    work_end_min = time_to_minutes(work_end_str)
    check_end_min = time_to_minutes(check_end)
    continuations = []
    failed_msg = None
    if check_end_min > work_end_min:
        overflow_minutes = work_minutes_in_range(work_end_str, check_end, sttngs)
        updates['end_time'] = work_end_str
        check_end = work_end_str

        if overflow_minutes > 0 and block.get('task_id'):
            from datetime import date as date_cls, timedelta
            work_start = sttngs.get('actual_work_start') or sttngs.get('work_start', '08:30')
            work_start_min = time_to_minutes(work_start)
            day_work_min = work_minutes_in_range(work_start, work_end_str, sttngs)
            current_date = date_cls.fromisoformat(updates.get('date', block['date']))
            remaining_overflow = overflow_minutes

            while remaining_overflow > 0:
                current_date += timedelta(days=1)
                while current_date.weekday() >= 5:
                    current_date += timedelta(days=1)
                next_date = current_date.isoformat()

                place_min = min(remaining_overflow, day_work_min)
                cont_start = work_start
                cont_raw_end = minutes_to_time(work_start_min + place_min)
                cont_end = adjust_end_for_breaks(cont_start, cont_raw_end, sttngs)

                cont_overlap = check_overlap(
                    assignee_names, location_id, next_date, cont_start, cont_end,
                )
                if cont_overlap:
                    failed_msg = (
                        next_date + ' ' + cont_start + '~' + cont_end +
                        ' 시간대에 다른 시험이 있어 배치하지 못했습니다. '
                        '초과분(' + str(remaining_overflow) + '분)은 줄어듭니다.'
                    )
                    break

                cont_block = schedule_block.create(
                    task_id=block.get('task_id'),
                    assignee_names=block.get('assignee_names', []),
                    location_id=location_id,
                    date=next_date,
                    start_time=cont_start,
                    end_time=cont_end,
                    identifier_ids=block.get('identifier_ids'),
                )
                continuations.append(cont_block)
                remaining_overflow -= place_min

    # continuation 전부 실패 시 overflow_minutes를 0으로
    if 'overflow_minutes' in dir() and overflow_minutes > 0 and not continuations:
        updates['overflow_minutes'] = 0

    updated = schedule_block.update(block_id, **updates)

    if block.get('task_id'):
        sync_task_remaining_minutes(block['task_id'])

    result = dict(updated)
    if continuations:
        result['continuation'] = continuations[-1]
        result['continuations'] = continuations
    if failed_msg:
        result['continuation_failed'] = failed_msg
    return jsonify(result)


@schedule_bp.route('/api/blocks/<block_id>', methods=['DELETE'])
def api_delete_block(block_id):
    """스케줄 블록을 삭제한다.

    Args:
        block_id (str): 삭제할 블록 ID

    Query Parameters:
        restore (str, optional): '1'이면 태스크의 장소 정보도 초기화 (큐로 복원)

    Returns:
        JSON: 성공 여부 또는 에러 (404)
    """
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    task_id = block.get('task_id')
    # restore=1이면 큐로 복원하는 동작 (장소 초기화)
    is_restore = request.args.get('restore') == '1'
    schedule_block.delete(block_id)
    if task_id:
        sync_task_remaining_minutes(task_id)
        if is_restore:
            # 큐로 복원 시 태스크의 장소 정보를 비움
            task.patch(task_id, location_id='')
    return jsonify({'success': True})


@schedule_bp.route('/api/blocks/<block_id>/lock', methods=['PUT'])
def api_toggle_lock(block_id):
    """블록의 잠금 상태를 토글한다.

    잠금된 블록은 드래그 이동/리사이즈/일괄 이동에서 제외된다.

    Args:
        block_id (str): 대상 블록 ID

    Returns:
        JSON: 수정된 블록 데이터 또는 에러 (404)
    """
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    updated = schedule_block.update(block_id, is_locked=not block.get('is_locked', False))
    return jsonify(updated)


@schedule_bp.route('/api/blocks/<block_id>/status', methods=['PUT'])
def api_update_block_status(block_id):
    """블록의 진행 상태를 변경한다.

    블록 상태 변경 시 해당 태스크의 전체 상태도 자동 동기화된다.

    Args:
        block_id (str): 대상 블록 ID

    Request Body (JSON):
        - block_status (str): 변경할 상태 (pending/in_progress/completed/cancelled)

    Returns:
        JSON: 수정된 블록 데이터 또는 에러 (400/404)
    """
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if not data or 'block_status' not in data:
        return jsonify({'error': '상태 값이 필요합니다.'}), 400
    status = data['block_status']
    if status not in VALID_BLOCK_STATUSES:
        return jsonify({'error': '유효하지 않은 상태입니다.'}), 400
    updated = schedule_block.update(block_id, block_status=status)

    # 블록 상태 변경에 따라 태스크 전체 상태를 자동 갱신
    task_id = block.get('task_id')
    if task_id:
        sync_task_status(task_id)

    return jsonify(updated)


@schedule_bp.route('/api/simple-blocks', methods=['POST'])
def api_create_simple_block():
    """간단 블록용 태스크를 생성한다.

    시험이 아닌 일반 작업(회의, 점검 등)을 큐에 추가할 때 사용한다.
    내부적으로 'BLK-' 접두사가 붙은 절차서 ID로 태스크를 생성하고
    is_simple=True로 마킹한다.

    Request Body (JSON):
        - title (str): 블록 제목 (필수)
        - estimated_minutes (int, optional): 예상 소요 시간(분, 기본 60)

    Returns:
        JSON: 생성된 태스크 데이터 (201) 또는 에러 (400)
    """
    data = request.get_json()
    if not data or not data.get('title', '').strip():
        return jsonify({'error': '제목을 입력해주세요.'}), 400
    title = data['title'].strip()
    minutes = int(data.get('estimated_minutes', 60))
    # 고유한 문서 ID 생성 (타임스탬프 뒤 6자리를 정수로)
    t = task.create(
        doc_id=int(str(int(__import__('time').time()))[-6:]),
        version_id='',
        assignee_names=[],
        location_id='',
        doc_name=title,
        identifiers=[],
        estimated_minutes=minutes,
        memo='',
    )
    # 간단 블록으로 표시
    task.patch(t['id'], is_simple=True)
    return jsonify(t), 201


@schedule_bp.route('/api/blocks/<block_id>/memo', methods=['PUT'])
def api_update_block_memo(block_id):
    """블록의 메모를 수정한다.

    블록 메모 변경 시 연결된 태스크의 메모도 함께 갱신된다.

    Args:
        block_id (str): 대상 블록 ID

    Request Body (JSON):
        - memo (str): 메모 내용

    Returns:
        JSON: 수정된 블록 데이터 또는 에러 (400/404)
    """
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if data is None:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    memo = data.get('memo', '')
    updated = schedule_block.update(block_id, memo=memo)
    # 블록 메모를 태스크에도 동기화
    if block.get('task_id'):
        task.patch(block['task_id'], memo=memo)
    return jsonify(updated)


@schedule_bp.route('/api/export')
def api_export():
    """스케줄 데이터를 CSV 또는 XLSX 형식으로 내보낸다.

    Query Parameters:
        start_date (str): 시작 날짜 (YYYY-MM-DD, 필수)
        end_date (str): 종료 날짜 (YYYY-MM-DD, 필수)
        format (str, optional): 내보내기 형식 ('csv' 또는 'xlsx', 기본 'csv')

    Returns:
        Response: CSV/XLSX 파일 다운로드 응답 또는 에러 (400)
    """
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    fmt = request.args.get('format', 'csv')

    if not start_date or not end_date:
        return jsonify({'error': 'start_date와 end_date는 필수입니다.'}), 400

    # 날짜 형식 유효성 검사
    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': '날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)'}), 400

    from app.features.schedule.models import version as version_model
    users_map, tasks_map, locations_map = build_maps()
    sttngs = settings.get()
    blocks = schedule_block.get_by_date_range(start_date, end_date)
    enriched = enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        sttngs.get('block_color_by', 'assignee'),
    )
    # 날짜 → 시작 시간 순으로 정렬
    enriched.sort(key=lambda b: (b.get('date', ''), b.get('start_time', '')))

    # 버전 정보
    versions = version_model.get_all()
    version_name = versions[0]['name'] if versions else ''

    from app.features.schedule.services.export import export_xlsx, export_csv

    safe_ver = version_name.replace('/', '_').replace('\\', '_') if version_name else ''
    filename_base = f'schedule_{safe_ver}_{start_date}_{end_date}' if safe_ver else f'schedule_{start_date}_{end_date}'

    if fmt == 'xlsx':
        try:
            data = export_xlsx(enriched, start_date, end_date, version_name=version_name)
            return Response(
                data,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': f'attachment; filename="{filename_base}.xlsx"'},
            )
        except ImportError:
            fmt = 'csv'

    return Response(
        export_csv(enriched),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename_base}.csv"'},
    )


@schedule_bp.route('/api/blocks/by-task/<task_id>')
def api_blocks_by_task(task_id):
    """특정 태스크에 연결된 모든 블록을 조회한다.

    분할 블록의 식별자 배분 현황을 확인할 때 사용된다.

    Args:
        task_id (str): 조회할 태스크 ID

    Returns:
        JSON: 해당 태스크의 블록 리스트 (identifier_ids 포함)
    """
    blocks = [b for b in schedule_block.get_all() if b.get('task_id') == task_id]
    return jsonify({'blocks': blocks})


@schedule_bp.route('/api/blocks/shift', methods=['POST'])
def api_shift_blocks():
    """지정 날짜 이후의 모든 블록을 +1일 또는 -1일 이동한다.

    주말(토/일)은 자동으로 건너뛴다.
    잠금된 블록(is_locked=True)은 이동에서 제외된다.

    Request Body (JSON):
        - from_date (str): 기준 날짜 (이 날짜 이후 블록만 이동, 필수)
        - direction (int, optional): 이동 방향 (1=미래, -1=과거, 기본 1)

    Returns:
        JSON: 성공 여부 및 이동된 블록 수
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    from_date = data.get('from_date', '')
    direction = data.get('direction', 1)

    if not from_date:
        return jsonify({'error': 'from_date는 필수입니다.'}), 400

    all_blocks = schedule_block.get_all()
    shifted = 0
    for b in all_blocks:
        # 기준 날짜 이전 블록은 건너뜀
        if b['date'] < from_date:
            continue
        # 잠금 블록은 건너뜀
        if b.get('is_locked'):
            continue

        d = date.fromisoformat(b['date'])
        d += timedelta(days=direction)
        # 주말을 건너뛰어 평일로 이동
        if direction > 0:
            while d.weekday() >= 5:  # 5=토요일, 6=일요일
                d += timedelta(days=1)
        else:
            while d.weekday() >= 5:
                d -= timedelta(days=1)

        schedule_block.update(b['id'], date=d.isoformat())
        shifted += 1

    return jsonify({'success': True, 'shifted_count': shifted})


@schedule_bp.route('/api/blocks/<block_id>/split', methods=['POST'])
def api_split_block(block_id):
    """블록을 식별자 기준으로 두 개로 분리한다.

    선택한 식별자는 원래 블록에 유지되고,
    나머지 식별자는 원래 블록 바로 뒤에 새 블록으로 생성된다.

    Args:
        block_id (str): 분리할 블록 ID

    Request Body (JSON):
        - keep_identifier_ids (list): 원래 블록에 유지할 식별자 ID 리스트

    Returns:
        JSON: 성공 여부 및 새로 생성된 블록 데이터 또는 에러 (400/404/409)
    """
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404

    data = request.get_json()
    keep_ids = data.get('keep_identifier_ids', [])
    if not keep_ids:
        return jsonify({'error': '유지할 식별자를 선택해주세요.'}), 400

    task_id = block.get('task_id')
    if not task_id:
        return jsonify({'error': '간단 블록은 분리할 수 없습니다.'}), 400

    t = task.get_by_id(task_id)
    if not t:
        return jsonify({'error': '연결된 시험 항목을 찾을 수 없습니다.'}), 404

    sttngs = settings.get()
    test_list = t.get('identifiers', [])
    keep_set = set(keep_ids)

    # 이 블록이 실제로 커버하는 식별자 목록을 결정
    block_ids = block.get('identifier_ids')
    if block_ids is None:
        # identifier_ids가 None이면 전체 태스크의 식별자를 커버하는 블록
        # 다른 분할 블록에 이미 할당된 식별자는 제외
        other_ids = set()
        for b in schedule_block.get_all():
            if b['id'] == block_id or b.get('task_id') != task_id:
                continue
            if b.get('identifier_ids'):
                other_ids.update(b['identifier_ids'])
        block_ids = [item['id'] for item in test_list
                     if isinstance(item, dict) and item['id'] not in other_ids]

    # 분리할 식별자 = 현재 블록 식별자 - 유지할 식별자
    split_ids = [iid for iid in block_ids if iid not in keep_set]

    # 유지/분리 각각의 예상 소요 시간 계산
    keep_minutes = sum(
        item.get('estimated_minutes', 0)
        for item in test_list
        if isinstance(item, dict) and item.get('id') in keep_set
    )
    split_minutes = sum(
        item.get('estimated_minutes', 0)
        for item in test_list
        if isinstance(item, dict) and item.get('id') in set(split_ids)
    )

    # 원래 블록 수정: 유지할 식별자만 남기고 시간 축소
    keep_min = max(keep_minutes, 1)  # 최소 1분 보장
    new_end_min = time_to_minutes(block['start_time']) + keep_min
    new_end = minutes_to_time(new_end_min)
    adjusted_end = adjust_end_for_breaks(block['start_time'], new_end, sttngs)
    schedule_block.update(block_id, identifier_ids=keep_ids, end_time=adjusted_end)

    # 새 블록 생성: 분리된 식별자, 원래 블록 바로 뒤에 배치
    split_min = max(split_minutes, 1)
    split_start = adjusted_end  # 원래 블록 종료 시간이 새 블록 시작 시간
    split_end_min = time_to_minutes(split_start) + split_min
    split_end = minutes_to_time(split_end_min)
    split_adjusted_end = adjust_end_for_breaks(split_start, split_end, sttngs)

    # 새 블록의 시간 겹침 검사
    overlap = check_overlap(
        block.get('assignee_names', []),
        block.get('location_id', ''),
        block['date'],
        split_start,
        split_adjusted_end,
        exclude_block_id=block_id,
    )
    if overlap:
        # 겹침 발생 시 원래 블록을 원상복구
        schedule_block.update(block_id, identifier_ids=block.get('identifier_ids'),
                              end_time=block['end_time'])
        return jsonify({
            'error': '분리된 블록이 다른 블록과 시간이 겹칩니다.',
            'overlap_block': overlap.get('id'),
        }), 409

    new_block = schedule_block.create(
        task_id=task_id,
        assignee_names=block.get('assignee_names', []),
        location_id=block.get('location_id', ''),
        date=block['date'],
        start_time=split_start,
        end_time=split_adjusted_end,
        block_status=block.get('block_status', 'pending'),
        identifier_ids=split_ids,
    )

    # 분리 후 태스크 잔여 시간 동기화
    sync_task_remaining_minutes(task_id)
    return jsonify({'success': True, 'new_block': new_block})


@schedule_bp.route('/api/blocks/<block_id>/return-identifiers', methods=['POST'])
def api_return_identifiers_to_queue(block_id):
    """블록에서 선택한 식별자를 큐로 되돌린다.

    유지할 식별자만 블록에 남기고, 나머지는 미배치 상태로 전환한다.
    유지 식별자가 없으면 블록 자체를 삭제한다.

    Args:
        block_id (str): 대상 블록 ID

    Request Body (JSON):
        - keep_identifier_ids (list): 블록에 남길 식별자 ID 목록

    Returns:
        JSON: 성공 여부
    """
    block = schedule_block.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    keep_ids = data.get('keep_identifier_ids', [])
    task_id = block.get('task_id')

    if not keep_ids:
        # 모든 식별자를 큐로 → 블록 삭제
        schedule_block.delete(block_id)
    else:
        # 유지 식별자로 블록 축소
        t = task.get_by_id(task_id) if task_id else None
        if t:
            keep_set = set(keep_ids)
            keep_minutes = sum(
                item.get('estimated_minutes', 0)
                for item in t.get('identifiers', [])
                if isinstance(item, dict) and item.get('id') in keep_set
            )
            sttngs = settings.get()
            keep_min = max(keep_minutes, 1)
            new_end_min = time_to_minutes(block['start_time']) + keep_min
            new_end = minutes_to_time(new_end_min)
            adjusted_end = adjust_end_for_breaks(block['start_time'], new_end, sttngs)
            schedule_block.update(block_id, identifier_ids=keep_ids, end_time=adjusted_end)
        else:
            schedule_block.update(block_id, identifier_ids=keep_ids)

    # 태스크 잔여 시간 동기화
    if task_id:
        sync_task_remaining_minutes(task_id)

    return jsonify({'success': True})
