"""Repository for compact snapshots backed by SQLAlchemy ORM models."""

from copy import deepcopy

from app.db import Base, create_session_factory, session_scope
from app.db.models import (
    AppSettings,
    BlockItem,
    ExamAttempt,
    ExecutionRun,
    MigrationWarning,
    ResourceRecord,
    ScheduleBlock,
    SnapshotSync,
    SourceDocument,
    TestItem,
)
from app.services.compact_migration import SCHEMA_VERSION


class CompactSnapshotOrmRepository:
    """Read and replace compact snapshots in a relational database."""

    def __init__(self, database_url, session_factory=None, engine=None):
        self.database_url = database_url
        if session_factory is None:
            session_factory, engine = create_session_factory(database_url)
        self.session_factory = session_factory
        self.engine = engine

    def create_schema(self, drop_existing=False):
        if drop_existing:
            Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)

    def replace_snapshot(self, snapshot):
        """Replace all compact tables with one complete snapshot."""
        with session_scope(self.session_factory) as session:
            self._clear(session)
            self._insert_snapshot(session, snapshot)

    def replace_catalog_schedule_executions(self, snapshot):
        """Replace compact catalog, schedule, and execution tables together."""
        self.create_schema()
        with session_scope(self.session_factory) as session:
            self._clear_sections(session, ('catalog', 'schedule', 'executions'))
            self._insert_catalog(session, snapshot.get('catalog', {}))
            self._insert_schedule(session, snapshot.get('schedule', {}))
            self._insert_executions(session, snapshot.get('executions', {}))

    def replace_schedule(self, schedule):
        """Replace compact schedule tables without touching catalog/resources."""
        self.create_schema()
        with session_scope(self.session_factory) as session:
            self._clear_sections(session, ('schedule',))
            self._insert_schedule(session, schedule)

    def replace_executions(self, executions):
        """Replace compact execution tables without touching catalog/schedule."""
        self.create_schema()
        with session_scope(self.session_factory) as session:
            self._clear_sections(session, ('executions',))
            self._insert_executions(session, executions)

    def replace_resources(self, kind, items):
        """Replace one resource collection in compact ORM tables."""
        self.create_schema()
        with session_scope(self.session_factory) as session:
            session.query(ResourceRecord).filter_by(kind=kind).delete()
            for item in items or []:
                session.add(ResourceRecord(
                    kind=kind,
                    id=str(item.get('id', '')),
                    payload=deepcopy(item),
                ))

    def replace_settings(self, settings):
        """Replace compact settings without rebuilding the whole snapshot."""
        self.create_schema()
        with session_scope(self.session_factory) as session:
            row = session.get(AppSettings, 'current')
            payload = _settings_payload(settings)
            if row is None:
                session.add(AppSettings(id='current', payload=payload))
            else:
                row.payload = payload

    def load_snapshot(self):
        """Load the database state as the compact snapshot contract."""
        with self.session_factory() as session:
            sync = session.get(SnapshotSync, 'current')
            settings = session.get(AppSettings, 'current')
            return {
                'catalog': {
                    'schema_version': sync.schema_version if sync else SCHEMA_VERSION,
                    'documents': [
                        _document_to_dict(item)
                        for item in session.query(SourceDocument).order_by(SourceDocument.id)
                    ],
                    'test_items': [
                        _test_item_to_dict(item)
                        for item in session.query(TestItem).order_by(TestItem.id)
                    ],
                    'exam_attempts': [
                        _attempt_to_dict(item)
                        for item in session.query(ExamAttempt).order_by(ExamAttempt.id)
                    ],
                    'sync': {
                        'provider': sync.provider if sync else '',
                        'updated_at': sync.updated_at if sync else '',
                        'data_hash': sync.data_hash if sync else '',
                    },
                    'migration': {
                        'warnings': self._warnings(session, 'catalog'),
                    },
                },
                'schedule': {
                    'schema_version': sync.schema_version if sync else SCHEMA_VERSION,
                    'blocks': [
                        _block_to_dict(item)
                        for item in session.query(ScheduleBlock).order_by(
                            ScheduleBlock.date,
                            ScheduleBlock.start_time,
                            ScheduleBlock.id,
                        )
                    ],
                    'block_items': [
                        _block_item_to_dict(item)
                        for item in session.query(BlockItem).order_by(
                            BlockItem.block_id,
                            BlockItem.sort_order,
                            BlockItem.id,
                        )
                    ],
                    'migration': {
                        'warnings': self._warnings(session, 'schedule'),
                    },
                },
                'executions': {
                    'schema_version': sync.schema_version if sync else SCHEMA_VERSION,
                    'runs': [
                        _run_to_dict(item)
                        for item in session.query(ExecutionRun).order_by(ExecutionRun.id)
                    ],
                    'migration': {
                        'warnings': self._warnings(session, 'executions'),
                    },
                },
                'resources': {
                    'schema_version': sync.schema_version if sync else SCHEMA_VERSION,
                    'users': self._resource_payloads(session, 'users'),
                    'locations': self._resource_payloads(session, 'locations'),
                    'versions': self._resource_payloads(session, 'versions'),
                },
                'settings': _settings_payload(settings.payload if settings else None),
            }

    def _clear(self, session):
        for model in (
            MigrationWarning,
            ExecutionRun,
            BlockItem,
            ScheduleBlock,
            ExamAttempt,
            TestItem,
            SourceDocument,
            ResourceRecord,
            AppSettings,
            SnapshotSync,
        ):
            session.query(model).delete()

    def _clear_sections(self, session, sections):
        sections = set(sections)
        if 'executions' in sections:
            session.query(ExecutionRun).delete()
            self._clear_warnings(session, ('executions',))
        if 'schedule' in sections:
            session.query(BlockItem).delete()
            session.query(ScheduleBlock).delete()
            self._clear_warnings(session, ('schedule',))
        if 'catalog' in sections:
            session.query(ExecutionRun).delete()
            session.query(BlockItem).delete()
            session.query(ExamAttempt).delete()
            session.query(TestItem).delete()
            session.query(SourceDocument).delete()
            session.query(SnapshotSync).delete()
            self._clear_warnings(session, ('catalog', 'schedule', 'executions'))

    def _clear_warnings(self, session, sources):
        session.query(MigrationWarning).filter(MigrationWarning.source.in_(sources)).delete()

    def _insert_snapshot(self, session, snapshot):
        catalog = snapshot.get('catalog', {})
        schedule = snapshot.get('schedule', {})
        executions = snapshot.get('executions', {})
        resources = snapshot.get('resources', {})

        self._insert_catalog(session, catalog)
        self._insert_schedule(session, schedule)
        self._insert_executions(session, executions)
        self._insert_resources(session, resources)
        self._insert_settings(session, snapshot.get('settings', {'schema_version': SCHEMA_VERSION}))

    def _insert_catalog(self, session, catalog):
        sync = catalog.get('sync', {})
        session.add(SnapshotSync(
            id='current',
            schema_version=catalog.get('schema_version', SCHEMA_VERSION),
            provider=sync.get('provider', ''),
            updated_at=sync.get('updated_at', ''),
            data_hash=sync.get('data_hash', ''),
        ))
        for item in catalog.get('documents', []):
            session.add(SourceDocument(**_document_fields(item)))
        for item in catalog.get('test_items', []):
            session.add(TestItem(**_test_item_fields(item)))
        for item in catalog.get('exam_attempts', []):
            session.add(ExamAttempt(**_attempt_fields(item)))
        for message in catalog.get('migration', {}).get('warnings', []):
            session.add(MigrationWarning(source='catalog', message=message))

    def _insert_schedule(self, session, schedule):
        for item in schedule.get('blocks', []):
            session.add(ScheduleBlock(**_block_fields(item)))
        for item in schedule.get('block_items', []):
            session.add(BlockItem(**_block_item_fields(item)))
        for message in schedule.get('migration', {}).get('warnings', []):
            session.add(MigrationWarning(source='schedule', message=message))

    def _insert_executions(self, session, executions):
        for item in executions.get('runs', []):
            session.add(ExecutionRun(**_run_fields(item)))
        for message in executions.get('migration', {}).get('warnings', []):
            session.add(MigrationWarning(source='executions', message=message))

    def _insert_resources(self, session, resources):
        for kind in ('users', 'locations', 'versions'):
            for item in resources.get(kind, []):
                session.add(ResourceRecord(
                    kind=kind,
                    id=str(item.get('id', '')),
                    payload=deepcopy(item),
                ))

    def _insert_settings(self, session, settings):
        session.add(AppSettings(
            id='current',
            payload=deepcopy(settings),
        ))

    def _warnings(self, session, source):
        return [
            item.message
            for item in session.query(MigrationWarning)
            .filter_by(source=source)
            .order_by(MigrationWarning.id)
        ]

    def _resource_payloads(self, session, kind):
        return [
            deepcopy(item.payload)
            for item in session.query(ResourceRecord)
            .filter_by(kind=kind)
            .order_by(ResourceRecord.id)
        ]


