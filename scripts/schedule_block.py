#!/usr/bin/env python3
"""Create, update, or delete JSON-backed schedule blocks."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import DOMAIN_DATA_DIR
from app.features.schedule.services.block_commands import ScheduleCommandService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default=DOMAIN_DATA_DIR)
    subparsers = parser.add_subparsers(dest='command', required=True)

    create = subparsers.add_parser('create')
    create.add_argument('--date', required=True)
    create.add_argument('--start-time', required=True)
    create.add_argument('--end-time', required=True)
    create.add_argument('--location-name', default='')
    create.add_argument('--assignee', action='append', default=[])
    create.add_argument('--procedure-id')
    create.add_argument('--test_item-id', action='append')
    create.add_argument('--block-id', default='')
    create.add_argument('--kind', default='test')
    create.add_argument('--title', default='')
    create.add_argument('--memo', default='')

    update = subparsers.add_parser('update')
    update.add_argument('block_id')
    update.add_argument('--date')
    update.add_argument('--start-time')
    update.add_argument('--end-time')
    update.add_argument('--location-name')
    update.add_argument('--memo')
    update.add_argument('--title')
    update.add_argument('--kind')

    test_items = subparsers.add_parser('test_items')
    test_items.add_argument('block_id')
    test_items.add_argument('--test_item-id', action='append', default=[])

    delete = subparsers.add_parser('delete')
    delete.add_argument('block_id')

    args = parser.parse_args()
    service = ScheduleCommandService(args.data_dir)

    if args.command == 'create':
        result = service.create_block(
            block_id=args.block_id,
            date=args.date,
            start_time=args.start_time,
            end_time=args.end_time,
            location_name=args.location_name,
            assignee_names=args.assignee,
            kind=args.kind,
            title=args.title,
            memo=args.memo,
            procedure_id=args.procedure_id,
            test_item_ids=args.test_item_id,
        )
    elif args.command == 'update':
        fields = {
            'date': args.date,
            'start_time': args.start_time,
            'end_time': args.end_time,
            'location_name': args.location_name,
            'memo': args.memo,
            'title': args.title,
            'kind': args.kind,
        }
        result = service.update_block(
            args.block_id,
            **{key: value for key, value in fields.items() if value is not None},
        )
    elif args.command == 'test_items':
        result = service.replace_test_items(args.block_id, args.test_item_id)
    else:
        result = {'deleted': service.delete_block(args.block_id)}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
