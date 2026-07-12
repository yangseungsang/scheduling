"""Storage adapters for execution records."""

from typing import Protocol

from app.db import Base, create_session_factory, session_scope
from app.db.models import ExamAttempt, ExecutionRun
from app.repositories.orm_file_storage import OrmFileStorage
from app.features.execution.store import generate_id, read_json, write_json

FILENAME = 'executions.json'


class ExecutionStorage(Protocol):
    """Storage contract used by ExecutionRepository."""

    def get_all(self):
        """Return all execution records."""

    def save_all(self, items):
        """Persist all execution records."""

    def generate_id(self, prefix):
        """Generate a new execution record id."""


class JsonExecutionStorage:
    """Execution storage backed by the current JSON file."""

    def get_all(self):
        return read_json(FILENAME)

    def save_all(self, items):
        write_json(FILENAME, items)

    def generate_id(self, prefix):
        return generate_id(prefix)


class OrmExecutionStorage:
    """Execution storage backed by the transitional ORM payload table."""

    def __init__(self, database_url, sync_compact=False):
        self.database_url = database_url
        self.sync_compact = sync_compact
        self.storage = OrmFileStorage(database_url, area='execution')

    def get_all(self):
        return self.storage.get_payload(FILENAME, [])

    def save_all(self, items):
        self.storage.save_payload(FILENAME, items)
        self._sync_compact()

    def generate_id(self, prefix):
        return generate_id(prefix)

    def _sync_compact(self):
        if not self.sync_compact:
            return
        from app.db.repository import CompactSnapshotOrmRepository
        from app.features.schedule.repositories import OrmScheduleStorage
        from app.services.compact_snapshot_storage import build_snapshot_from_legacy_storage

        schedule_storage = OrmScheduleStorage(self.database_url, sync_compact=False)
        snapshot = build_snapshot_from_legacy_storage(schedule_storage, self)
        CompactSnapshotOrmRepository(self.database_url).replace_executions(snapshot['executions'])


class CompactOrmExecutionStorage:
    """Execution storage backed directly by compact ORM execution_runs."""

    def __init__(self, database_url):
        self.database_url = database_url
        self.session_factory, self.engine = create_session_factory(database_url)
        Base.metadata.create_all(self.engine)

    def get_all(self):
        with self.session_factory() as session:
            rows = (
                session.query(ExecutionRun, ExamAttempt)
                .join(ExamAttempt, ExecutionRun.exam_attempt_id == ExamAttempt.id)
                .order_by(ExecutionRun.id)
            )
            return [
                _run_to_legacy_execution(run, attempt)
                for run, attempt in rows
            ]

    def save_all(self, items):
        with session_scope(self.session_factory) as session:
            session.query(ExecutionRun).delete()
            attempts = _attempt_lookup(session)
            for item in items or []:
                attempt = attempts.get((item.get('task_id', ''), item.get('identifier_id', '')))
                if attempt is None:
                    continue
                session.add(_legacy_execution_to_run(item, attempt.id))

    def generate_id(self, prefix):
        return generate_id(prefix)


def execution_storage_from_config(config):
    """Create the configured execution storage adapter."""
    source = config.get('EXECUTION_STORAGE', 'json')
    if source == 'json':
        return JsonExecutionStorage()
    if source == 'orm':
        return OrmExecutionStorage(
            config['DATABASE_URL'],
            sync_compact=config.get('SYNC_COMPACT_ON_ORM_STORAGE_WRITE', True),
        )
    if source == 'compact_orm':
        return CompactOrmExecutionStorage(config['DATABASE_URL'])
    raise ValueError(f'Unsupported EXECUTION_STORAGE: {source}')


def _attempt_lookup(session):
    return {
        (item.legacy_task_id, item.legacy_identifier_id): item
        for item in session.query(ExamAttempt)
    }


def _run_to_legacy_execution(run, attempt):
    return {
        'id': run.id,
        'legacy_execution_id': run.legacy_execution_id,
        'identifier_id': attempt.legacy_identifier_id,
        'task_id': attempt.legacy_task_id,
        'exam_no': attempt.exam_no,
        'status': run.status,
        'segments': list(run.segments or []),
        'total_count': int(run.total_count or 0),
        'fail_count': int(run.fail_count or 0),
        'block_count': int(run.block_count or 0),
        'pass_count': int(run.pass_count or 0),
        'comment': run.comment,
        'performer': run.performer_name,
        'created_at': run.created_at,
        'completed_at': run.completed_at,
        'elapsed_seconds': int(run.elapsed_seconds_snapshot or 0),
        'elapsed_mins': int(run.elapsed_mins_snapshot or 0),
    }


def _legacy_execution_to_run(item, attempt_id):
    return ExecutionRun(
        id=item['id'],
        legacy_execution_id=item.get('legacy_execution_id', item.get('id', '')),
        exam_attempt_id=attempt_id,
        status=item.get('status', 'pending'),
        segments=list(item.get('segments', [])),
        total_count=int(item.get('total_count') or 0),
        fail_count=int(item.get('fail_count') or 0),
        block_count=int(item.get('block_count') or 0),
        pass_count=int(item.get('pass_count') or 0),
        comment=item.get('comment', ''),
        performer_name=item.get('performer') or item.get('performer_name', ''),
        created_at=item.get('created_at'),
        completed_at=item.get('completed_at'),
        elapsed_seconds_snapshot=int(item.get('elapsed_seconds') or 0),
        elapsed_mins_snapshot=int(item.get('elapsed_mins') or 0),
    )
