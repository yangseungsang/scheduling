#!/usr/bin/env python3
"""Load current legacy JSON data into the compact ORM database."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import DATABASE_URL
from app.db.repository import CompactSnapshotOrmRepository
from app.repositories.compact_snapshot import LegacyJsonCompactSnapshotRepository

DEFAULT_SCHEDULE_DATA_DIR = ROOT / 'app' / 'features' / 'schedule' / 'data'
DEFAULT_EXECUTION_DATA_DIR = ROOT / 'app' / 'features' / 'execution' / 'data'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--schedule-data-dir',
        type=Path,
        default=DEFAULT_SCHEDULE_DATA_DIR,
        help='Legacy schedule data directory',
    )
    parser.add_argument(
        '--execution-data-dir',
        type=Path,
        default=DEFAULT_EXECUTION_DATA_DIR,
        help='Legacy execution data directory',
    )
    parser.add_argument(
        '--database-url',
        default=DATABASE_URL,
        help='SQLAlchemy database URL',
    )
    parser.add_argument(
        '--drop-existing',
        action='store_true',
        help='Drop compact ORM tables before loading the snapshot',
    )
    args = parser.parse_args()

    source_repository = LegacyJsonCompactSnapshotRepository(
        args.schedule_data_dir,
        args.execution_data_dir,
    )
    snapshot = source_repository.load_snapshot()
    repository = CompactSnapshotOrmRepository(args.database_url)
    repository.create_schema(drop_existing=args.drop_existing)
    repository.replace_snapshot(snapshot)

    print(f'Loaded compact snapshot into {args.database_url}')
    print(f'Documents: {len(snapshot["catalog"]["documents"])}')
    print(f'Test items: {len(snapshot["catalog"]["test_items"])}')
    print(f'Exam attempts: {len(snapshot["catalog"]["exam_attempts"])}')
    print(f'Blocks: {len(snapshot["schedule"]["blocks"])}')
    print(f'Block items: {len(snapshot["schedule"]["block_items"])}')
    print(f'Execution runs: {len(snapshot["executions"]["runs"])}')


if __name__ == '__main__':
    main()
