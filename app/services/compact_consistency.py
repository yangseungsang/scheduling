"""Consistency checks between compact snapshot sources."""

import hashlib
import json
from copy import deepcopy

from app.db.repository import CompactSnapshotOrmRepository
from app.services.compact_snapshot_storage import build_snapshot_from_legacy_storage

LIST_SORT_KEYS = {
    ('catalog', 'documents'): ('id',),
    ('catalog', 'test_items'): ('id',),
    ('catalog', 'exam_attempts'): ('id',),
    ('schedule', 'blocks'): ('id',),
    ('schedule', 'block_items'): ('id',),
    ('executions', 'runs'): ('id',),
    ('resources', 'users'): ('id', 'name'),
    ('resources', 'locations'): ('id', 'name'),
    ('resources', 'versions'): ('id', 'name'),
}


def check_orm_storage_consistency(database_url):
    """Compare ORM storage payloads with compact ORM tables."""
    from app.features.execution.repositories import OrmExecutionStorage
    from app.features.schedule.repositories import OrmScheduleStorage

    schedule_storage = OrmScheduleStorage(database_url, sync_compact=False)
    execution_storage = OrmExecutionStorage(database_url, sync_compact=False)
    expected = build_snapshot_from_legacy_storage(schedule_storage, execution_storage)
    actual = CompactSnapshotOrmRepository(database_url).load_snapshot()
    return compare_snapshots(expected, actual)


def compare_snapshots(expected, actual):
    """Return a compact consistency report for two snapshot payloads."""
    expected_canonical = canonical_snapshot(expected)
    actual_canonical = canonical_snapshot(actual)
    expected_hashes = _section_hashes(expected_canonical)
    actual_hashes = _section_hashes(actual_canonical)
    mismatches = [
        name for name in ('catalog', 'schedule', 'executions', 'resources', 'settings')
        if expected_hashes.get(name) != actual_hashes.get(name)
    ]
    return {
        'ok': not mismatches,
        'mismatches': mismatches,
        'counts': {
            'expected': snapshot_counts(expected_canonical),
            'actual': snapshot_counts(actual_canonical),
        },
        'hashes': {
            'expected': expected_hashes,
            'actual': actual_hashes,
        },
    }


def snapshot_counts(snapshot):
    """Return stable record counts for a compact snapshot."""
    return {
        'documents': len(snapshot.get('catalog', {}).get('documents', [])),
        'test_items': len(snapshot.get('catalog', {}).get('test_items', [])),
        'exam_attempts': len(snapshot.get('catalog', {}).get('exam_attempts', [])),
        'blocks': len(snapshot.get('schedule', {}).get('blocks', [])),
        'block_items': len(snapshot.get('schedule', {}).get('block_items', [])),
        'execution_runs': len(snapshot.get('executions', {}).get('runs', [])),
        'users': len(snapshot.get('resources', {}).get('users', [])),
        'locations': len(snapshot.get('resources', {}).get('locations', [])),
        'versions': len(snapshot.get('resources', {}).get('versions', [])),
    }


def canonical_snapshot(snapshot):
    """Return snapshot data with deterministic list ordering."""
    result = deepcopy(snapshot)
    for path, keys in LIST_SORT_KEYS.items():
        container = result
        for part in path[:-1]:
            container = container.get(part, {})
        values = container.get(path[-1], [])
        if isinstance(values, list):
            container[path[-1]] = sorted(values, key=lambda item: _sort_tuple(item, keys))
    for section in ('catalog', 'schedule', 'executions'):
        warnings = result.get(section, {}).get('migration', {}).get('warnings')
        if isinstance(warnings, list):
            result[section]['migration']['warnings'] = sorted(warnings)
    return result


def _section_hashes(snapshot):
    return {
        name: _hash_payload(snapshot.get(name, {}))
        for name in ('catalog', 'schedule', 'executions', 'resources', 'settings')
    }


def _hash_payload(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _sort_tuple(item, keys):
    if not isinstance(item, dict):
        return ('',)
    return tuple(str(item.get(key, '')) for key in keys)
