"""
시험 항목(시험 절차서) 관리 라우트 모듈.

시험 절차서의 CRUD(생성, 조회, 수정, 삭제)를 처리하는 웹 페이지 라우트와
REST API 엔드포인트를 제공한다. 시험 절차서는 문서 ID, 담당자,
시험 장소, 시험 항목 목록(test_items) 등을 포함한다.
"""

import json

from flask import Blueprint, current_app, request, jsonify, render_template, redirect, url_for, flash, abort

from app.features.schedule.services import test_procedures as procedure, blocks as schedule_block
from app.features.execution.repository import ExecutionRepository
from app.features.schedule.services.test_procedures import (
    TestProcedureService,
    TestProcedureError,
)

# 시험 절차서 관련 라우트가 등록되는 블루프린트
procedures_bp = Blueprint('procedures', __name__, url_prefix='/procedures')


def _procedure_service():
    return TestProcedureService(current_app.config['DOMAIN_DATA_DIR'])


def _location_options():
    names = sorted(
        {item.get('location_name', '') for item in procedure.get_all()}
        | {item.get('location_name', '') for item in schedule_block.get_all()}
    )
    return [{'id': name, 'name': name} for name in names if name]


def _procedure_error_response(exc):
    return jsonify({'error': str(exc)}), exc.status_code


def _procedure_payload_from_form(existing=None):
    test_items = _parse_test_items_from_form()
    estimated_minutes = (
        _compute_estimated_minutes(test_items)
        if test_items
        else int(request.form.get('estimated_minutes', 0) or 0)
    )
    payload = {
        'document_id': _parse_document_id(request.form.get('document_id')),
        'assignee_names': _parse_assignee_names(request.form.getlist('assignee_names')),
        'location_name': request.form.get('location_name', ''),
        'document_name': request.form.get('document_name', '').strip(),
        'test_items': test_items,
        'estimated_minutes': estimated_minutes,
        'memo': request.form.get('memo', '').strip(),
    }
    if existing and existing.get('test_round') is not None:
        payload['test_round'] = existing.get('test_round')
    return payload


def _parse_test_items_from_form():
    """폼의 숨겨진 JSON 필드에서 test_items(시험 항목 목록)를 파싱한다.

    폼 제출 시 JavaScript가 시험 항목 목록을 JSON 문자열로 직렬화하여
    'test_items_json' 필드에 담아 전송한다. (호환을 위해 test_list_json도 허용)

    Returns:
        list: 파싱된 시험 항목 목록 (각 항목은 dict). 파싱 실패 시 빈 리스트.
    """
    raw = (request.form.get('test_items_json') or
           request.form.get('test_list_json') or '').strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return []


def _parse_assignee_names(values):
    return list(dict.fromkeys(
        name.strip()
        for value in values or []
        for name in value.split(',')
        if name.strip()
    ))


def _compute_estimated_minutes(test_items):
    """시험 항목 목록의 예상 소요 시간 합계를 계산한다.

    Args:
        test_items (list): 시험 항목 목록 (각 항목에 'estimated_minutes' 포함)

    Returns:
        int: 전체 예상 소요 시간(분)
    """
    return sum(item.get('estimated_minutes', 0) for item in test_items if isinstance(item, dict))


def _parse_document_id(raw):
    """폼/요청에서 들어온 document_id 문자열을 정수로 변환한다.

    Returns:
        int 또는 None: 변환 성공 시 int, 실패 시 None.
    """
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 템플릿 렌더링 라우트 (웹 페이지)
# ---------------------------------------------------------------------------

