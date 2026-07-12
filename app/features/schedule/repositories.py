"""Storage adapters for schedule records."""

from typing import Protocol

from app.repositories.orm_file_storage import OrmFileStorage
from app.db.repository import CompactSnapshotOrmRepository
from app.features.schedule.store import generate_id, read_json, write_json

RESOURCE_FILES = {
    'users.json': 'users',
    'locations.json': 'locations',
    'versions.json': 'versions',
}


class ScheduleStorage(Protocol):
    """Storage contract used by schedule model repositories."""

    def get_all(self, filename):
        """Return all records from a schedule data file."""

    def save_all(self, filename, items):
        """Persist all records to a schedule data file."""

    def generate_id(self, prefix):
        """Generate a new schedule record id."""


class JsonScheduleStorage:
    """Schedule storage backed by current JSON files."""

    def get_all(self, filename):
        return read_json(filename)

    def save_all(self, filename, items):
        write_json(filename, items)

    def generate_id(self, prefix):
        return generate_id(prefix)


class OrmScheduleStorage:
    """Schedule storage backed by the transitional ORM payload table."""

    def __init__(self, database_url, sync_compact=False):
        self.database_url = database_url
        self.sync_compact = sync_compact
        self.storage = OrmFileStorage(database_url, area='schedule')

    def get_all(self, filename):
        default = {} if filename == 'settings.json' else []
        return self.storage.get_payload(filename, default)

    def save_all(self, filename, items):
        self.storage.save_payload(filename, items)
        self._sync_compact(filename, items)

    def generate_id(self, prefix):
        return generate_id(prefix)

    def _sync_compact(self, filename, items):
        if not self.sync_compact:
            return
        repository = CompactSnapshotOrmRepository(self.database_url)
        if filename in RESOURCE_FILES:
            repository.replace_resources(RESOURCE_FILES[filename], items)
            return
        if filename == 'settings.json':
            repository.replace_settings(items)
            return
        if filename == 'procedures.json':
            return
        snapshot = self._snapshot()
        if filename == 'tasks.json':
            repository.replace_catalog_schedule_executions(snapshot)
            return
        if filename == 'schedule_blocks.json':
            repository.replace_schedule(snapshot['schedule'])
            return
        from app.services.compact_orm_sync import sync_compact_from_orm_storage
        sync_compact_from_orm_storage(self.database_url)

    def _snapshot(self):
        from app.features.execution.repositories import OrmExecutionStorage
        from app.services.compact_snapshot_storage import build_snapshot_from_legacy_storage

        execution_storage = OrmExecutionStorage(self.database_url, sync_compact=False)
        return build_snapshot_from_legacy_storage(self, execution_storage)


class CompactOrmScheduleStorage:
    """Schedule storage facade backed by compact ORM tables.

    Resource/settings writes are supported directly. Catalog and schedule block
    legacy payloads are read-only compatibility projections.
    """

    def __init__(self, database_url):
        self.database_url = database_url
        self.repository = CompactSnapshotOrmRepository(database_url)
        self.repository.create_schema()

    def get_all(self, filename):
        snapshot = self.repository.load_snapshot()
        if filename in RESOURCE_FILES:
            return snapshot.get('resources', {}).get(RESOURCE_FILES[filename], [])
        if filename == 'settings.json':
            return snapshot.get('settings', {})
        if filename == 'tasks.json':
            return _compact_tasks(snapshot)
        if filename == 'schedule_blocks.json':
            return _compact_schedule_blocks(snapshot)
        if filename == 'procedures.json':
            return []
        return []

    def save_all(self, filename, items):
        if filename in RESOURCE_FILES:
            self.repository.replace_resources(RESOURCE_FILES[filename], items)
            return
        if filename == 'settings.json':
            self.repository.replace_settings(items)
            return
        raise ValueError(f'{filename} is read-only for SCHEDULE_STORAGE=compact_orm')

    def generate_id(self, prefix):
        return generate_id(prefix)


