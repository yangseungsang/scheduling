import logging
import os
import threading

import requests
from flask import Blueprint, jsonify, request, session

from app.features.execution.models.execution import ExecutionRepository

api_bp = Blueprint('execution_api', __name__, url_prefix='/execution/api')

logger = logging.getLogger(__name__)


def _notify_timing(identifier_id: str, task_id: str, elapsed_seconds: int):
    """시험완료 후 외부 서버에 소요시간을 비동기로 전송한다."""
    base_url = os.environ.get('API_BASE_URL', '').rstrip('/')
    if not base_url:
        return

    def _send():
        try:
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


def _get_total_count(identifier_id: str) -> int:
    # TODO: 실제 외부 API 연동
    return 10


def _execution_response(ex):
    if ex is None:
        return None
    return {
        'id': ex['id'],
        'status': ex['status'],
        'elapsed_seconds': ExecutionRepository.compute_elapsed_seconds(ex.get('segments', [])),
        'total_count': ex.get('total_count', 0),
        'fail_count': ex.get('fail_count', 0),
        'block_count': ex.get('block_count', 0),
        'pass_count': ex.get('pass_count', 0),
        'comment': ex.get('comment', ''),
        'performer': ex.get('performer', ''),
    }


def _load_schedule_data():
    from app.features.schedule.models import task as task_repo
    from app.features.schedule.models import schedule_block as block_repo
    from app.features.schedule.models import location as loc_repo

    tasks = task_repo.get_all()
    blocks = block_repo.get_all()
    locations = {loc['id']: loc for loc in loc_repo.get_all()}

    date_map = {}
    for block in blocks:
        block_date = block.get('date', '')
        block_task_id = block.get('task_id', '')
        block_iids = block.get('identifier_ids')
        task = next((t for t in tasks if t['id'] == block_task_id), None)
        if not task:
            continue
        for identifier in task.get('identifiers', []):
            iid = identifier['id'] if isinstance(identifier, dict) else identifier
            if block_iids is None or iid in block_iids:
                if iid not in date_map or block_date < date_map[iid]:
                    date_map[iid] = block_date

    return tasks, locations, date_map


def _build_item_dict(task, identifier, loc_name, scheduled_date):
    iid = identifier['id']
    execution = ExecutionRepository.get_by_identifier(iid)
    return {
        'identifier_id': iid,
        'identifier_name': identifier.get('name', ''),
        'task_id': task['id'],
        'doc_name': task.get('doc_name', ''),
        'assignee_names': task.get('assignee_names', []),
        'estimated_minutes': identifier.get('estimated_minutes', 0),
        'location_id': task.get('location_id', ''),
        'location_name': loc_name,
        'scheduled_date': scheduled_date,
        'execution': _execution_response(execution),
    }


@api_bp.route('/list')
def execution_list():
    date_filter = request.args.get('date', '')
    location_filter = request.args.get('location', '')

    tasks, locations, date_map = _load_schedule_data()
    result = []
    for task in tasks:
        loc_id = task.get('location_id', '')
        loc_name = locations.get(loc_id, {}).get('name', '') if loc_id else ''
        for identifier in task.get('identifiers', []):
            if not isinstance(identifier, dict):
                continue
            iid = identifier['id']
            scheduled_date = date_map.get(iid, '')
            if date_filter and scheduled_date != date_filter:
                continue
            if location_filter and loc_id != location_filter:
                continue
            result.append(_build_item_dict(task, identifier, loc_name, scheduled_date))

    return jsonify(result)


@api_bp.route('/item/<identifier_id>')
def get_item(identifier_id):
    tasks, locations, date_map = _load_schedule_data()
    for task in tasks:
        loc_id = task.get('location_id', '')
        loc_name = locations.get(loc_id, {}).get('name', '') if loc_id else ''
        for identifier in task.get('identifiers', []):
            if not isinstance(identifier, dict):
                continue
            if identifier['id'] != identifier_id:
                continue
            return jsonify(_build_item_dict(task, identifier, loc_name, date_map.get(identifier_id, '')))
    return jsonify({'error': 'not found'}), 404


@api_bp.route('/total-count/<identifier_id>')
def total_count(identifier_id):
    return jsonify({'total_count': _get_total_count(identifier_id)})


@api_bp.route('/whoami')
def whoami():
    return jsonify({'username': session.get('username', '')})


@api_bp.route('/login', methods=['POST'])
def login():
    body = request.get_json(silent=True) or {}
    username = body.get('username', '').strip()
    if not username:
        return jsonify({'error': 'username required'}), 400
    session['username'] = username
    return jsonify({'username': username})


@api_bp.route('/start', methods=['POST'])
def start():
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
                continue
            performer = ex.get('performer', '')
            if performer == current_user:
                return jsonify({'error': '이미 진행 중인 시험이 있습니다.', 'code': 'user_busy'}), 409
            if performer:
                return jsonify({'error': f'"{performer}"님이 시험을 진행 중입니다.', 'code': 'another_user_busy'}), 409

    total = _get_total_count(identifier_id)
    ex = ExecutionRepository.start(identifier_id, task_id, total_count=total)

    if ex and current_user and not ex.get('performer'):
        ExecutionRepository.update_performer(ex['id'], current_user)
        ex['performer'] = current_user

    return jsonify(ex), 201


@api_bp.route('/pause', methods=['POST'])
def pause():
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
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    fail_count = body.get('fail_count', 0)
    block_count = body.get('block_count', 0)
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.complete(execution_id, fail_count, block_count)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404

    elapsed = ExecutionRepository.compute_elapsed_seconds(ex.get('segments', []))
    _notify_timing(ex.get('identifier_id', ''), ex.get('task_id', ''), elapsed)

    return jsonify(ex)


@api_bp.route('/pending-comment', methods=['PUT'])
def pending_comment():
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
    """외부 API로부터 시험 소요시간(초)을 수신해 estimated_minutes를 갱신한다."""
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

            # 선택적 검증
            if body.get('doc_name') and t.get('doc_name') != body['doc_name']:
                return jsonify({'error': 'doc_name mismatch'}), 400
            if body.get('identifier_name') and item.get('name') != body['identifier_name']:
                return jsonify({'error': 'identifier_name mismatch'}), 400

            new_minutes = ceil(int(elapsed_seconds) / 60)
            identifiers = list(t['identifiers'])
            idx = identifiers.index(item)
            identifiers[idx] = {**item, 'estimated_minutes': new_minutes}

            total_minutes = sum(
                i.get('estimated_minutes', 0) for i in identifiers if isinstance(i, dict)
            )
            task_repo.patch(t['id'], identifiers=identifiers, estimated_minutes=total_minutes)
            return jsonify({'ok': True, 'identifier_id': identifier_id, 'estimated_minutes': new_minutes})

    return jsonify({'error': 'identifier not found'}), 404


@api_bp.route('/reset', methods=['POST'])
def reset():
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.reset(execution_id)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(ex)
