"""
시험실행(Execution) REST API 블루프린트.

URL 접두사: /execution/api

이 모듈은 시험 실행의 전체 생명주기를 HTTP 엔드포인트로 노출한다.
- 실행 목록 조회 (/list, /item/<id>)
- 상태 전이 (/start, /pause, /resume, /complete, /reset)
- 메타데이터 갱신 (/comment, /pending-comment, /performer)
- 외부 연동 (/timing/<id>)

데이터 흐름:
    schedule 모델(task, block, location) → _load_schedule_data()로 컨텍스트 구성
    → _build_item_dict()로 단일 응답 객체 조립
    → ExecutionRepository로 실행 상태 읽기/쓰기
"""

import logging
import os
import threading

import requests
from flask import Blueprint, jsonify, request, session

from app.features.execution.models.execution import ExecutionRepository

api_bp = Blueprint('execution_api', __name__, url_prefix='/execution/api')

logger = logging.getLogger(__name__)


def _notify_timing(identifier_id: str, task_id: str, elapsed_seconds: int):
    """시험완료 후 외부 서버에 소요시간을 비동기로 전송한다.

    완료 API 응답 지연을 막기 위해 daemon 스레드에서 실행한다.
    API_BASE_URL 환경변수가 없으면 즉시 반환하여 내부 전용 배포에서는 동작하지 않는다.

    전송 실패는 경고 로그만 남기고 예외를 전파하지 않는다.
    (시험 완료 자체는 이미 저장됐으므로 알림 실패가 치명적이지 않다.)
    """
    base_url = os.environ.get('API_BASE_URL', '').rstrip('/')
    if not base_url:
        return

    def _send():
        try:
            # task의 version_id를 외부 API의 ofp_id로 매핑
            from app.features.schedule.models import task as task_repo
            task = task_repo.get_by_id(task_id)
            ofp_id = task.get('version_id', '') if task else ''

            api_key = os.environ.get('API_KEY', '')
            headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
            resp = requests.post(
                f'{base_url}/update_test_time',
                json={'test_id': identifier_id, 'ofp_id': ofp_id, 'time_taking': int(elapsed_seconds)},
                headers=headers,
                timeout=10,
            )
            if not resp.ok:
                logger.warning('update_test_time 실패: %s %s', resp.status_code, resp.text)
        except Exception as e:
            logger.warning('update_test_time 전송 오류: %s', e)

    threading.Thread(target=_send, daemon=True).start()


def _identifier_total_count(identifier: dict) -> int:
    """식별자 데이터에 저장된 전체 시험 건수를 반환한다.

    외부 API 연동 전까지 10을 고정 반환하던 값이 결과를 오염시키지 않도록,
    동기화 데이터에 명시된 카운트 필드를 우선 사용하고 없으면 0으로 둔다.
    """
    for key in ('total_count', 'pf_num', 'test_count', 'case_count', 'count'):
        value = identifier.get(key)
        if value in (None, ''):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _get_total_count(identifier_id: str, task_id: str = '') -> int:
    from app.features.schedule.models import task as task_repo

    for task in task_repo.get_all():
        if task_id and task.get('id') != task_id:
            continue
        for identifier in task.get('identifiers', []):
            if isinstance(identifier, dict) and identifier.get('id') == identifier_id:
                return _identifier_total_count(identifier)
    return 0


def _execution_response(ex):
    """실행 레코드를 API 응답용 딕셔너리로 변환한다.

    elapsed_seconds는 저장된 스냅샷 값 대신 segments로부터 실시간 재계산하여
    반환한다. 진행 중(end=None)인 구간이 있으면 호출 시각까지의 시간이 포함된다.

    None이 전달되면 None을 반환하며, 호출부에서 execution 필드가 null인
    응답으로 처리한다(미시작 식별자).
    """
    if ex is None:
        return None
    return {
        'id': ex['id'],
        'status': ex['status'],
        # segments 기반 실시간 계산 — 저장된 elapsed_seconds 필드는 스냅샷용
        'elapsed_seconds': ExecutionRepository.compute_elapsed_seconds(ex.get('segments', [])),
        'total_count': ex.get('total_count', 0),
        'fail_count': ex.get('fail_count', 0),
        'block_count': ex.get('block_count', 0),
        'pass_count': ex.get('pass_count', 0),
        'comment': ex.get('comment', ''),
        'performer': ex.get('performer', ''),
        'completed_at': ex.get('completed_at'),
    }


