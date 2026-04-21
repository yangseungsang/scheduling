from flask import Blueprint, jsonify, request

from app.features.execution.models.execution import ExecutionRepository

api_bp = Blueprint('execution_api', __name__, url_prefix='/execution/api')


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
        'pass_count': ex.get('pass_count', 0),
        'comment': ex.get('comment', ''),
    }


@api_bp.route('/list')
def execution_list():
    from app.features.schedule.models import task as task_repo
    from app.features.schedule.models import schedule_block as block_repo
    from app.features.schedule.models import location as loc_repo

    date_filter = request.args.get('date', '')
    location_filter = request.args.get('location', '')

    tasks = task_repo.get_all()
    blocks = block_repo.get_all()
    locations = {loc['id']: loc for loc in loc_repo.get_all()}

    # 식별자 → 가장 이른 배치 날짜 매핑
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

            execution = ExecutionRepository.get_by_identifier(iid)
            result.append({
                'identifier_id': iid,
                'identifier_name': identifier.get('name', ''),
                'task_id': task['id'],
                'doc_name': task.get('doc_name', ''),
                'assignee_names': task.get('assignee_names', []),
                'location_id': loc_id,
                'location_name': loc_name,
                'scheduled_date': scheduled_date,
                'execution': _execution_response(execution),
            })

    return jsonify(result)


@api_bp.route('/total-count/<identifier_id>')
def total_count(identifier_id):
    return jsonify({'total_count': _get_total_count(identifier_id)})


@api_bp.route('/start', methods=['POST'])
def start():
    body = request.get_json(silent=True) or {}
    identifier_id = body.get('identifier_id', '').strip()
    task_id = body.get('task_id', '').strip()
    if not identifier_id or not task_id:
        return jsonify({'error': 'identifier_id and task_id required'}), 400
    total = _get_total_count(identifier_id)
    ex = ExecutionRepository.start(identifier_id, task_id, total_count=total)
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
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.complete(execution_id, fail_count)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404
    return jsonify(ex)


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
