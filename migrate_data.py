#!/usr/bin/env python3
"""One-time migration: convert test_list from string arrays to object arrays,
and add new fields to schedule_blocks."""

import json
import os
import shutil

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def read(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write(filename, data):
    path = os.path.join(DATA_DIR, filename)
    backup = path + '.pre_migration.bak'
    if os.path.exists(path) and not os.path.exists(backup):
        shutil.copy2(path, backup)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  Written {filename} ({len(data)} records)')


def migrate_tasks():
    tasks = read('tasks.json')
    changed = 0
    for t in tasks:
        tl = t.get('test_list', [])
        if not tl:
            continue
        # Already migrated?
        if isinstance(tl[0], dict):
            continue
        est = t.get('estimated_hours', 0)
        n = len(tl)
        per_item = round(est / n, 4) if n > 0 else 0
        t['test_list'] = [{'id': item, 'estimated_hours': per_item, 'owners': []} for item in tl]
        changed += 1
    write('tasks.json', tasks)
    print(f'  Migrated {changed} tasks')


def migrate_procedures():
    procedures = read('procedures.json')
    changed = 0
    for p in procedures:
        tl = p.get('test_list', [])
        if not tl:
            continue
        if isinstance(tl[0], dict):
            continue
        p['test_list'] = [{'id': item, 'estimated_hours': 0, 'owners': []} for item in tl]
        changed += 1
    write('procedures.json', procedures)
    print(f'  Migrated {changed} procedures')


def migrate_schedule_blocks():
    blocks = read('schedule_blocks.json')
    changed = 0
    for b in blocks:
        if 'identifier_ids' not in b:
            b['identifier_ids'] = None
            changed += 1
        if 'title' not in b:
            b['title'] = ''
        if 'is_simple' not in b:
            b['is_simple'] = False
    write('schedule_blocks.json', blocks)
    print(f'  Added new fields to {changed} blocks')


def cleanup_schedule_blocks():
    """Remove unused origin and is_draft fields from all schedule blocks."""
    blocks = read('schedule_blocks.json')
    changed = 0
    for b in blocks:
        removed = False
        if 'origin' in b:
            del b['origin']
            removed = True
        if 'is_draft' in b:
            del b['is_draft']
            removed = True
        if removed:
            changed += 1
    write('schedule_blocks.json', blocks)
    print(f'  Cleaned up {changed} blocks (removed origin, is_draft)')


def add_source_fields():
    """Add source and external_key to existing tasks."""
    tasks = read('tasks.json')
    changed = 0
    for t in tasks:
        if 'source' not in t:
            t['source'] = 'local'
            t['external_key'] = ''
            changed += 1
    write('tasks.json', tasks)
    print(f'  Added source field to {changed} tasks')


def update_procedures_format():
    """Update procedures.json to new provider format with version_id."""
    procedures = read('procedures.json')
    changed = 0
    for p in procedures:
        if 'identifiers' not in p:
            p['identifiers'] = p.pop('test_list', [])
            changed += 1
        if 'version_id' not in p:
            p['version_id'] = ''
            changed += 1
    write('procedures.json', procedures)
    print(f'  Updated {changed} procedures to new format')


def remove_task_status_field():
    """tasks.json 에서 status 필드 제거 (#108).

    'cancelled' 값은 sync 서비스가 외부에서 삭제된 태스크 표시에 사용하므로 유지.
    'waiting'/'in_progress'/'completed' 는 execution 기반으로 동적 계산되므로 삭제.
    """
    import os, json as _json
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'app', 'features', 'schedule', 'data')
    tasks_file = os.path.join(data_dir, 'tasks.json')
    with open(tasks_file) as f:
        tasks = _json.load(f)

    removed = retained = 0
    for t in tasks:
        s = t.get('status')
        if s == 'cancelled':
            retained += 1
        elif 'status' in t:
            del t['status']
            removed += 1

    with open(tasks_file, 'w', encoding='utf-8') as f:
        _json.dump(tasks, f, ensure_ascii=False, indent=2)

    print(f'  tasks.json: status 필드 {removed}개 삭제, cancelled {retained}개 유지')


if __name__ == '__main__':
    print('=== Data Migration ===')
    print('Migrating tasks...')
    migrate_tasks()
    print('Migrating procedures...')
    migrate_procedures()
    print('Migrating schedule blocks...')
    migrate_schedule_blocks()
    print('태스크 status 필드 마이그레이션 중...')
    remove_task_status_field()
    print('=== Done ===')