def _document_fields(item):
    return {
        'id': item['id'],
        'legacy_task_ids': list(item.get('legacy_task_ids', [])),
        'external_doc_id': item.get('external_doc_id'),
        'version_id': item.get('version_id', ''),
        'doc_name': item.get('doc_name', ''),
        'is_active': bool(item.get('is_active', True)),
    }


def _document_to_dict(item):
    return _document_fields({
        'id': item.id,
        'legacy_task_ids': item.legacy_task_ids or [],
        'external_doc_id': item.external_doc_id,
        'version_id': item.version_id,
        'doc_name': item.doc_name,
        'is_active': item.is_active,
    })


def _test_item_fields(item):
    return {
        'id': item['id'],
        'document_id': item.get('document_id', ''),
        'external_test_id': item.get('external_test_id', ''),
        'name': item.get('name', ''),
        'estimated_minutes': int(item.get('estimated_minutes') or 0),
        'total_count': int(item.get('total_count') or 0),
        'owner_names': list(item.get('owner_names', [])),
        'is_active': bool(item.get('is_active', True)),
    }


def _test_item_to_dict(item):
    return _test_item_fields({
        'id': item.id,
        'document_id': item.document_id,
        'external_test_id': item.external_test_id,
        'name': item.name,
        'estimated_minutes': item.estimated_minutes,
        'total_count': item.total_count,
        'owner_names': item.owner_names or [],
        'is_active': item.is_active,
    })


