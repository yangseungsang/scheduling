"""Read services for execution list and detail responses."""

from collections import defaultdict
from datetime import date, timedelta

from app.repositories import get_repository
from app.services.read_models import build_execution_list_items


def build_daily_procedure_metrics(start_date='', end_date=''):
    """Aggregate planned and current execution outcomes by unique procedure ID."""
    repository = get_repository()
    plan = repository.load_plan()
    executions = repository.load_executions()

    planned = defaultdict(set)
    started = defaultdict(set)
    completed = defaultdict(set)
    failed = defaultdict(set)
    blocked = defaultdict(set)

    for block in plan.schedule.blocks:
        if block.procedure_id and block.date:
            planned[block.date].add(block.procedure_id)

    runs_by_procedure = defaultdict(list)
    for run in executions.runs:
        runs_by_procedure[run.procedure_id].append(run)

    for procedure in plan.test_procedures:
        procedure_runs = runs_by_procedure.get(procedure.id, [])
        started_dates = [
            _date_part(run.started_at)
            for run in procedure_runs
            if run.status != 'pending' and _date_part(run.started_at)
        ]
        if started_dates:
            started[min(started_dates)].add(procedure.id)

        # 호출 시점에 완료 상태인 실행 항목이 하나라도 있으면 해당 절차서를
        # 실제 수행한 것으로 본다. 아직 배치·실행하지 않은 형제 항목 때문에
        # 이미 끝낸 procedure_id가 집계에서 누락되지 않도록 한다.
        completed_runs = [
            run for run in procedure_runs
            if run.status == 'completed' and _date_part(run.ended_at)
        ]
        if not completed_runs:
            continue
        completion_date = max(_date_part(run.ended_at) for run in completed_runs)
        completed[completion_date].add(procedure.id)
        if any(run.fail_count > 0 for run in completed_runs):
            failed[completion_date].add(procedure.id)
        if any(run.block_count > 0 for run in completed_runs):
            blocked[completion_date].add(procedure.id)

    available_dates = set().union(planned, started, completed, failed, blocked)
    range_start = start_date or (min(available_dates) if available_dates else '')
    range_end = end_date or (max(available_dates) if available_dates else '')
    if range_start and range_end and range_start > range_end:
        raise ValueError('시작일은 종료일보다 늦을 수 없습니다.')

    days = []
    if range_start and range_end:
        current = date.fromisoformat(range_start)
        last = date.fromisoformat(range_end)
        while current <= last:
            value = current.isoformat()
            fail_ids = failed[value]
            block_ids = blocked[value]
            days.append({
                'date': value,
                'planned_count': len(planned[value]),
                'started_count': len(started[value]),
                'completed_count': len(completed[value]),
                'failed_count': len(fail_ids),
                'blocked_count': len(block_ids),
                'failed_or_blocked_count': len(fail_ids | block_ids),
                'planned_procedure_ids': sorted(planned[value]),
                'started_procedure_ids': sorted(started[value]),
                'completed_procedure_ids': sorted(completed[value]),
                'failed_procedure_ids': sorted(fail_ids),
                'blocked_procedure_ids': sorted(block_ids),
            })
            current += timedelta(days=1)

    return {
        'start_date': range_start,
        'end_date': range_end,
        'days': days,
        'summary': {
            'planned_count': sum(item['planned_count'] for item in days),
            'started_count': sum(item['started_count'] for item in days),
            'completed_count': sum(item['completed_count'] for item in days),
            'failed_count': sum(item['failed_count'] for item in days),
            'blocked_count': sum(item['blocked_count'] for item in days),
        },
    }


def _date_part(value):
    """Return the ISO date portion of a stored datetime string."""
    return str(value)[:10] if value else ''


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
    repository = get_repository()
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
