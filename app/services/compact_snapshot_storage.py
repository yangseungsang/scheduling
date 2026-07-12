"""Build compact snapshots from legacy-shaped storage adapters."""

from app.services.compact_migration import build_compact_snapshot


def build_snapshot_from_legacy_storage(schedule_storage, execution_storage):
    """Build a compact snapshot from schedule/execution storage adapters."""
    provider_cache = _provider_cache(schedule_storage.get_all('dyn_ready_meta.json'))
    return build_compact_snapshot(
        tasks=schedule_storage.get_all('tasks.json'),
        schedule_blocks=schedule_storage.get_all('schedule_blocks.json'),
        executions=execution_storage.get_all(),
        users=schedule_storage.get_all('users.json'),
        locations=schedule_storage.get_all('locations.json'),
        versions=schedule_storage.get_all('versions.json'),
        settings=schedule_storage.get_all('settings.json'),
        provider_cache=provider_cache,
    )


def _provider_cache(meta):
    if not meta:
        return {}
    return {
        'provider': 'dyn_ready',
        'updated_at': meta.get('updated_at', ''),
        'data_hash': meta.get('data_hash', ''),
    }
