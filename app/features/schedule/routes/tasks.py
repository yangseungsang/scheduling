"""
시험 항목(태스크) 관리 라우트 모듈.

태스크의 CRUD(생성, 조회, 수정, 삭제)를 처리하는 웹 페이지 라우트와
REST API 엔드포인트를 제공한다. 태스크는 절차서 식별자, 담당자,
시험 장소, 식별자 목록(test_list) 등을 포함한다.
"""

import json

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, abort

from app.features.schedule.models import task, user, location, version, schedule_block

# 태스크 관련 라우트가 등록되는 블루프린트
tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


def _parse_test_list_from_form():
    """폼의 숨겨진 JSON 필드에서 test_list(식별자 목록)를 파싱한다.

    폼 제출 시 JavaScript가 식별자 목록을 JSON 문자열로 직렬화하여
    'test_list_json' 필드에 담아 전송한다.

    Returns:
        list: 파싱된 식별자 목록 (각 항목은 dict). 파싱 실패 시 빈 리스트.
    """
    raw = request.form.get('test_list_json', '').strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return []


def _compute_estimated_minutes(test_list):
    """식별자 목록의 예상 소요 시간 합계를 계산한다.

    Args:
        test_list (list): 식별자 목록 (각 항목에 'estimated_minutes' 포함)

    Returns:
        int: 전체 예상 소요 시간(분)
    """
    return sum(item.get('estimated_minutes', 0) for item in test_list if isinstance(item, dict))


# ---------------------------------------------------------------------------
# 템플릿 렌더링 라우트 (웹 페이지)
# ---------------------------------------------------------------------------

@tasks_bp.route('/')
def task_list():
    """태스크 목록 페이지를 렌더링한다.

    다양한 필터 조건을 지원한다:
    - status: 태스크 상태 필터
    - assignee: 담당자 필터 (복수 선택 가능)
    - location: 시험 장소 필터
    - procedure: 절차서 식별자 검색
    - date: 특정 날짜에 배치된 태스크만 필터

    Returns:
        렌더링된 태스크 목록 HTML
    """
    tasks_all = task.get_all()
    status = request.args.get('status')
    assignees = request.args.getlist('assignee')
    location_filter = request.args.get('location')
    procedure = request.args.get('procedure', '').strip()
    date_filter = request.args.get('date', '').strip()

    # 상태 필터 적용
    if status:
        tasks_all = [t for t in tasks_all if t['status'] == status]
    # 담당자 필터 (하나라도 포함되면 통과)
    if assignees:
        tasks_all = [t for t in tasks_all if any(a in t.get('assignee_ids', []) for a in assignees)]
    # 장소 필터
    if location_filter:
        tasks_all = [t for t in tasks_all if t.get('location_id') == location_filter]
    # 절차서 식별자 부분 일치 검색 (대소문자 무시)
    if procedure:
        tasks_all = [t for t in tasks_all if procedure.lower() in t.get('procedure_id', '').lower()]
    # 날짜 필터: 해당 날짜에 블록이 배치된 태스크만 표시
    if date_filter:
        blocks_on_date = schedule_block.get_by_date(date_filter)
        task_ids_on_date = {b['task_id'] for b in blocks_on_date if b.get('task_id')}
        tasks_all = [t for t in tasks_all if t['id'] in task_ids_on_date]

    users = user.get_all()
    locations = location.get_all()
    versions = version.get_all()
    user_map = {u['id']: u['name'] for u in users}
    location_map = {loc['id']: loc['name'] for loc in locations}

    all_blocks = schedule_block.get_all()
    task_ids_scheduled = {b['task_id'] for b in all_blocks if b.get('task_id')}

    # 태스크별 배치 상태 및 분할 정보 구성
    schedule_status_map = {}  # task_id → 'scheduled' 또는 'queue'
    split_info_map = {}  # task_id → { block_count, has_split, blocks }
    blocks_by_task = {}  # task_id → [블록 리스트]
    for b in all_blocks:
        tid = b.get('task_id')
        if tid:
            blocks_by_task.setdefault(tid, []).append(b)

    location_map_full = {loc['id']: loc for loc in locations}
    for t in tasks_all:
        tid = t['id']
        task_blocks = blocks_by_task.get(tid, [])
        # 블록이 하나라도 있으면 배치 완료
        schedule_status_map[tid] = 'scheduled' if task_blocks else 'queue'
        total_ids = len(t.get('test_list', []))
        # 분할 여부: 블록의 식별자 수가 전체보다 적으면 분할된 것
        has_split = any(b.get('identifier_ids') is not None and len(b.get('identifier_ids', [])) < total_ids
                        for b in task_blocks)
        # 각 블록의 상세 정보 구성 (날짜/시간순 정렬)
        block_details = []
        for b in sorted(task_blocks, key=lambda x: (x['date'], x['start_time'])):
            loc_obj = location_map_full.get(b.get('location_id'))
            ids = b.get('identifier_ids')
            block_details.append({
                'date': b['date'],
                'start_time': b['start_time'],
                'end_time': b['end_time'],
                'location_name': loc_obj['name'] if loc_obj else '',
                'identifier_ids': ids,
                'id_count': len(ids) if ids else total_ids,
            })
        split_info_map[tid] = {
            'block_count': len(task_blocks),
            'has_split': has_split,
            'blocks': block_details,
        }

    return render_template('schedule/tasks/list.html',
                           tasks=tasks_all, users=users,
                           locations=locations, versions=versions,
                           user_map=user_map, location_map=location_map,
                           schedule_status_map=schedule_status_map,
                           split_info_map=split_info_map,
                           filters={
                               'status': status or '',
                               'assignees': assignees,
                               'location': location_filter or '',
                               'procedure': procedure,
                               'date': date_filter,
                           })