@procedures_bp.route('/')
def procedure_list():
    """시험 절차서 목록 페이지를 렌더링한다.

    다양한 필터 조건을 지원한다:
    - status: 시험 절차서 상태 필터
    - assignee: 담당자 필터 (이름 기반, 복수 선택 가능)
    - location: 시험 장소 필터
    - doc: 문서명/ID 검색
    - date: 특정 날짜에 배치된 시험 절차서만 필터

    Returns:
        렌더링된 시험 절차서 목록 HTML
    """
    all_procedures = procedure.get_all()
    procedures_all = list(all_procedures)
    status = request.args.get('status')
    assignees = request.args.getlist('assignee')
    location_filter = request.args.get('location')
    doc_query = (request.args.get('doc') or request.args.get('procedure') or '').strip()
    date_filter = request.args.get('date', '').strip()

    # 담당자 필터 (하나라도 포함되면 통과, 이름 기반)
    if assignees:
        procedures_all = [t for t in procedures_all if any(a in t.get('assignee_names', []) for a in assignees)]
    # 장소 필터
    if location_filter:
        procedures_all = [t for t in procedures_all if t.get('location_name') == location_filter]
    # 문서명/ID 부분 일치 검색 (대소문자 무시)
    if doc_query:
        q = doc_query.lower()
        procedures_all = [t for t in procedures_all
                     if q in (t.get('document_name') or '').lower()
                     or q in str(t.get('document_id', '')).lower()]
    # 날짜 필터: 해당 날짜에 블록이 배치된 시험 절차서만 표시
    if date_filter:
        blocks_on_date = schedule_block.get_by_date(date_filter)
        procedure_ids_on_date = {b['procedure_id'] for b in blocks_on_date if b.get('procedure_id')}
        procedures_all = [t for t in procedures_all if t['id'] in procedure_ids_on_date]

    assignee_options = sorted({
        name for item in all_procedures for name in item.get('assignee_names', []) if name
    })
    locations = _location_options()
    location_map = {loc['name']: loc['name'] for loc in locations}

    all_blocks = schedule_block.get_all()
    procedure_ids_scheduled = {b['procedure_id'] for b in all_blocks if b.get('procedure_id')}

    # 시험 절차서별 배치 상태 및 분할 정보 구성
    schedule_status_map = {}  # procedure_id → 'scheduled' 또는 'queue'
    split_info_map = {}  # procedure_id → { block_count, has_split, blocks }
    blocks_by_procedure = {}  # procedure_id → [블록 리스트]
    for b in all_blocks:
        tid = b.get('procedure_id')
        if tid:
            blocks_by_procedure.setdefault(tid, []).append(b)

    for t in procedures_all:
        tid = t['id']
        procedure_blocks = blocks_by_procedure.get(tid, [])
        # 블록이 하나라도 있으면 배치 완료
        schedule_status_map[tid] = 'scheduled' if procedure_blocks else 'queue'
        total_ids = len(t.get('test_items', []))
        # 분할 여부: 블록의 시험 항목 수가 전체보다 적으면 분할된 것
        has_split = any(b.get('test_item_ids') is not None and len(b.get('test_item_ids', [])) < total_ids
                        for b in procedure_blocks)
        # 각 블록의 상세 정보 구성 (날짜/시간순 정렬)
        block_details = []
        block_locations = []
        for b in sorted(procedure_blocks, key=lambda x: (x['date'], x['start_time'])):
            loc_name = b.get('location_name', '')
            ids = b.get('test_item_ids')
            block_details.append({
                'date': b['date'],
                'start_time': b['start_time'],
                'end_time': b['end_time'],
                'location_name': loc_name,
                'test_item_ids': ids,
                'id_count': len(ids) if ids else total_ids,
            })
            if loc_name and loc_name not in block_locations:
                block_locations.append(loc_name)
        split_info_map[tid] = {
            'block_count': len(procedure_blocks),
            'has_split': has_split,
            'blocks': block_details,
            'block_locations': block_locations,
        }

    # -------------------------------------------------------------------------
    # execution 기반 실행 상태 계산 (#108)
    # 시험 절차서 자체에 status 필드를 저장하지 않고, 실행(execution) 레코드를 기준으로
    # 동적으로 상태를 계산한다. 이렇게 하면 execution 데이터가 변경될 때
    # 진행 상태는 execution에서 계산하므로 catalog를 갱신할 필요가 없다.
    # -------------------------------------------------------------------------
    all_executions = ExecutionRepository.get_all()
    # (test_item_id, procedure_id) 조합을 키로 사용해 재시험 레코드가 섞이지 않게 한다.
    exec_by_procedure_test_item = {
        (ex['test_item_id'], ex.get('procedure_id', '')): ex for ex in all_executions
    }

    execution_status_map = {}
    execution_minutes_map = {}  # procedure_id → 완료된 시험 항목의 예상시간 합계
    for t in procedures_all:
        tid = t['id']
        test_items = t.get('test_items', [])
        if not test_items:
            # 시험 항목가 없는 시험 절차서는 항상 'pending' 처리
            execution_status_map[tid] = 'pending'
            execution_minutes_map[tid] = 0
            continue
        statuses = []
        completed_minutes = 0
        for idf in test_items:
            iid = idf['id'] if isinstance(idf, dict) else idf
            est = idf.get('estimated_minutes', 0) if isinstance(idf, dict) else 0
            ex = exec_by_procedure_test_item.get((iid, tid))
            # execution 레코드가 없으면 아직 시작 전이므로 'pending'
            s = ex['status'] if ex else 'pending'
            statuses.append(s)
            if s == 'completed':
                # 완료된 시험 항목의 시간만 실제 진행된 시간으로 합산
                completed_minutes += est
        if all(s == 'completed' for s in statuses):
            # "완료": 모든 시험 항목가 completed 상태일 때만
            execution_status_map[tid] = 'completed'
        elif any(s in ('in_progress', 'paused', 'completed') for s in statuses):
            # "진행 중": 하나라도 시작된 시험 항목(in_progress/paused/completed)가 있으면
            # (#105 수정: 이전에는 in_progress만 체크했으나, 완료된 시험 항목가 섞인
            #  경우도 진행 중으로 표시해야 하므로 completed도 포함)
            execution_status_map[tid] = 'in_progress'
        else:
            # "대기": 모든 시험 항목가 아직 시작되지 않은 경우
            execution_status_map[tid] = 'pending'
        execution_minutes_map[tid] = completed_minutes

    # -------------------------------------------------------------------------
    # status URL 파라미터 필터 적용 (#108)
    # 구 상태값(waiting)을 새 execution 기반 상태값(pending)으로 매핑하여
    # 기존 북마크/링크가 깨지지 않도록 호환성을 유지한다.
    # 'cancelled'는 execution 기반이 아닌 procedure.status 필드로 구분한다
    # (sync 서비스가 외부에서 삭제된 시험 절차서를 cancelled로 마크하기 때문).
    # -------------------------------------------------------------------------
    if status:
        STATUS_MAPPING = {
            'waiting': 'pending',      # 하위 호환: 구 URL 파라미터 값
            'in_progress': 'in_progress',
            'completed': 'completed',
        }
        if status == 'cancelled':
            # cancelled는 procedure.status 필드로 판단 (execution 기반 상태 아님)
            procedures_all = [t for t in procedures_all if t.get('status') == 'cancelled']
            # 필터링 후 execution_status_map도 대상 시험 절차서만 남기도록 재구성
            execution_status_map = {t['id']: execution_status_map[t['id']]
                                    for t in procedures_all if t['id'] in execution_status_map}
        else:
            exec_status_filter = STATUS_MAPPING.get(status)
            if exec_status_filter:
                # execution_status_map 기반으로 필터링
                procedures_all = [t for t in procedures_all
                             if execution_status_map.get(t['id']) == exec_status_filter]

    from app.features.schedule.services.test_procedures import display_name as make_display_name
    for t in procedures_all:
        t['display_name'] = make_display_name(t)

    return render_template('schedule/procedures/list.html',
                           test_procedures=procedures_all, assignee_options=assignee_options,
                           locations=locations,
                           location_map=location_map,
                           schedule_status_map=schedule_status_map,
                           split_info_map=split_info_map,
                           execution_status_map=execution_status_map,
                           execution_minutes_map=execution_minutes_map,
                           filters={
                               'status': status or '',
                               'assignees': assignees,
                               'location': location_filter or '',
                               'doc': doc_query,
                               'date': date_filter,
                           })