def schedule_storage_from_config(config):
    """Create the configured schedule storage adapter."""
    source = config.get('SCHEDULE_STORAGE', 'json')
    if source == 'json':
        return JsonScheduleStorage()
    if source == 'orm':
        return OrmScheduleStorage(
            config['DATABASE_URL'],
            sync_compact=config.get('SYNC_COMPACT_ON_ORM_STORAGE_WRITE', True),
        )
    if source == 'compact_orm':
        return CompactOrmScheduleStorage(config['DATABASE_URL'])
    raise ValueError(f'Unsupported SCHEDULE_STORAGE: {source}')


def _compact_tasks(snapshot):
    catalog = snapshot.get('catalog', {})
    documents = {
        item['id']: item
        for item in catalog.get('documents', [])
    }
    test_items = {
        item['id']: item
        for item in catalog.get('test_items', [])
    }
    grouped = {}
    for attempt in catalog.get('exam_attempts', []):
        task_id = attempt.get('legacy_task_id')
        if not task_id:
            continue
        grouped.setdefault(task_id, []).append(attempt)

    tasks = []
    for task_id, attempts in grouped.items():
        attempts = sorted(
            attempts,
            key=lambda item: (
                item.get('legacy_identifier_id', ''),
                item.get('exam_no') if item.get('exam_no') is not None else 0,
                item.get('id', ''),
            ),
        )
        first = attempts[0]
        first_test = test_items.get(first.get('test_item_id'), {})
        document = documents.get(first_test.get('document_id'), {})
        identifiers = []
        estimated_minutes = 0
        for attempt in attempts:
            test_item = test_items.get(attempt.get('test_item_id'), {})
            minutes = int(test_item.get('estimated_minutes') or 0)
            estimated_minutes += minutes
            identifiers.append({
                'id': test_item.get('external_test_id', ''),
                'name': test_item.get('name', ''),
                'estimated_minutes': minutes,
                'total_count': int(test_item.get('total_count') or 0),
                'owners': list(test_item.get('owner_names', [])),
            })
        tasks.append({
            'id': task_id,
            'doc_id': document.get('external_doc_id', ''),
            'version_id': document.get('version_id', ''),
            'doc_name': document.get('doc_name', ''),
            'exam_no': first.get('exam_no'),
            'assignee_names': list(first.get('default_assignee_names', [])),
            'location_id': first.get('default_location_id', ''),
            'identifiers': identifiers,
            'estimated_minutes': estimated_minutes,
            'memo': first.get('memo', ''),
            'status': 'cancelled' if first.get('state') == 'cancelled' else 'pending',
        })
    return sorted(tasks, key=lambda item: (item.get('doc_name', ''), item.get('exam_no') or 0, item['id']))


def _compact_schedule_blocks(snapshot):
    attempts = {
        item['id']: item
        for item in snapshot.get('catalog', {}).get('exam_attempts', [])
    }
    items_by_block = {}
    for item in snapshot.get('schedule', {}).get('block_items', []):
        items_by_block.setdefault(item.get('block_id'), []).append(item)

    blocks = []
    for block in snapshot.get('schedule', {}).get('blocks', []):
        block_items = sorted(
            items_by_block.get(block.get('id'), []),
            key=lambda item: item.get('sort_order', 0),
        )
        block_attempts = [
            attempts.get(item.get('exam_attempt_id'), {})
            for item in block_items
        ]
        block_attempts = [item for item in block_attempts if item]
        task_id = block_attempts[0].get('legacy_task_id') if block_attempts else None
        identifier_ids = [
            item.get('legacy_identifier_id')
            for item in block_attempts
            if item.get('legacy_identifier_id')
        ]
        blocks.append({
            'id': block.get('legacy_block_id') or block.get('id'),
            'compact_id': block.get('id'),
            'task_id': task_id,
            'date': block.get('date', ''),
            'start_time': block.get('start_time', ''),
            'end_time': block.get('end_time', ''),
            'location_id': block.get('location_id', ''),
            'assignee_names': list(block.get('assignee_names', [])),
            'identifier_ids': identifier_ids,
            'block_status': block.get('manual_status') or 'pending',
            'memo': block.get('memo', ''),
            'is_locked': bool(block.get('is_locked')),
            'title': block.get('title', ''),
            'is_simple': block.get('kind') == 'simple',
            'overflow_minutes': int(block.get('overflow_minutes') or 0),
        })
    return sorted(blocks, key=lambda item: (item.get('date', ''), item.get('start_time', ''), item.get('id', '')))