@tasks_bp.route('/new', methods=['GET', 'POST'])
def task_new():
    """새 태스크 생성 페이지를 렌더링하거나 생성 요청을 처리한다.

    GET: 빈 폼 렌더링
    POST: 폼 데이터로 태스크 생성

    Returns:
        GET: 태스크 생성 폼 HTML
        POST: 성공 시 목록 페이지로 리다이렉트, 실패 시 폼 페이지로 리다이렉트
    """
    if request.method == 'POST':
        procedure_id = request.form.get('procedure_id', '').strip()
        if not procedure_id:
            flash('절차서 식별자를 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_new'))
        assignee_ids = request.form.getlist('assignee_ids')
        test_list = _parse_test_list_from_form()
        # test_list가 있으면 식별자 시간 합계 사용, 없으면 직접 입력값 사용
        estimated_minutes = _compute_estimated_minutes(test_list) if test_list else int(request.form.get('estimated_minutes', 0) or 0)

        # 식별자 ID 중복 검사
        dupes = task.validate_unique_identifiers(test_list)
        if dupes:
            flash(f'중복된 식별자가 있습니다: {", ".join(dupes)}', 'danger')
            return redirect(url_for('tasks.task_new'))

        task.create(
            procedure_id=procedure_id,
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_minutes=estimated_minutes,
            memo=request.form.get('memo', '').strip(),
        )
        flash('시험 항목이 생성되었습니다.', 'success')
        return redirect(url_for('tasks.task_list'))
    users = user.get_all()
    locations = location.get_all()
    versions = version.get_all()
    return render_template('schedule/tasks/form.html', task=None,
                           users=users, locations=locations, versions=versions)


@tasks_bp.route('/<task_id>')
def task_detail(task_id):
    """태스크 상세 페이지를 렌더링한다.

    각 식별자가 어떤 블록에 배치되어 있는지도 함께 표시한다.

    Args:
        task_id (str): 조회할 태스크 ID

    Returns:
        렌더링된 태스크 상세 HTML 또는 404
    """
    t = task.get_by_id(task_id)
    if not t:
        abort(404)
    users = user.get_all()
    user_map = {u['id']: u['name'] for u in users}
    assignee_names = [user_map.get(uid, uid) for uid in t.get('assignee_ids', [])]
    loc = location.get_by_id(t.get('location_id')) if t.get('location_id') else None

    # 식별자별 배치 일정 매핑 (식별자 ID → 날짜/시간 정보)
    all_blocks = schedule_block.get_all()
    task_blocks = [b for b in all_blocks if b.get('task_id') == task_id]
    total_ids = [item['id'] if isinstance(item, dict) else item
                 for item in t.get('test_list', [])]
    identifier_schedule = {}  # id → {date, start_time, end_time}
    for b in sorted(task_blocks, key=lambda x: (x['date'], x['start_time'])):
        block_ids = b.get('identifier_ids')
        if block_ids:
            covered = block_ids
        else:
            # identifier_ids가 없으면 전체 식별자를 커버
            covered = total_ids
        for iid in covered:
            # 같은 식별자가 여러 블록에 있으면 첫 번째(가장 이른) 블록 기준
            if iid not in identifier_schedule:
                identifier_schedule[iid] = {
                    'date': b['date'],
                    'start_time': b['start_time'],
                    'end_time': b['end_time'],
                }

    return render_template('schedule/tasks/detail.html', task=t,
                           assignee_names=assignee_names,
                           identifier_schedule=identifier_schedule,
                           location=loc)


