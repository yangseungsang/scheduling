from datetime import datetime

from schedule.store import read_json, write_json, generate_id

FILENAME = 'tasks.json'


def get_all():
    return read_json(FILENAME)


def validate_unique_identifiers(test_list, exclude_task_id=None):
    """Check that identifier IDs in test_list are globally unique across all tasks.

    Returns list of duplicate IDs, or empty list if all unique.
    """
    new_ids = [item['id'] for item in test_list if isinstance(item, dict)]
    if not new_ids:
        return []

    existing_ids = set()
    for t in read_json(FILENAME):
        if exclude_task_id and t['id'] == exclude_task_id:
            continue
        for item in t.get('test_list', []):
            if isinstance(item, dict):
                existing_ids.add(item['id'])
            else:
                existing_ids.add(item)
    return [i for i in new_ids if i in existing_ids]


def compute_estimated_hours(test_list):
    """Sum estimated_hours from test_list identifiers."""
    total = 0
    for item in (test_list or []):
        if isinstance(item, dict):
            total += item.get('estimated_hours', 0)
    return round(total, 2)


def get_by_id(task_id):
    for t in read_json(FILENAME):
        if t['id'] == task_id:
            return t
    return None


def get_by_version(version_id):
    return [t for t in read_json(FILENAME) if t.get('version_id') == version_id]


def create(procedure_id, version_id, assignee_ids, location_id,
           section_name, procedure_owner, test_list,
           estimated_hours, memo=''):
    tasks = read_json(FILENAME)
    task = {
        'id': generate_id('t_'),
        'procedure_id': procedure_id,
        'version_id': version_id,
        'assignee_ids': assignee_ids or [],
        'location_id': location_id,
        'section_name': section_name,
        'procedure_owner': procedure_owner,
        'test_list': test_list or [],
        'estimated_hours': estimated_hours,
        'remaining_hours': estimated_hours,
        'status': 'waiting',
        'memo': memo,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    tasks.append(task)
    write_json(FILENAME, tasks)
    return task


def update(task_id, procedure_id, version_id, assignee_ids, location_id,
           section_name, procedure_owner, test_list,
           estimated_hours, remaining_hours, status, memo=''):
    tasks = read_json(FILENAME)
    for t in tasks:
        if t['id'] == task_id:
            t['procedure_id'] = procedure_id
            t['version_id'] = version_id
            t['assignee_ids'] = assignee_ids or []
            t['location_id'] = location_id
            t['section_name'] = section_name
            t['procedure_owner'] = procedure_owner
            t['test_list'] = test_list or []
            t['estimated_hours'] = estimated_hours
            t['remaining_hours'] = remaining_hours
            t['status'] = status
            t['memo'] = memo
            write_json(FILENAME, tasks)
            return t
    return None


def patch(task_id, **kwargs):
    tasks = read_json(FILENAME)
    for t in tasks:
        if t['id'] == task_id:
            for k, v in kwargs.items():
                t[k] = v
            write_json(FILENAME, tasks)
            return t
    return None


def delete(task_id):
    tasks = read_json(FILENAME)
    tasks = [t for t in tasks if t['id'] != task_id]
    write_json(FILENAME, tasks)