@procedures_bp.route('/new', methods=['GET', 'POST'])
def procedure_new():
    """새 시험 절차서 생성 페이지를 렌더링하거나 생성 요청을 처리한다.

    GET: 빈 폼 렌더링
    POST: 폼 데이터로 시험 절차서 생성

    Returns:
        GET: 시험 절차서 생성 폼 HTML
        POST: 성공 시 목록 페이지로 리다이렉트, 실패 시 폼 페이지로 리다이렉트
    """
    if request.method == 'POST':
        payload = _procedure_payload_from_form()
        if payload['document_id'] is None:
            flash('문서 ID를 입력해주세요.', 'danger')
            return redirect(url_for('procedures.procedure_new'))
        try:
            _procedure_service().create_procedure(payload)
        except TestProcedureError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('procedures.procedure_new'))
        flash('시험 항목이 생성되었습니다.', 'success')
        return redirect(url_for('procedures.procedure_list'))
    locations = _location_options()
    return render_template('schedule/procedures/form.html', procedure=None,
                           locations=locations)


@procedures_bp.route('/<procedure_id>')
def procedure_detail(procedure_id):
    """시험 절차서 상세 페이지를 렌더링한다.

    각 시험 항목가 어떤 블록에 배치되어 있는지도 함께 표시한다.

    Args:
        procedure_id (str): 조회할 시험 절차서 ID

    Returns:
        렌더링된 시험 절차서 상세 HTML 또는 404
    """
    t = procedure.get_by_id(procedure_id)
    if not t:
        abort(404)
    assignee_names = list(t.get('assignee_names', []))
    loc = {'name': t['location_name']} if t.get('location_name') else None

    # 시험 항목별 배치 일정 매핑 (시험 항목 ID → 날짜/시간 정보)
    all_blocks = schedule_block.get_all()
    procedure_blocks = [b for b in all_blocks if b.get('procedure_id') == procedure_id]
    total_ids = [item['id'] if isinstance(item, dict) else item
                 for item in t.get('test_items', [])]
    test_item_schedule = {}  # id → {date, start_time, end_time}
    for b in sorted(procedure_blocks, key=lambda x: (x['date'], x['start_time'])):
        block_ids = b.get('test_item_ids')
        if block_ids:
            covered = block_ids
        else:
            # test_item_ids가 없으면 전체 시험 항목를 커버
            covered = total_ids
        for iid in covered:
            # 같은 시험 항목가 여러 블록에 있으면 첫 번째(가장 이른) 블록 기준
            if iid not in test_item_schedule:
                test_item_schedule[iid] = {
                    'date': b['date'],
                    'start_time': b['start_time'],
                    'end_time': b['end_time'],
                }

    # 시험 항목별 execution 상태 (이 시험 절차서에 속한 레코드만 사용)
    from app.features.execution.repository import ExecutionRepository
    all_executions = ExecutionRepository.get_all()
    test_item_execution = {
        ex['test_item_id']: ex for ex in all_executions if ex.get('procedure_id') == procedure_id
    }

    from app.features.schedule.services.test_procedures import display_name as make_display_name
    t['display_name'] = make_display_name(t)

    return render_template('schedule/procedures/detail.html', procedure=t,
                           assignee_names=assignee_names,
                           test_item_schedule=test_item_schedule,
                           test_item_execution=test_item_execution,
                           location=loc)


