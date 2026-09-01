"""Typed JSON storage facade for execution records."""

from math import ceil

from app.features.execution.domain import ExecutionRun, Executions
from app.repositories import JsonDomainRepository, get_repository


class ExecutionStorage:
    """Adapter between dictionary-based workflows and typed execution records."""

    def __init__(self, repository: JsonDomainRepository):
        """Bind storage to the shared domain repository."""
        self.repository = repository

    def get_all(self):
        """Return every run in the compatibility dictionary shape."""
        return [_run_to_dict(item) for item in self.repository.load_executions().runs]

    def save_all(self, items):
        """Replace all execution records from dictionaries."""
        self.repository.replace_executions(Executions(runs=_runs(items)))

    def update_all(self, operation):
        """Apply a dict-level callback inside a typed repository update."""
        result = []

        def update(executions):
            # 상태 전이 코드는 dict를 사용하지만 저장 경계에서는 domain 타입을 유지한다.
            items = [_run_to_dict(item) for item in executions.runs]
            updated_items = operation(items)
            result.extend(updated_items)
            return Executions(runs=_runs(updated_items))
        self.repository.update_executions(update)
        return result

def _runs(items):
    """Normalize dictionary records into immutable ExecutionRun objects."""
    return tuple(ExecutionRun.from_dict({
            'procedure_id': item.get('procedure_id', ''),
            'test_item_id': item.get('test_item_id', ''),
            'status': item.get('status', 'pending'),
            'started_at': item.get('started_at'),
            'ended_at': item.get('ended_at'),
            'active_started_at': item.get('active_started_at'),
            'actual_seconds': item.get('actual_seconds', 0),
            'total_count': item.get('total_count', 0),
            'fail_count': item.get('fail_count', 0),
            'block_count': item.get('block_count', 0),
            'pass_count': item.get('pass_count', 0),
            'comment': item.get('comment', ''),
            'performer_name': item.get('performer') or item.get('performer_name', ''),
        }) for item in items or [])

def get_execution_storage():
    """Create an execution adapter backed by the current app repository."""
    return ExecutionStorage(get_repository())


def _run_to_dict(run):
    """Expose persisted and calculated timing fields to execution services."""
    elapsed_seconds = run.elapsed_seconds
    return {
        'test_item_id': run.test_item_id,
        'procedure_id': run.procedure_id,
        'status': run.status,
        'started_at': run.started_at,
        'ended_at': run.ended_at,
        'active_started_at': run.active_started_at,
        'actual_seconds': run.actual_seconds,
        'total_count': run.total_count,
        'fail_count': run.fail_count,
        'block_count': run.block_count,
        'pass_count': run.pass_count,
        'comment': run.comment,
        'performer': run.performer_name,
        'created_at': run.started_at,
        'completed_at': run.ended_at,
        'elapsed_seconds': elapsed_seconds,
        'elapsed_mins': ceil(elapsed_seconds / 60) if elapsed_seconds else 0,
    }
