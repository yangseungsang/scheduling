"""Read services for execution list and detail responses."""

from flask import current_app

from app.db.repository import CompactSnapshotOrmRepository
from app.features.execution.models.execution import ExecutionRepository
from app.services.read_models import build_execution_list_items


def build_execution_items(date_filter='', location_filter=''):
    """Return execution list items for the current legacy data store."""
    if _use_compact_orm_schedule():
        return _compact_execution_items(date_filter, location_filter)

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
            loc_id = block_loc_id or task.get('location_id', '')
            if date_filter and scheduled_date != date_filter:
                continue
            if location_filter and loc_id != location_filter:
                continue
            result.append(_build_item_dict(task, identifier, locations, scheduled_date, block_loc_id))
    return result


def build_execution_item(identifier_id, task_id_filter=''):
    """Return one execution item or None when it does not exist."""
    if _use_compact_orm_schedule():
        for item in _compact_execution_items():
            if item.get('identifier_id') != identifier_id:
                continue
            if task_id_filter and item.get('task_id') != task_id_filter:
                continue
            return item
        return None

    tasks, locations, date_map, block_loc_map = _load_schedule_data()
    for task in tasks:
        if task_id_filter and task['id'] != task_id_filter:
            continue
        for identifier in task.get('identifiers', []):
            if not isinstance(identifier, dict):
                continue
            if identifier['id'] != identifier_id:
                continue
            return _build_item_dict(
                task,
                identifier,
                locations,
                date_map.get((task['id'], identifier_id), ''),
                block_loc_map.get((task['id'], identifier_id), ''),
            )
    return None


def get_total_count(identifier_id, task_id=''):
    """Return the total test count stored in synced identifier data."""
    if _use_compact_orm_schedule():
        for item in _compact_execution_items():
            if item.get('identifier_id') != identifier_id:
                continue
            if task_id and item.get('task_id') != task_id:
                continue
            return item.get('total_count', 0)
        return 0

    from app.features.schedule.models import task as task_repo

    for task in task_repo.get_all():
        if task_id and task.get('id') != task_id:
            continue
        for identifier in task.get('identifiers', []):
            if isinstance(identifier, dict) and identifier.get('id') == identifier_id:
                return _identifier_total_count(identifier)
    return 0


