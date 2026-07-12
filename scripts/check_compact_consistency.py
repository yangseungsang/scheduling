#!/usr/bin/env python3
"""Check ORM storage payloads against compact ORM tables."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import DATABASE_URL
from app.services.compact_consistency import check_orm_storage_consistency


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--database-url',
        default=DATABASE_URL,
        help='SQLAlchemy database URL',
    )
    args = parser.parse_args()

    report = check_orm_storage_consistency(args.database_url)
    print(f'Consistency: {"ok" if report["ok"] else "mismatch"}')
    print(f'Expected counts: {report["counts"]["expected"]}')
    print(f'Actual counts: {report["counts"]["actual"]}')
    if report['mismatches']:
        print('Mismatched sections:')
        for section in report['mismatches']:
            print(f'  - {section}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
