"""시험 실행 REST API."""

from flask import request, jsonify

from app.features.execution.models import execution
from app.features.execution.routes.execution_views import execution_bp
from app.features.schedule.models import schedule_block, task, location


def _sync_block_status(block_id):
    """블록 내 모든 식별자의 실행 상태를 기반으로 block_status를 갱신한다."""
    execs = execution.get_by_block(block_id)
    if not execs:
        return

    # 블록에 연결된 태스크의 전체 식별자 수 확인
    block = schedule_block.get_by_id(block_id)
    if not block:
        return
    t = task.get_by_id(block.get('task_id')) if block.get('task_id') else None
    if not t:
        return

    # 이 블록에 할당된 식별자 목록
    block_ids = block.get('identifier_ids')
    if block_ids is None:
        all_ids = [item['id'] if isinstance(item, dict) else item
                   for item in t.get('identifiers', [])]
    else:
        all_ids = block_ids

    # 식별자별 실행 상태 매핑
    exec_map = {}
    for e in execs:
        exec_map[e['identifier_id']] = e['status']

    statuses = [exec_map.get(iid, 'pending') for iid in all_ids]

    if all(s == 'completed' for s in statuses) and statuses:
        new_status = 'completed'
    elif any(s == 'in_progress' for s in statuses):
        new_status = 'in_progress'
    elif any(s == 'completed' for s in statuses):
        new_status = 'in_progress'
    else:
        new_status = 'pending'

    schedule_block.update(block_id, block_status=new_status)


@execution_bp.route('/api/day')
def api_day():
    """당일 실행 현황 — 블록 목록 + 식별자별 실행 기록."""
    date_str = request.args.get('date', '')
    if not date_str:
        from datetime import date as date_cls
        date_str = date_cls.today().isoformat()

    blocks = schedule_block.get_by_date(date_str)
    all_execs = execution.get_all()

    # 실행 기록을 block_id + identifier_id로 빠른 조회
    exec_map = {}
    for e in all_execs:
        key = (e.get('block_id'), e.get('identifier_id'))
        exec_map[key] = e

    locations_all = location.get_all()
    loc_map = {loc['id']: loc['name'] for loc in locations_all}

    result_blocks = []
    total = pending = in_progress = completed = 0
    total_pass = total_fail = 0

    for b in sorted(blocks, key=lambda x: (x.get('start_time', ''), x.get('location_id', ''))):
        if b.get('is_simple'):
            continue

        t = task.get_by_id(b.get('task_id'))
        if not t:
            continue

        # 이 블록의 식별자 목록
        block_ids = b.get('identifier_ids')
        if block_ids is None:
            identifiers = t.get('identifiers', [])
        else:
            id_set = set(block_ids)
            identifiers = [item for item in t.get('identifiers', [])
                          if isinstance(item, dict) and item.get('id') in id_set]

        id_list = []
        for item in identifiers:
            if not isinstance(item, dict):
                continue
            iid = item['id']
            ex = exec_map.get((b['id'], iid))

            id_list.append({
                'id': iid,
                'name': item.get('name', ''),
                'estimated_minutes': item.get('estimated_minutes', 0),
                'owners': item.get('owners', []),
                'execution': ex,
            })

            total += 1
            if ex:
                if ex['status'] == 'completed':
                    completed += 1
                    total_pass += ex.get('pass_count', 0)
                    total_fail += ex.get('fail_count', 0)
                elif ex['status'] == 'in_progress':
                    in_progress += 1
                else:
                    pending += 1
            else:
                pending += 1

        result_blocks.append({
            'block_id': b['id'],
            'task_id': b.get('task_id'),
            'doc_name': t.get('doc_name', ''),
            'start_time': b.get('start_time', ''),
            'end_time': b.get('end_time', ''),
            'location_name': loc_map.get(b.get('location_id', ''), ''),
            'assignee_names': t.get('assignee_names', []),
            'identifiers': id_list,
        })

    return jsonify({
        'date': date_str,
        'blocks': result_blocks,
        'summary': {
            'total': total,
            'pending': pending,
            'in_progress': in_progress,
            'completed': completed,
            'total_pass': total_pass,
            'total_fail': total_fail,
        },
    })


@execution_bp.route('/api/start', methods=['POST'])
def api_start():
    """시험 시작."""
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    for field in ('block_id', 'task_id', 'identifier_id', 'tester_name'):
        if not data.get(field):
            return jsonify({'error': f'{field}은(는) 필수입니다.'}), 400

    # 이미 시작된 식별자인지 확인
    existing = execution.get_by_identifier(data['block_id'], data['identifier_id'])
    if existing:
        return jsonify({'error': '이미 시작된 식별자입니다.'}), 409

    ex = execution.start(
        block_id=data['block_id'],
        task_id=data['task_id'],
        doc_name=data.get('doc_name', ''),
        identifier_id=data['identifier_id'],
        tester_name=data['tester_name'],
    )

    _sync_block_status(data['block_id'])
    return jsonify(ex), 201


@execution_bp.route('/api/complete', methods=['POST'])
def api_complete():
    """결과 입력."""
    data = request.get_json()
    if not data or not data.get('execution_id'):
        return jsonify({'error': 'execution_id는 필수입니다.'}), 400

    ex = execution.complete(
        execution_id=data['execution_id'],
        pass_count=int(data.get('pass_count', 0)),
        fail_count=int(data.get('fail_count', 0)),
    )
    if not ex:
        return jsonify({'error': '실행 기록을 찾을 수 없습니다.'}), 404

    _sync_block_status(ex['block_id'])
    return jsonify(ex)


@execution_bp.route('/api/<execution_id>/comment', methods=['PUT'])
def api_update_comment(execution_id):
    """특이사항/조치사항 수정."""
    data = request.get_json()
    if data is None:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    ex = execution.update_comment(
        execution_id=execution_id,
        comment=data.get('comment', ''),
        action=data.get('action', ''),
    )
    if not ex:
        return jsonify({'error': '실행 기록을 찾을 수 없습니다.'}), 404
    return jsonify(ex)


@execution_bp.route('/api/cancel', methods=['POST'])
def api_cancel():
    """시작 취소."""
    data = request.get_json()
    if not data or not data.get('execution_id'):
        return jsonify({'error': 'execution_id는 필수입니다.'}), 400

    ex = execution.cancel(data['execution_id'])
    if not ex:
        return jsonify({'error': '실행 기록을 찾을 수 없습니다.'}), 404

    _sync_block_status(ex['block_id'])
    return jsonify(ex)
