"""Procedure 중심 데이터 조합 서비스.

Schedule과 Execution은 아직 기존 JSON 파일을 사용하지만, feature가 서로의
repository를 직접 조합하지 않도록 공통 Procedure 관점의 조회 함수를 제공한다.
"""

from math import ceil


class ProcedureServiceError(Exception):
    """Procedure 서비스 처리 중 API 응답으로 변환 가능한 오류."""

    status_code = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ProcedureNotFoundError(ProcedureServiceError):
    status_code = 404


def _execution_repository():
    from app.features.execution.models.execution import ExecutionRepository

    return ExecutionRepository


def _schedule_repositories():
    from app.features.schedule.models import location, schedule_block, task

    return task, schedule_block, location


def identifier_total_count(identifier):
    """식별자 데이터에 저장된 전체 시험 건수를 반환한다."""
    for key in ('total_count', 'pf_num', 'test_count', 'case_count', 'count'):
        value = identifier.get(key)
        if value in (None, ''):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def execution_response(execution):
    """실행 레코드를 화면/API 응답용 dict로 변환한다."""
    if execution is None:
        return None
    execution_repo = _execution_repository()
    return {
        'id': execution['id'],
        'status': execution['status'],
        'elapsed_seconds': execution_repo.compute_elapsed_seconds(
            execution.get('segments', [])
        ),
        'total_count': execution.get('total_count', 0),
        'fail_count': execution.get('fail_count', 0),
        'block_count': execution.get('block_count', 0),
        'pass_count': execution.get('pass_count', 0),
        'comment': execution.get('comment', ''),
        'performer': execution.get('performer', ''),
        'completed_at': execution.get('completed_at'),
    }


def execution_status_map():
    """(identifier_id, task_id) -> execution status 맵을 반환한다."""
    execution_repo = _execution_repository()
    return {
        (ex['identifier_id'], ex.get('task_id', '')): ex.get('status', 'pending')
        for ex in execution_repo.get_all()
    }


def execution_map():
    """(identifier_id, task_id) -> execution dict 맵을 반환한다."""
    execution_repo = _execution_repository()
    return {
        (ex['identifier_id'], ex.get('task_id', '')): ex
        for ex in execution_repo.get_all()
    }


def reset_execution_records():
    """Execution 저장 파일을 비운다."""
    from app.features.execution.store import write_json

    write_json('executions.json', [])


def schedule_snapshot():
    """기능 간 공유용 schedule 원천 데이터 스냅샷을 반환한다."""
    from app.features.schedule.models import user, version

    tasks, blocks, locations, _ = _schedule_maps()
    return {
        'tasks': tasks,
        'schedule_blocks': blocks,
        'users': user.get_all(),
        'locations': list(locations.values()),
        'versions': version.get_all(),
    }


def execution_snapshot():
    """기능 간 공유용 execution 원천 데이터 스냅샷을 반환한다."""
    execution_repo = _execution_repository()
    return {
        'executions': execution_repo.get_all(),
    }


def feature_snapshot():
    """schedule/execution 원천 데이터와 조합 item을 함께 반환한다."""
    return {
        'schedule': schedule_snapshot(),
        'execution': execution_snapshot(),
        'procedure_items': execution_items(),
    }


def _schedule_maps():
    task, schedule_block, location = _schedule_repositories()
    tasks = task.get_all()
    blocks = schedule_block.get_all()
    locations = {loc['id']: loc for loc in location.get_all()}
    tasks_by_id = {item['id']: item for item in tasks}
    return tasks, blocks, locations, tasks_by_id


def schedule_context():
    """실행 목록 구성에 필요한 Procedure 스케줄 컨텍스트를 반환한다."""
    tasks, blocks, locations, tasks_by_id = _schedule_maps()
    date_map = {}
    block_loc_map = {}

    for block in blocks:
        block_date = block.get('date', '')
        block_task_id = block.get('task_id', '')
        block_iids = block.get('identifier_ids')
        block_loc = block.get('location_id', '')
        task_dict = tasks_by_id.get(block_task_id)
        if not task_dict:
            continue

        for identifier in task_dict.get('identifiers', []):
            iid = identifier['id'] if isinstance(identifier, dict) else identifier
            if block_iids is not None and iid not in block_iids:
                continue

            key = (block_task_id, iid)
            if key not in date_map or block_date < date_map[key]:
                date_map[key] = block_date
                if block_loc:
                    block_loc_map[key] = block_loc

    return {
        'tasks': tasks,
        'locations': locations,
        'date_map': date_map,
        'block_loc_map': block_loc_map,
    }