@procedures_bp.route('/<procedure_id>/edit', methods=['GET', 'POST'])
def procedure_edit(procedure_id):
    """시험 절차서 수정 페이지를 렌더링하거나 수정 요청을 처리한다.

    Args:
        procedure_id (str): 수정할 시험 절차서 ID

    Returns:
        GET: 기존 데이터가 채워진 수정 폼 HTML
        POST: 성공 시 상세 페이지로 리다이렉트, 실패 시 수정 폼으로 리다이렉트
    """
    t = procedure.get_by_id(procedure_id)
    if not t:
        abort(404)
    if request.method == 'POST':
        payload = _procedure_payload_from_form(t)
        if payload['document_id'] is None:
            flash('문서 ID를 입력해주세요.', 'danger')
            return redirect(url_for('procedures.procedure_edit', procedure_id=procedure_id))
        try:
            _procedure_service().update_procedure(procedure_id, payload)
        except TestProcedureError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('procedures.procedure_edit', procedure_id=procedure_id))
        flash('시험 항목이 수정되었습니다.', 'success')
        return redirect(url_for('procedures.procedure_detail', procedure_id=procedure_id))
    locations = _location_options()
    return render_template('schedule/procedures/form.html', procedure=t,
                           locations=locations)


@procedures_bp.route('/<procedure_id>/delete', methods=['POST'])
def procedure_delete(procedure_id):
    """시험 절차서를 삭제한다.

    Args:
        procedure_id (str): 삭제할 시험 절차서 ID

    Returns:
        목록 페이지로 리다이렉트 또는 404
    """
    t = procedure.get_by_id(procedure_id)
    if not t:
        abort(404)
    try:
        _procedure_service().delete_procedure(procedure_id)
    except TestProcedureError:
        abort(404)
    flash('시험 항목이 삭제되었습니다.', 'success')
    return redirect(url_for('procedures.procedure_list'))