def _identifier_total_count(identifier):
    for key in ('total_count', 'pf_num', 'test_count', 'case_count', 'count'):
        value = identifier.get(key)
        if value in (None, ''):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _execution_response(execution):
    if execution is None:
        return None
    return {
        'id': execution['id'],
        'status': execution['status'],
        'elapsed_seconds': ExecutionRepository.compute_elapsed_seconds(
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


def _load_schedule_data():
    from app.features.schedule.models import location as loc_repo
    from app.features.schedule.models import schedule_block as block_repo
    from app.features.schedule.models import task as task_repo

    tasks = task_repo.get_all()
    blocks = block_repo.get_all()
    locations = {loc['id']: loc for loc in loc_repo.get_all()}

    date_map = {}
    block_loc_map = {}

    for block in blocks:
        block_date = block.get('date', '')
        block_task_id = block.get('task_id', '')
        block_iids = block.get('identifier_ids')
        block_loc = block.get('location_id', '')
        task = next((item for item in tasks if item['id'] == block_task_id), None)
        if not task:
            continue
        for identifier in task.get('identifiers', []):
            iid = identifier['id'] if isinstance(identifier, dict) else identifier
            if block_iids is None or iid in block_iids:
                key = (block_task_id, iid)
                if key not in date_map or block_date < date_map[key]:
                    date_map[key] = block_date
                    if block_loc:
                        block_loc_map[key] = block_loc

    return tasks, locations, date_map, block_loc_map


def _build_item_dict(task, identifier, locations, scheduled_date, block_loc_id=''):
    iid = identifier['id']
    loc_id = block_loc_id or task.get('location_id', '')
    loc_name = locations.get(loc_id, {}).get('name', '') if loc_id else ''
    execution = ExecutionRepository.get_by_identifier_and_task(iid, task['id'])
    execution_payload = _execution_response(execution)
    completed_at = execution.get('completed_at') if execution else None
    exam_no = task.get('exam_no')
    doc_name = task.get('doc_name', '')
    display_name = (
        f'{doc_name} ({exam_no}차)'
        if exam_no is not None and exam_no != 1
        else doc_name
    )
    total_count = _identifier_total_count(identifier)
    status = execution_payload.get('status') if execution_payload else 'pending'
    result_counts = _result_counts(execution_payload, total_count)
    return {
        'identifier_id': iid,
        'identifier_name': identifier.get('name', ''),
        'task_id': task['id'],
        'exam_no': exam_no,
        'doc_name': doc_name,
        'display_name': display_name,
        'assignee_names': task.get('assignee_names', []),
        'owners': identifier.get('owners', []),
        'estimated_minutes': identifier.get('estimated_minutes', 0),
        'location_id': loc_id,
        'location_name': loc_name,
        'scheduled_date': scheduled_date,
        'display_date': completed_at or scheduled_date,
        'total_count': total_count,
        'execution_status': status,
        'execution_comment': execution_payload.get('comment', '') if execution_payload else '',
        'elapsed_seconds': execution_payload.get('elapsed_seconds', 0) if execution_payload else 0,
        'performer_name': execution_payload.get('performer', '') if execution_payload else '',
        'result_counts': result_counts,
        'status_order': _status_order(status),
        'execution': execution_payload,
    }


def _result_counts(execution, fallback_total):
    return {
        'fail_count': execution.get('fail_count', 0) if execution else 0,
        'block_count': execution.get('block_count', 0) if execution else 0,
        'pass_count': execution.get('pass_count', 0) if execution else 0,
        'total_count': execution.get('total_count', fallback_total) if execution else fallback_total,
    }


def _status_order(status):
    return {
        'pending': 0,
        'in_progress': 1,
        'paused': 2,
        'completed': 3,
    }.get(status, 0)


def _use_compact_orm_schedule():
    return current_app.config.get('SCHEDULE_STORAGE') == 'compact_orm'


def _compact_snapshot():
    return CompactSnapshotOrmRepository(current_app.config['DATABASE_URL']).load_snapshot()


def _compact_execution_items(date_filter='', location_filter=''):
    snapshot = _compact_snapshot()
    rows = build_execution_list_items(snapshot, date_filter, location_filter)
    attempts = {
        item['id']: item
        for item in snapshot.get('catalog', {}).get('exam_attempts', [])
    }
    runs = {
        item.get('exam_attempt_id'): item
        for item in snapshot.get('executions', {}).get('runs', [])
    }
    result = []
    for row in rows:
        attempt = attempts.get(row.get('exam_attempt_id'), {})
        run = runs.get(row.get('exam_attempt_id'))
        execution_payload = _compact_execution_response(run)
        total_count = row.get('total_count', 0)
        status = row.get('execution_status', 'pending')
        item = {
            'identifier_id': row.get('external_test_id', ''),
            'identifier_name': row.get('test_name', ''),
            'task_id': attempt.get('legacy_task_id', ''),
            'exam_no': row.get('exam_no'),
            'doc_name': row.get('doc_name', ''),
            'display_name': row.get('display_name', ''),
            'assignee_names': list(attempt.get('default_assignee_names', [])),
            'owners': list(row.get('owner_names', [])),
            'estimated_minutes': row.get('estimated_minutes', 0),
            'location_id': row.get('location_id', ''),
            'location_name': row.get('location_name', ''),
            'scheduled_date': row.get('scheduled_date', ''),
            'display_date': (run or {}).get('completed_at') or row.get('scheduled_date', ''),
            'total_count': total_count,
            'execution_status': status,
            'execution_comment': row.get('comment', ''),
            'elapsed_seconds': row.get('elapsed_seconds', 0),
            'performer_name': row.get('performer_name', ''),
            'result_counts': _result_counts(execution_payload, total_count),
            'status_order': _status_order(status),
            'execution': execution_payload,
        }
        result.append(item)
    return result


def _compact_execution_response(run):
    if not run:
        return None
    elapsed_seconds = ExecutionRepository.compute_elapsed_seconds(run.get('segments', []))
    return {
        'id': run.get('id', ''),
        'status': run.get('status', 'pending'),
        'elapsed_seconds': elapsed_seconds,
        'total_count': run.get('total_count', 0),
        'fail_count': run.get('fail_count', 0),
        'block_count': run.get('block_count', 0),
        'pass_count': run.get('pass_count', 0),
        'comment': run.get('comment', ''),
        'performer': run.get('performer_name', ''),
        'completed_at': run.get('completed_at'),
    }
