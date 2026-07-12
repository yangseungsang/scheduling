"""File adapters for compact snapshot generation."""

import json
from pathlib import Path

from app.services.compact_migration import build_compact_snapshot


def read_json(path, default):
    """Read a JSON file and return default for missing or empty files."""
    path = Path(path)
    if not path.exists():
        return default
    raw = path.read_text(encoding='utf-8').strip()
    if not raw:
        return default
    return json.loads(raw)


def write_json(path, data):
    """Write a JSON file using the app's readable compact format."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def build_snapshot_from_files(schedule_data_dir, execution_data_dir):
    """Build a compact snapshot from the current legacy JSON directories."""
    schedule_data_dir = Path(schedule_data_dir)
    execution_data_dir = Path(execution_data_dir)
    provider_cache = _load_provider_cache(schedule_data_dir)
    return build_compact_snapshot(
        tasks=read_json(schedule_data_dir / 'tasks.json', []),
        schedule_blocks=read_json(schedule_data_dir / 'schedule_blocks.json', []),
        executions=read_json(execution_data_dir / 'executions.json', []),
        users=read_json(schedule_data_dir / 'users.json', []),
        locations=read_json(schedule_data_dir / 'locations.json', []),
        versions=read_json(schedule_data_dir / 'versions.json', []),
        settings=read_json(schedule_data_dir / 'settings.json', {}),
        provider_cache=provider_cache,
    )


def _load_provider_cache(schedule_data_dir):
    meta = read_json(Path(schedule_data_dir) / 'dyn_ready_meta.json', {})
    if not meta:
        return {}
    return {
        'provider': 'dyn_ready',
        'updated_at': meta.get('updated_at', ''),
        'data_hash': meta.get('data_hash', ''),
    }