def _load_schedule_data():
    """스케줄 데이터(태스크·블록·장소)를 읽어 실행 목록 구성에 필요한 맵을 반환한다.

    Returns:
        tasks (list): 전체 태스크 목록
        locations (dict): location_id → location 객체
        date_map (dict): (task_id, identifier_id) → 가장 이른 배치 날짜(YYYY-MM-DD)
            식별자가 여러 블록에 걸쳐 배치됐을 때 가장 빠른 날짜를 사용한다.
        block_loc_map (dict): (task_id, identifier_id) → 블록에 지정된 location_id
            블록에 장소가 명시되지 않은 식별자는 포함되지 않으며,
            이 경우 태스크의 location_id로 폴백한다.
            (버그 #104 수정: 이전에는 항상 태스크 장소를 사용했다.)

    date_map과 block_loc_map을 갱신하는 기준:
        - 한 식별자에 블록이 여러 개면, 날짜가 가장 이른 블록의 장소를 채택한다.
          (가장 이른 날짜와 그 날의 장소를 한 번에 갱신해야 일관성이 유지됨)
    """
    from app.features.schedule.models import task as task_repo
    from app.features.schedule.models import schedule_block as block_repo
    from app.features.schedule.models import location as loc_repo

    tasks = task_repo.get_all()
    blocks = block_repo.get_all()
    locations = {loc['id']: loc for loc in loc_repo.get_all()}

    date_map = {}        # (task_id, identifier_id) → earliest scheduled date
    block_loc_map = {}   # (task_id, identifier_id) → location_id from block

    for block in blocks:
        block_date = block.get('date', '')
        block_task_id = block.get('task_id', '')
        # identifier_ids=None이면 태스크의 모든 식별자를 포함하는 블록
        block_iids = block.get('identifier_ids')
        block_loc = block.get('location_id', '')
        task = next((t for t in tasks if t['id'] == block_task_id), None)
        if not task:
            continue
        for identifier in task.get('identifiers', []):
            iid = identifier['id'] if isinstance(identifier, dict) else identifier
            # block_iids가 None(전체 포함 블록)이거나 해당 식별자가 블록에 속할 때만 처리
            if block_iids is None or iid in block_iids:
                key = (block_task_id, iid)
                # 더 이른 날짜의 블록이 발견되면 날짜와 장소를 함께 갱신
                if key not in date_map or block_date < date_map[key]:
                    date_map[key] = block_date
                    if block_loc:
                        block_loc_map[key] = block_loc

    return tasks, locations, date_map, block_loc_map


def _build_item_dict(task, identifier, locations, scheduled_date, block_loc_id=''):
    """태스크·식별자·스케줄·실행 데이터를 하나의 응답 딕셔너리로 조립한다.

    장소 우선순위: 블록에 명시된 location_id > 태스크의 location_id
    (버그 #104 수정 결과 — 블록 장소가 더 구체적인 정보이므로 우선 적용)

    Args:
        task: 상위 태스크 딕셔너리
        identifier: 식별자 딕셔너리 (id, name, estimated_minutes 등 포함)
        locations: location_id → location 객체 딕셔너리
        scheduled_date: 이 식별자의 가장 이른 배치 날짜
        block_loc_id: 블록에서 가져온 location_id (없으면 빈 문자열)
    """
    iid = identifier['id']
    # 블록 장소가 있으면 우선, 없으면 태스크 장소로 폴백
    loc_id = block_loc_id or task.get('location_id', '')
    loc_name = locations.get(loc_id, {}).get('name', '') if loc_id else ''
    execution = ExecutionRepository.get_by_identifier_and_task(iid, task['id'])
    completed_at = execution.get('completed_at') if execution else None
    exam_no = task.get('exam_no')
    doc_name = task.get('doc_name', '')
    display_name = f'{doc_name} ({exam_no}차)' if exam_no is not None and exam_no != 1 else doc_name
    return {
        'identifier_id': iid,
        'identifier_name': identifier.get('name', ''),
        'task_id': task['id'],
        'exam_no': exam_no,
        'doc_name': doc_name,
        'display_name': display_name,
        'assignee_names': task.get('assignee_names', []),
        'estimated_minutes': identifier.get('estimated_minutes', 0),
        'location_id': loc_id,
        'location_name': loc_name,
        'scheduled_date': scheduled_date,
        'display_date': completed_at or scheduled_date,
        'total_count': _identifier_total_count(identifier),
        # 실행 레코드가 없으면 None (미시작 상태를 프론트에서 pending으로 표시)
        'execution': _execution_response(execution),
    }


