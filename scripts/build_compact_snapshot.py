#!/usr/bin/env python3
"""Build compact JSON snapshot files from the current legacy data files."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.compact_snapshot_files import (
    build_snapshot_from_files,
    write_json,
)

DEFAULT_SCHEDULE_DATA_DIR = ROOT / 'app' / 'features' / 'schedule' / 'data'
DEFAULT_EXECUTION_DATA_DIR = ROOT / 'app' / 'features' / 'execution' / 'data'
DEFAULT_OUTPUT_DIR = ROOT / 'exports' / 'compact-snapshot'


def build_from_files(schedule_data_dir, execution_data_dir):
    return build_snapshot_from_files(schedule_data_dir, execution_data_dir)


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
        '--output-dir',
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help='Directory for compact JSON snapshot files',
    )
    args = parser.parse_args()

    snapshot = build_snapshot_from_files(args.schedule_data_dir, args.execution_data_dir)
    for name, payload in snapshot.items():
        write_json(args.output_dir / f'{name}.json', payload)

    warnings = []
    for name in ('catalog', 'schedule', 'executions'):
        warnings.extend(snapshot[name].get('migration', {}).get('warnings', []))

    print(f'Wrote compact snapshot to {args.output_dir}')
    print(f'Documents: {len(snapshot["catalog"]["documents"])}')
    print(f'Test items: {len(snapshot["catalog"]["test_items"])}')
    print(f'Exam attempts: {len(snapshot["catalog"]["exam_attempts"])}')
    print(f'Blocks: {len(snapshot["schedule"]["blocks"])}')
    print(f'Block items: {len(snapshot["schedule"]["block_items"])}')
    print(f'Execution runs: {len(snapshot["executions"]["runs"])}')
    if warnings:
        print(f'Warnings: {len(warnings)}')
        for warning in warnings[:20]:
            print(f'  - {warning}')
        if len(warnings) > 20:
            print(f'  ... {len(warnings) - 20} more')


if __name__ == '__main__':
    main()