# ---------------------------------------------------------------------------
# API 라우트 (JSON 응답)
# ---------------------------------------------------------------------------

@procedures_bp.route('/api/list')
def api_procedure_list():
    """전체 시험 절차서 목록을 JSON으로 반환한다.

    Returns:
        JSON: {'test_procedures': [시험 절차서 목록]}
    """
    procedures_all = procedure.get_all()
    return jsonify({'test_procedures': procedures_all})


@procedures_bp.route('/api/<procedure_id>')
def api_procedure_detail(procedure_id):
    """시험 절차서 상세 정보를 JSON으로 반환한다.

    담당자명과 장소명도 함께 포함하여 반환한다.

    Args:
        procedure_id (str): 조회할 시험 절차서 ID

    Returns:
        JSON: {'procedure': 시험 절차서 데이터} 또는 404 에러
    """
    t = procedure.get_by_id(procedure_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    result = dict(t)
    from app.features.schedule.services.test_procedures import display_name as make_display_name
    result['display_name'] = make_display_name(result)

    # 각 시험 항목의 실행 상태 정보 추가 (#108 확장)
    all_executions = ExecutionRepository.get_all()
    # (test_item_id, procedure_id) 조합을 키로 사용
    exec_map = {
        (ex['test_item_id'], ex.get('procedure_id', '')): ex['status']
        for ex in all_executions if ex.get('procedure_id') == procedure_id
    }
    
    # test_items 리스트를 순회하며 상태 주입
    enriched_test_items = []
    for idf in t.get('test_items', []):
        if isinstance(idf, dict):
            status = exec_map.get((idf['id'], procedure_id), 'pending')
            enriched_test_items.append({**idf, 'execution_status': status})
        else:
            status = exec_map.get((idf, procedure_id), 'pending')
            enriched_test_items.append({'id': idf, 'execution_status': status})
    
    result['test_items'] = enriched_test_items
    
    return jsonify({'procedure': result})


@procedures_bp.route('/api/create', methods=['POST'])
def api_procedure_create():
    """API를 통해 새 시험 절차서를 생성한다.

    Request Body (JSON):
        - document_id (int): 문서 ID (필수)
        - assignee_names (list, optional): 담당자 이름 리스트
        - location_name (str, optional): 시험 장소 ID
        - document_name (str, optional): 문서명
        - test_items (list, optional): 시험 항목 목록
        - estimated_minutes (int, optional): 예상 소요 시간(분)
        - memo (str, optional): 메모

    Returns:
        JSON: 생성된 시험 절차서 데이터 (201) 또는 에러 (400)
    """
    data = request.get_json() or {}
    document_id = _parse_document_id(data.get('document_id'))
    if document_id is None:
        return jsonify({'error': '문서 ID를 입력해주세요.'}), 400
    test_items = data.get('test_items') or data.get('test_list') or []
    estimated_minutes = _compute_estimated_minutes(test_items) if test_items else int(data.get('estimated_minutes', 0) or 0)
    try:
        created = _procedure_service().create_procedure({
            **data,
            'document_id': document_id,
            'test_items': test_items,
            'estimated_minutes': estimated_minutes,
        })
    except TestProcedureError as exc:
        return _procedure_error_response(exc)
    return jsonify(created), 201


@procedures_bp.route('/api/<procedure_id>/update', methods=['PUT'])
def api_procedure_update(procedure_id):
    """API를 통해 시험 절차서를 수정한다.

    Args:
        procedure_id (str): 수정할 시험 절차서 ID

    Request Body (JSON):
        api_procedure_create와 동일한 필드

    Returns:
        JSON: 수정된 시험 절차서 데이터 또는 에러 (400/404)
    """
    t = procedure.get_by_id(procedure_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    data = request.get_json() or {}
    # 부분 업데이트(patch)일 수도 있고 전체 업데이트일 수도 있음 — 필수값 완화
    document_id = _parse_document_id(data.get('document_id', t.get('document_id')))
    if document_id is None:
        return jsonify({'error': '문서 ID를 입력해주세요.'}), 400
    test_items = data.get('test_items') or data.get('test_list') or t.get('test_items', [])
    estimated_minutes = _compute_estimated_minutes(test_items) if test_items else int(data.get('estimated_minutes', 0) or 0)
    try:
        updated = _procedure_service().update_procedure(procedure_id, {
            **data,
            'document_id': document_id,
            'test_items': test_items,
            'estimated_minutes': estimated_minutes,
        })
    except TestProcedureError as exc:
        return _procedure_error_response(exc)
    return jsonify(updated)


@procedures_bp.route('/api/<procedure_id>/delete', methods=['DELETE'])
def api_procedure_delete(procedure_id):
    """API를 통해 시험 절차서를 삭제한다.

    Args:
        procedure_id (str): 삭제할 시험 절차서 ID

    Returns:
        JSON: 성공 여부 또는 에러 (404)
    """
    t = procedure.get_by_id(procedure_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    try:
        _procedure_service().delete_procedure(procedure_id)
    except TestProcedureError as exc:
        return _procedure_error_response(exc)
    return jsonify({'success': True})


@procedures_bp.route('/api/check-test-item')
def api_check_test_item():
    """시험 항목 ID가 다른 시험 절차서에서 이미 사용 중인지 확인한다.

    시험 절차서 생성/수정 폼에서 실시간 중복 검사에 사용된다.

    Query Parameters:
        id (str): 확인할 시험 항목 ID
        exclude_procedure (str, optional): 중복 검사에서 제외할 시험 절차서 ID
        test_round (int, optional): 현재 시험 절차서의 test_round (재시험 중복 허용에 사용)

    Returns:
        JSON: {'available': bool, 'duplicates': list}
    """
    test_item_id = request.args.get('id', '').strip()
    exclude_procedure = request.args.get('exclude_procedure', '')
    raw_test_round = request.args.get('test_round', '')
    try:
        test_round = int(raw_test_round) if raw_test_round != '' else None
    except ValueError:
        test_round = None
    if not test_item_id:
        return jsonify({'available': True})
    dupes = procedure.validate_unique_test_items(
        [{'id': test_item_id}],
        exclude_procedure_id=exclude_procedure or None,
        test_round=test_round,
    )
    return jsonify({'available': len(dupes) == 0, 'duplicates': dupes})