@api_bp.route('/list')
def execution_list():
    """전체 식별자 목록을 실행 상태와 함께 반환한다.

    쿼리 파라미터:
        date     (str): YYYY-MM-DD 형식. 해당 날짜에 배치된 식별자만 반환
        location (str): location_id. 해당 장소의 식별자만 반환

    장소 필터는 블록 장소 우선, 없으면 태스크 장소 기준으로 적용한다.
    """
    date_filter = request.args.get('date', '')
    location_filter = request.args.get('location', '')

    tasks, locations, date_map, block_loc_map = _load_schedule_data()
    result = []
    for task in tasks:
        for identifier in task.get('identifiers', []):
            if not isinstance(identifier, dict):
                continue
            iid = identifier['id']
            key = (task['id'], iid)
            scheduled_date = date_map.get(key, '')
            block_loc_id = block_loc_map.get(key, '')
            # 필터 적용 시 블록 장소 우선, 없으면 태스크 장소로 폴백
            loc_id = block_loc_id or task.get('location_id', '')
            if date_filter and scheduled_date != date_filter:
                continue
            if location_filter and loc_id != location_filter:
                continue
            result.append(_build_item_dict(task, identifier, locations, scheduled_date, block_loc_id))

    return jsonify(result)


@api_bp.route('/item/<identifier_id>')
def get_item(identifier_id):
    """단일 식별자의 상세 실행 정보를 반환한다."""
    task_id_filter = request.args.get('task_id', '')
    tasks, locations, date_map, block_loc_map = _load_schedule_data()
    for task in tasks:
        if task_id_filter and task['id'] != task_id_filter:
            continue
        for identifier in task.get('identifiers', []):
            if not isinstance(identifier, dict):
                continue
            if identifier['id'] != identifier_id:
                continue
            return jsonify(_build_item_dict(
                task, identifier, locations,
                date_map.get((task['id'], identifier_id), ''),
                block_loc_map.get((task['id'], identifier_id), ''),
            ))
    return jsonify({'error': 'not found'}), 404


@api_bp.route('/total-count/<identifier_id>')
def total_count(identifier_id):
    """식별자의 전체 시험 케이스 수를 반환한다."""
    return jsonify({'total_count': _get_total_count(identifier_id, request.args.get('task_id', ''))})


@api_bp.route('/whoami')
def whoami():
    """세션에 저장된 현재 로그인 사용자명을 반환한다."""
    return jsonify({'username': session.get('username', '')})


@api_bp.route('/login', methods=['POST'])
def login():
    """간이 로그인: 사용자명을 세션에 저장한다.

    인증이 목적이 아니라 시험 수행자를 추적하기 위한 최소한의 식별 기능이다.
    중복 시험 시작 방지(동일 사용자가 두 개 이상 진행 불가) 로직에 사용된다.
    """
    body = request.get_json(silent=True) or {}
    username = body.get('username', '').strip()
    if not username:
        return jsonify({'error': 'username required'}), 400
    session['username'] = username
    return jsonify({'username': username})


@api_bp.route('/start', methods=['POST'])
def start():
    """시험 실행을 시작한다.

    중복 진행 방지 로직:
        세션 사용자가 현재 다른 식별자를 진행 중이면 409를 반환한다.
        다른 수행자가 진행 중인 실행은 현재 사용자의 시작을 막지 않는다.
        단, 동일 식별자에 대한 재시작은 항상 허용한다.

    시작 후 performer가 비어 있으면 현재 세션 사용자를 자동으로 지정한다.
    (ExecutionRepository.start()에서 performer를 초기화하지 않으므로 여기서 설정)
    """
    body = request.get_json(silent=True) or {}
    identifier_id = body.get('identifier_id', '').strip()
    task_id = body.get('task_id', '').strip()
    if not identifier_id or not task_id:
        return jsonify({'error': 'identifier_id and task_id required'}), 400

    current_user = session.get('username', '')
    if current_user:
        for ex in ExecutionRepository.get_all():
            if ex.get('status') != 'in_progress':
                continue
            if ex.get('identifier_id') == identifier_id:
                # 같은 식별자면 재시작 허용 — 충돌 아님
                continue
            performer = ex.get('performer', '')
            if performer == current_user:
                return jsonify({'error': '이미 진행 중인 시험이 있습니다.', 'code': 'user_busy'}), 409

    total = _get_total_count(identifier_id, task_id)
    ex = ExecutionRepository.start(identifier_id, task_id, total_count=total)

    # start() 후 performer가 비어 있을 때만 세션 사용자를 지정
    if ex and current_user and not ex.get('performer'):
        ExecutionRepository.update_performer(ex['id'], current_user)
        ex['performer'] = current_user

    return jsonify(ex), 201