@tasks_bp.route('/<task_id>/edit', methods=['GET', 'POST'])
def task_edit(task_id):
    """태스크 수정 페이지를 렌더링하거나 수정 요청을 처리한다.

    Args:
        task_id (str): 수정할 태스크 ID

    Returns:
        GET: 기존 데이터가 채워진 수정 폼 HTML
        POST: 성공 시 상세 페이지로 리다이렉트, 실패 시 수정 폼으로 리다이렉트
    """
    t = task.get_by_id(task_id)
    if not t:
        abort(404)
    if request.method == 'POST':
        procedure_id = request.form.get('procedure_id', '').strip()
        if not procedure_id:
            flash('절차서 식별자를 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_edit', task_id=task_id))
        assignee_ids = request.form.getlist('assignee_ids')
        test_list = _parse_test_list_from_form()
        estimated_minutes = _compute_estimated_minutes(test_list) if test_list else int(request.form.get('estimated_minutes', 0) or 0)
        remaining_minutes = int(request.form.get('remaining_minutes', 0) or 0)

        # 식별자 ID 중복 검사 (자기 자신은 제외)
        dupes = task.validate_unique_identifiers(test_list, exclude_task_id=task_id)
        if dupes:
            flash(f'중복된 식별자가 있습니다: {", ".join(dupes)}', 'danger')
            return redirect(url_for('tasks.task_edit', task_id=task_id))

        task.update(
            task_id=task_id,
            procedure_id=procedure_id,
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_minutes=estimated_minutes,
            remaining_minutes=remaining_minutes,
            status=request.form.get('status', 'waiting'),
            memo=request.form.get('memo', '').strip(),
        )
        flash('시험 항목이 수정되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    users = user.get_all()
    locations = location.get_all()
    versions = version.get_all()
    return render_template('schedule/tasks/form.html', task=t,
                           users=users, locations=locations, versions=versions)


@tasks_bp.route('/<task_id>/delete', methods=['POST'])
def task_delete(task_id):
    """태스크를 삭제한다.

    Args:
        task_id (str): 삭제할 태스크 ID

    Returns:
        목록 페이지로 리다이렉트 또는 404
    """
    t = task.get_by_id(task_id)
    if not t:
        abort(404)
    task.delete(task_id)
    flash('시험 항목이 삭제되었습니다.', 'success')
    return redirect(url_for('tasks.task_list'))


# ---------------------------------------------------------------------------
# API 라우트 (JSON 응답)
# ---------------------------------------------------------------------------

@tasks_bp.route('/api/list')
def api_task_list():
    """전체 태스크 목록을 JSON으로 반환한다.

    Returns:
        JSON: {'tasks': [태스크 리스트]}
    """
    tasks_all = task.get_all()
    return jsonify({'tasks': tasks_all})


@tasks_bp.route('/api/<task_id>')
def api_task_detail(task_id):
    """태스크 상세 정보를 JSON으로 반환한다.

    담당자명과 장소명도 함께 포함하여 반환한다.

    Args:
        task_id (str): 조회할 태스크 ID

    Returns:
        JSON: {'task': 태스크 데이터} 또는 404 에러
    """
    t = task.get_by_id(task_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    users = user.get_all()
    user_map = {u['id']: u['name'] for u in users}
    locations = location.get_all()
    loc_map = {loc['id']: loc['name'] for loc in locations}
    result = dict(t)
    # 담당자 ID를 이름으로 변환하여 추가
    result['assignee_names'] = [user_map.get(uid, uid) for uid in t.get('assignee_ids', [])]
    # 장소 ID를 이름으로 변환하여 추가
    result['location_name'] = loc_map.get(t.get('location_id', ''), '')
    return jsonify({'task': result})


@tasks_bp.route('/api/create', methods=['POST'])
def api_task_create():
    """API를 통해 새 태스크를 생성한다.

    Request Body (JSON):
        - procedure_id (str): 절차서 식별자 (필수)
        - assignee_ids (list, optional): 담당자 ID 리스트
        - location_id (str, optional): 시험 장소 ID
        - section_name (str, optional): 장절명
        - procedure_owner (str, optional): 절차서 작성자
        - test_list (list, optional): 식별자 목록
        - estimated_minutes (int, optional): 예상 소요 시간(분)
        - memo (str, optional): 메모

    Returns:
        JSON: 생성된 태스크 데이터 (201) 또는 에러 (400)
    """
    data = request.get_json()
    if not data or not data.get('procedure_id', '').strip():
        return jsonify({'error': '절차서 식별자를 입력해주세요.'}), 400
    test_list = data.get('test_list', [])
    estimated_minutes = _compute_estimated_minutes(test_list) if test_list else int(data.get('estimated_minutes', 0) or 0)

    # 식별자 중복 검사
    dupes = task.validate_unique_identifiers(test_list)
    if dupes:
        return jsonify({'error': f'중복된 식별자: {", ".join(dupes)}'}), 400

    t = task.create(
        procedure_id=data['procedure_id'].strip(),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=test_list,
        estimated_minutes=estimated_minutes,
        memo=data.get('memo', ''),
    )
    return jsonify(t), 201


@tasks_bp.route('/api/<task_id>/update', methods=['PUT'])
def api_task_update(task_id):
    """API를 통해 태스크를 수정한다.

    Args:
        task_id (str): 수정할 태스크 ID

    Request Body (JSON):
        api_task_create와 동일한 필드 + status, remaining_minutes

    Returns:
        JSON: 수정된 태스크 데이터 또는 에러 (400/404)
    """
    t = task.get_by_id(task_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if not data or not data.get('procedure_id', '').strip():
        return jsonify({'error': '절차서 식별자를 입력해주세요.'}), 400
    test_list = data.get('test_list', [])
    estimated_minutes = _compute_estimated_minutes(test_list) if test_list else int(data.get('estimated_minutes', 0) or 0)

    # 식별자 중복 검사 (자기 자신은 제외)
    dupes = task.validate_unique_identifiers(test_list, exclude_task_id=task_id)
    if dupes:
        return jsonify({'error': f'중복된 식별자: {", ".join(dupes)}'}), 400

    updated = task.update(
        task_id=task_id,
        procedure_id=data['procedure_id'].strip(),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=test_list,
        estimated_minutes=estimated_minutes,
        remaining_minutes=int(data.get('remaining_minutes', 0) or 0),
        status=data.get('status', 'waiting'),
        memo=data.get('memo', ''),
    )
    return jsonify(updated)


@tasks_bp.route('/api/<task_id>/delete', methods=['DELETE'])
def api_task_delete(task_id):
    """API를 통해 태스크를 삭제한다.

    Args:
        task_id (str): 삭제할 태스크 ID

    Returns:
        JSON: 성공 여부 또는 에러 (404)
    """
    t = task.get_by_id(task_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    task.delete(task_id)
    return jsonify({'success': True})


@tasks_bp.route('/api/procedure/<procedure_id>')
def api_procedure_lookup(procedure_id):
    """절차서 ID로 외부 절차서 정보를 조회한다.

    외부 데이터 소스에서 절차서 메타데이터를 가져오는 데 사용된다.

    Args:
        procedure_id (str): 조회할 절차서 식별자

    Returns:
        JSON: 절차서 정보 또는 에러 (404)
    """
    from app.features.schedule.services.procedure import lookup
    result = lookup(procedure_id)
    if not result:
        return jsonify({'error': '절차서를 찾을 수 없습니다.'}), 404
    return jsonify(result)


@tasks_bp.route('/api/check-identifier')
def api_check_identifier():
    """식별자 ID가 다른 태스크에서 이미 사용 중인지 확인한다.

    태스크 생성/수정 폼에서 실시간 중복 검사에 사용된다.

    Query Parameters:
        id (str): 확인할 식별자 ID
        exclude_task (str, optional): 중복 검사에서 제외할 태스크 ID

    Returns:
        JSON: {'available': bool, 'duplicates': list}
    """
    identifier_id = request.args.get('id', '').strip()
    exclude_task = request.args.get('exclude_task', '')
    if not identifier_id:
        return jsonify({'available': True})
    dupes = task.validate_unique_identifiers(
        [{'id': identifier_id}],
        exclude_task_id=exclude_task or None,
    )
    return jsonify({'available': len(dupes) == 0, 'duplicates': dupes})