def build_execution_item(task_dict, identifier, context):
    """태스크, 식별자, 계획, 실행 데이터를 하나의 item으로 조합한다."""
    iid = identifier['id']
    task_id = task_dict['id']
    key = (task_id, iid)
    block_loc_id = context['block_loc_map'].get(key, '')
    loc_id = block_loc_id or task_dict.get('location_id', '')
    loc_name = context['locations'].get(loc_id, {}).get('name', '') if loc_id else ''
    execution_repo = _execution_repository()
    execution = execution_repo.get_by_identifier_and_task(iid, task_id)
    completed_at = execution.get('completed_at') if execution else None
    exam_no = task_dict.get('exam_no')
    doc_name = task_dict.get('doc_name', '')
    display_name = (
        f'{doc_name} ({exam_no}차)'
        if exam_no is not None and exam_no != 1
        else doc_name
    )

    return {
        'identifier_id': iid,
        'identifier_name': identifier.get('name', ''),
        'task_id': task_id,
        'exam_no': exam_no,
        'doc_name': doc_name,
        'display_name': display_name,
        'assignee_names': task_dict.get('assignee_names', []),
        'owners': identifier.get('owners', []),
        'estimated_minutes': identifier.get('estimated_minutes', 0),
        'location_id': loc_id,
        'location_name': loc_name,
        'scheduled_date': context['date_map'].get(key, ''),
        'display_date': completed_at or context['date_map'].get(key, ''),
        'total_count': identifier_total_count(identifier),
        'execution': execution_response(execution),
    }


def execution_items(date_filter='', location_filter=''):
    """실행 목록 API가 사용할 Procedure item 목록을 반환한다."""
    context = schedule_context()
    result = []
    for task_dict in context['tasks']:
        for identifier in task_dict.get('identifiers', []):
            if not isinstance(identifier, dict):
                continue
            item = build_execution_item(task_dict, identifier, context)
            if date_filter and item['scheduled_date'] != date_filter:
                continue
            if location_filter and item['location_id'] != location_filter:
                continue
            result.append(item)
    return result


def find_execution_item(identifier_id, task_id=''):
    """identifier_id와 선택적 task_id로 실행 item을 찾는다."""
    context = schedule_context()
    for task_dict in context['tasks']:
        if task_id and task_dict['id'] != task_id:
            continue
        for identifier in task_dict.get('identifiers', []):
            if not isinstance(identifier, dict):
                continue
            if identifier.get('id') == identifier_id:
                return build_execution_item(task_dict, identifier, context)
    return None


def total_count(identifier_id, task_id=''):
    """식별자 전체 시험 건수를 task 범위 안에서 찾는다."""
    task, _, _ = _schedule_repositories()
    for task_dict in task.get_all():
        if task_id and task_dict.get('id') != task_id:
            continue
        for identifier in task_dict.get('identifiers', []):
            if isinstance(identifier, dict) and identifier.get('id') == identifier_id:
                return identifier_total_count(identifier)
    return 0


def task_version_id(task_id):
    """task_id에 연결된 version_id를 반환한다."""
    task, _, _ = _schedule_repositories()
    task_dict = task.get_by_id(task_id)
    return task_dict.get('version_id', '') if task_dict else ''


def task_exam_round(task_id):
    """task_id에 연결된 exam_no를 반환한다."""
    task, _, _ = _schedule_repositories()
    task_dict = task.get_by_id(task_id)
    return task_dict.get('exam_no') if task_dict else None


def execution_filter_context():
    """Execution 목록 화면의 장소/날짜 필터 데이터를 반환한다."""
    _, schedule_block, location = _schedule_repositories()
    blocks = schedule_block.get_all()
    return {
        'locations': location.get_all(),
        'dates': sorted({block['date'] for block in blocks if block.get('date')}),
    }


def update_identifier_elapsed(identifier_id, elapsed_seconds, doc_name='', identifier_name=''):
    """외부 timing 입력으로 식별자 예상 시간을 갱신한다."""
    task, _, _ = _schedule_repositories()
    for task_dict in task.get_all():
        for item in task_dict.get('identifiers', []):
            if not isinstance(item, dict) or item.get('id') != identifier_id:
                continue
            if doc_name and task_dict.get('doc_name') != doc_name:
                raise ProcedureServiceError('doc_name mismatch')
            if identifier_name and item.get('name') != identifier_name:
                raise ProcedureServiceError('identifier_name mismatch')

            new_minutes = ceil(int(elapsed_seconds) / 60)
            identifiers = list(task_dict['identifiers'])
            idx = identifiers.index(item)
            identifiers[idx] = {**item, 'estimated_minutes': new_minutes}
            total_minutes = sum(
                i.get('estimated_minutes', 0)
                for i in identifiers
                if isinstance(i, dict)
            )
            task.patch(
                task_dict['id'],
                identifiers=identifiers,
                estimated_minutes=total_minutes,
            )
            return {'identifier_id': identifier_id, 'estimated_minutes': new_minutes}

    raise ProcedureNotFoundError('identifier not found')