@api_bp.route('/pause', methods=['POST'])
def pause():
    """진행 중인 시험을 일시정지한다."""
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.pause(execution_id)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404
    return jsonify(ex)


@api_bp.route('/resume', methods=['POST'])
def resume():
    """일시정지된 시험을 재개한다."""
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.resume(execution_id)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404
    return jsonify(ex)


@api_bp.route('/complete', methods=['POST'])
def complete():
    """시험을 완료 처리하고, 소요시간을 외부 서버에 비동기로 전송한다.

    완료 후 _notify_timing()을 호출하지만, 전송 실패가 완료 응답에 영향을 주지 않는다.
    """
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    fail_count = body.get('fail_count', 0)
    block_count = body.get('block_count', 0)
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.complete(execution_id, fail_count, block_count)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404

    # 완료 후 segments로 최종 경과시간을 재계산하여 전송
    elapsed = ExecutionRepository.compute_elapsed_seconds(ex.get('segments', []))
    _notify_timing(ex.get('identifier_id', ''), ex.get('task_id', ''), elapsed)

    return jsonify(ex)


@api_bp.route('/pending-comment', methods=['PUT'])
def pending_comment():
    """시험 시작 전 식별자에 코멘트를 저장한다.

    실행 레코드가 없으면 pending 상태로 생성, 이미 있으면 save_pre_comment()의
    상태 분기 로직에 따라 처리된다. (진행 중이면 무시)
    """
    body = request.get_json(silent=True) or {}
    identifier_id = body.get('identifier_id', '').strip()
    task_id = body.get('task_id', '').strip()
    comment = body.get('comment', '')
    if not identifier_id or not task_id:
        return jsonify({'error': 'identifier_id and task_id required'}), 400
    ExecutionRepository.save_pre_comment(identifier_id, task_id, comment)
    return jsonify({'ok': True})


@api_bp.route('/comment', methods=['PUT'])
def update_comment():
    """진행 중/완료된 실행 레코드의 코멘트를 갱신한다."""
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    comment = body.get('comment', '')
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.update_comment(execution_id, comment)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@api_bp.route('/performer', methods=['PUT'])
def update_performer():
    """실행 레코드의 수행자(performer)를 갱신한다."""
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    performer = body.get('performer', '')
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.update_performer(execution_id, performer)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@api_bp.route('/timing/<identifier_id>', methods=['PATCH'])
def update_timing(identifier_id):
    """외부 API로부터 시험 소요시간(초)을 수신해 estimated_minutes를 갱신한다.

    실제 소요시간을 올림(ceil)하여 분 단위로 변환 후,
    해당 식별자의 estimated_minutes를 업데이트하고
    태스크 전체의 estimated_minutes(식별자 합계)도 재계산한다.

    선택적 검증 파라미터(doc_name, identifier_name)가 제공되면
    일치 여부를 확인하여 잘못된 식별자에 적용되는 것을 방지한다.
    """
    body = request.get_json(silent=True) or {}
    elapsed_seconds = body.get('elapsed_seconds')
    if elapsed_seconds is None:
        return jsonify({'error': 'elapsed_seconds required'}), 400

    from app.features.schedule.models import task as task_repo
    from math import ceil

    for t in task_repo.get_all():
        for item in t.get('identifiers', []):
            if not isinstance(item, dict) or item.get('id') != identifier_id:
                continue

            # doc_name / identifier_name이 넘어왔을 때만 일치 여부 검증
            if body.get('doc_name') and t.get('doc_name') != body['doc_name']:
                return jsonify({'error': 'doc_name mismatch'}), 400
            if body.get('identifier_name') and item.get('name') != body['identifier_name']:
                return jsonify({'error': 'identifier_name mismatch'}), 400

            # 초 단위 소요시간을 올림하여 분으로 변환
            new_minutes = ceil(int(elapsed_seconds) / 60)
            identifiers = list(t['identifiers'])
            idx = identifiers.index(item)
            identifiers[idx] = {**item, 'estimated_minutes': new_minutes}

            # 태스크 전체 estimated_minutes = 소속 식별자 시간 합계
            total_minutes = sum(
                i.get('estimated_minutes', 0) for i in identifiers if isinstance(i, dict)
            )
            task_repo.patch(t['id'], identifiers=identifiers, estimated_minutes=total_minutes)
            return jsonify({'ok': True, 'identifier_id': identifier_id, 'estimated_minutes': new_minutes})

    return jsonify({'error': 'identifier not found'}), 404


@api_bp.route('/reset', methods=['POST'])
def reset():
    """실행 레코드를 pending 상태로 초기화한다. (재시험 또는 잘못 시작된 경우)"""
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.reset(execution_id)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(ex)
