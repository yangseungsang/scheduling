"""Repository boundary for compact snapshot storage backends."""

from pathlib import Path
from typing import Protocol

from app.db.repository import CompactSnapshotOrmRepository
from app.services.compact_snapshot_files import build_snapshot_from_files


class CompactSnapshotRepository(Protocol):
    """Storage-independent compact snapshot reader."""

    def load_snapshot(self):
        """Return the compact snapshot contract."""


class LegacyJsonCompactSnapshotRepository:
    """Build compact snapshots from the current legacy JSON data files."""

    def __init__(self, schedule_data_dir, execution_data_dir):
        self.schedule_data_dir = Path(schedule_data_dir)
        self.execution_data_dir = Path(execution_data_dir)

    def load_snapshot(self):
        return build_snapshot_from_files(self.schedule_data_dir, self.execution_data_dir)


def compact_snapshot_repository_from_config(config):
    """Create the configured compact snapshot repository."""
    source = config.get('EXTERNAL_DATA_SOURCE', 'json')
    if source == 'json':
        return LegacyJsonCompactSnapshotRepository(
            config['DATA_DIR'],
            config['EXECUTION_DATA_DIR'],
        )
    if source == 'orm':
        return CompactSnapshotOrmRepository(config['DATABASE_URL'])
    raise ValueError(f'Unsupported EXTERNAL_DATA_SOURCE: {source}')
