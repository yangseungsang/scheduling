"""Read services for execution list and detail responses."""

from flask import current_app

from app.repositories import JsonDomainRepository
from app.services.read_models import build_execution_list_items


def build_execution_items(
    date_filter='', location_filter='', status_filter='', procedure_filter='',
):
    """Return execution list items from the shared typed JSON domain."""
    return _execution_items(
        date_filter, location_filter, status_filter, procedure_filter,
    )


def build_execution_item(test_item_id, procedure_id_filter=''):
    """Return one execution item or None when it does not exist."""
    for item in _execution_items():
        if item.get('test_item_id') != test_item_id:
            continue
        if procedure_id_filter and item.get('procedure_id') != procedure_id_filter:
            continue
        return item
    return None


def get_total_count(test_item_id, procedure_id=''):
    """Return the total test count stored in synced test_item data."""
    for item in _execution_items():
        if item.get('test_item_id') != test_item_id:
            continue
        if procedure_id and item.get('procedure_id') != procedure_id:
            continue
        return item.get('total_count', 0)
    return 0


def _result_counts(execution, fallback_total):
    """Build pass/fail/block counts with a procedure item total fallback."""
    return {
        'fail_count': execution.get('fail_count', 0) if execution else 0,
        'block_count': execution.get('block_count', 0) if execution else 0,
        'pass_count': execution.get('pass_count', 0) if execution else 0,
        'total_count': execution.get('total_count', fallback_total) if execution else fallback_total,
    }


def _status_order(status):
    """Return the stable UI sort order for execution states."""
    return {
        'pending': 0,
        'in_progress': 1,
        'paused': 2,
        'completed': 3,
    }.get(status, 0)


def _execution_items(
    date_filter='', location_filter='', status_filter='', procedure_filter='',
):
    """Join plan and execution data, then apply list filters."""
    repository = JsonDomainRepository(current_app.config['DOMAIN_DATA_DIR'])
    plan = repository.load_plan()
    procedures = plan.test_procedures
    schedule = plan.schedule
    executions = repository.load_executions()
    rows = build_execution_list_items(
        procedures, schedule, executions,
    )
    runs = {
        (item.procedure_id, item.test_item_id): item
        for item in executions.runs
    }
    procedures_by_id = {item.id: item for item in procedures}
    result = []
    for row in rows:
        if not _matches_filter(row.get('procedure_id'), procedure_filter):
            continue
        if not _matches_filter(row.get('scheduled_date'), date_filter):
            continue
        if not _matches_filter(row.get('location_name'), location_filter):
            continue
        procedure = procedures_by_id.get(row.get('procedure_id'))
        run = runs.get((row.get('procedure_id'), row.get('test_item_id')))
        execution_payload = _execution_response(run)
        actual_start_at, actual_end_at = _actual_period(run)
        total_count = row.get('total_count', 0)
        status = row.get('execution_status', 'pending')
        if not _matches_filter(status, status_filter):
            continue
        item = {
            'test_item_id': row.get('test_item_id', ''),
            'test_item_name': row.get('test_name', ''),
            'procedure_id': row.get('procedure_id', ''),
            'test_round': row.get('test_round'),
            'document_name': row.get('document_name', ''),
            'display_name': row.get('display_name', ''),
            'assignee_names': list(procedure.assignee_names) if procedure else [],
            'owners': list(row.get('owner_names', [])),
            'estimated_minutes': row.get('estimated_minutes', 0),
            'location_name': row.get('location_name', ''),
            'scheduled_date': row.get('scheduled_date', ''),
            'scheduled_start_time': row.get('scheduled_start_time', ''),
            'scheduled_end_time': row.get('scheduled_end_time', ''),
            'actual_start_at': actual_start_at,
            'actual_end_at': actual_end_at,
            'display_date': actual_end_at or row.get('scheduled_date', ''),
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


def _actual_period(run):
    """Return a concise actual start/end period for list display."""
    if not run:
        return '', ''
    return run.started_at or '', run.ended_at or ''


def _matches_filter(value, selected):
    """Treat an empty selected list as an unrestricted filter."""
    if isinstance(selected, str):
        selected = [selected] if selected else []
    selected = {item for item in (selected or []) if item}
    return not selected or value in selected


def _execution_response(run):
    """Normalize a stored execution dict for API responses."""
    if not run:
        return None
    return {
        'status': run.status,
        'elapsed_seconds': run.elapsed_seconds,
        'total_count': run.total_count,
        'fail_count': run.fail_count,
        'block_count': run.block_count,
        'pass_count': run.pass_count,
        'comment': run.comment,
        'performer': run.performer_name,
        'started_at': run.started_at,
        'ended_at': run.ended_at,
        'completed_at': run.ended_at if run.status == 'completed' else None,
    }