def _attempt_fields(item):
    return {
        'id': item['id'],
        'test_item_id': item.get('test_item_id', ''),
        'exam_no': item.get('exam_no'),
        'legacy_task_id': item.get('legacy_task_id', ''),
        'legacy_identifier_id': item.get('legacy_identifier_id', ''),
        'default_location_id': item.get('default_location_id', ''),
        'default_assignee_names': list(item.get('default_assignee_names', [])),
        'memo': item.get('memo', ''),
        'state': item.get('state', 'active'),
    }


def _attempt_to_dict(item):
    return _attempt_fields({
        'id': item.id,
        'test_item_id': item.test_item_id,
        'exam_no': item.exam_no,
        'legacy_task_id': item.legacy_task_id,
        'legacy_identifier_id': item.legacy_identifier_id,
        'default_location_id': item.default_location_id,
        'default_assignee_names': item.default_assignee_names or [],
        'memo': item.memo,
        'state': item.state,
    })


def _block_fields(item):
    return {
        'id': item['id'],
        'legacy_block_id': item.get('legacy_block_id', ''),
        'date': item.get('date', ''),
        'start_time': item.get('start_time', ''),
        'end_time': item.get('end_time', ''),
        'location_id': item.get('location_id', ''),
        'assignee_names': list(item.get('assignee_names', [])),
        'kind': item.get('kind', 'test'),
        'title': item.get('title', ''),
        'memo': item.get('memo', ''),
        'is_locked': bool(item.get('is_locked', False)),
        'manual_status': item.get('manual_status', ''),
        'overflow_minutes': int(item.get('overflow_minutes') or 0),
    }


def _block_to_dict(item):
    return _block_fields({
        'id': item.id,
        'legacy_block_id': item.legacy_block_id,
        'date': item.date,
        'start_time': item.start_time,
        'end_time': item.end_time,
        'location_id': item.location_id,
        'assignee_names': item.assignee_names or [],
        'kind': item.kind,
        'title': item.title,
        'memo': item.memo,
        'is_locked': item.is_locked,
        'manual_status': item.manual_status,
        'overflow_minutes': item.overflow_minutes,
    })


def _block_item_fields(item):
    return {
        'id': item['id'],
        'block_id': item.get('block_id', ''),
        'exam_attempt_id': item.get('exam_attempt_id', ''),
        'sort_order': int(item.get('sort_order') or 0),
    }


def _block_item_to_dict(item):
    return _block_item_fields({
        'id': item.id,
        'block_id': item.block_id,
        'exam_attempt_id': item.exam_attempt_id,
        'sort_order': item.sort_order,
    })


def _run_fields(item):
    return {
        'id': item['id'],
        'legacy_execution_id': item.get('legacy_execution_id', ''),
        'exam_attempt_id': item.get('exam_attempt_id', ''),
        'status': item.get('status', 'pending'),
        'segments': list(item.get('segments', [])),
        'total_count': int(item.get('total_count') or 0),
        'fail_count': int(item.get('fail_count') or 0),
        'block_count': int(item.get('block_count') or 0),
        'pass_count': int(item.get('pass_count') or 0),
        'comment': item.get('comment', ''),
        'performer_name': item.get('performer_name', ''),
        'created_at': item.get('created_at'),
        'completed_at': item.get('completed_at'),
        'elapsed_seconds_snapshot': int(item.get('elapsed_seconds_snapshot') or 0),
        'elapsed_mins_snapshot': int(item.get('elapsed_mins_snapshot') or 0),
    }


def _run_to_dict(item):
    return _run_fields({
        'id': item.id,
        'legacy_execution_id': item.legacy_execution_id,
        'exam_attempt_id': item.exam_attempt_id,
        'status': item.status,
        'segments': item.segments or [],
        'total_count': item.total_count,
        'fail_count': item.fail_count,
        'block_count': item.block_count,
        'pass_count': item.pass_count,
        'comment': item.comment,
        'performer_name': item.performer_name,
        'created_at': item.created_at,
        'completed_at': item.completed_at,
        'elapsed_seconds_snapshot': item.elapsed_seconds_snapshot,
        'elapsed_mins_snapshot': item.elapsed_mins_snapshot,
    })


def _settings_payload(settings):
    payload = deepcopy(settings or {})
    payload['schema_version'] = payload.get('schema_version', SCHEMA_VERSION)
    payload.setdefault('provider_cache', {})
    return payload
