#!/usr/bin/env python3
"""Load current legacy JSON storage files into ORM storage payloads."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import DATABASE_URL
from app.features.execution.repositories import OrmExecutionStorage
from app.features.schedule.repositories import OrmScheduleStorage
from app.services.compact_orm_sync import sync_compact_from_orm_storage
from app.services.compact_snapshot_files import read_json

DEFAULT_SCHEDULE_DATA_DIR = ROOT / 'app' / 'features' / 'schedule' / 'data'
DEFAULT_EXECUTION_DATA_DIR = ROOT / 'app' / 'features' / 'execution' / 'data'
SCHEDULE_FILES = (
    'users.json',
    'locations.json',
    'tasks.json',
    'schedule_blocks.json',
    'versions.json',
    'procedures.json',
    'settings.json',
    'dyn_ready_meta.json',
)


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
    args = parser.parse_args()

    schedule_storage = OrmScheduleStorage(args.database_url)
    execution_storage = OrmExecutionStorage(args.database_url)

    loaded_schedule = 0
    for filename in SCHEDULE_FILES:
        default = {} if filename in ('settings.json', 'dyn_ready_meta.json') else []
        payload = read_json(args.schedule_data_dir / filename, default)
        schedule_storage.save_all(filename, payload)
        loaded_schedule += 1

    executions = read_json(args.execution_data_dir / 'executions.json', [])
    execution_storage.save_all(executions)
    snapshot = sync_compact_from_orm_storage(args.database_url)

    print(f'Loaded legacy storage payloads into {args.database_url}')
    print(f'Schedule files: {loaded_schedule}')
    print(f'Execution records: {len(executions)}')
    print(f'Compact documents: {len(snapshot["catalog"]["documents"])}')
    print(f'Compact blocks: {len(snapshot["schedule"]["blocks"])}')


if __name__ == '__main__':
    main()
