#!/usr/bin/env python3
"""Create, update, or delete compact ORM schedule blocks."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import DATABASE_URL
from app.services.compact_schedule_commands import CompactScheduleCommandService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=DATABASE_URL)
    subparsers = parser.add_subparsers(dest='command', required=True)

    create = subparsers.add_parser('create')
    create.add_argument('--date', required=True)
    create.add_argument('--start-time', required=True)
    create.add_argument('--end-time', required=True)
    create.add_argument('--location-id', default='')
    create.add_argument('--assignee', action='append', default=[])
    create.add_argument('--attempt-id', action='append', default=[])
    create.add_argument('--legacy-block-id', default='')
    create.add_argument('--kind', default='test')
    create.add_argument('--title', default='')
    create.add_argument('--memo', default='')

    update = subparsers.add_parser('update')
    update.add_argument('block_id')
    update.add_argument('--date')
    update.add_argument('--start-time')
    update.add_argument('--end-time')
    update.add_argument('--location-id')
    update.add_argument('--memo')
    update.add_argument('--title')
    update.add_argument('--kind')

    items = subparsers.add_parser('items')
    items.add_argument('block_id')
    items.add_argument('--attempt-id', action='append', default=[])

    delete = subparsers.add_parser('delete')
    delete.add_argument('block_id')

    args = parser.parse_args()
    service = CompactScheduleCommandService(args.database_url)

    if args.command == 'create':
        result = service.create_block(
            legacy_block_id=args.legacy_block_id,
            date=args.date,
            start_time=args.start_time,
            end_time=args.end_time,
            location_id=args.location_id,
            assignee_names=args.assignee,
            kind=args.kind,
            title=args.title,
            memo=args.memo,
            exam_attempt_ids=args.attempt_id,
        )
    elif args.command == 'update':
        fields = {
            'date': args.date,
            'start_time': args.start_time,
            'end_time': args.end_time,
            'location_id': args.location_id,
            'memo': args.memo,
            'title': args.title,
            'kind': args.kind,
        }
        result = service.update_block(
            args.block_id,
            **{key: value for key, value in fields.items() if value is not None},
        )
    elif args.command == 'items':
        result = service.replace_block_items(args.block_id, args.attempt_id)
    else:
        result = {'deleted': service.delete_block(args.block_id)}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
