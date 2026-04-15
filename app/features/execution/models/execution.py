"""시험 실행 기록 레포지토리."""

from datetime import datetime

from app.features.execution.store import read_json, write_json, generate_id

FILENAME = 'executions.json'
ID_PREFIX = 'ex_'


def get_all():
    return read_json(FILENAME)


def get_by_id(execution_id):
    for item in read_json(FILENAME):
        if item['id'] == execution_id:
            return item
    return None


def get_by_block(block_id):
    return [e for e in read_json(FILENAME) if e.get('block_id') == block_id]


def get_by_identifier(block_id, identifier_id):
    for e in read_json(FILENAME):
        if e.get('block_id') == block_id and e.get('identifier_id') == identifier_id:
            return e
    return None


def start(block_id, task_id, doc_name, identifier_id, tester_name):
    """시험 시작 — status=in_progress, started_at=now."""
    items = read_json(FILENAME)
    data = {
        'id': generate_id(ID_PREFIX),
        'block_id': block_id,
        'task_id': task_id,
        'doc_name': doc_name,
        'identifier_id': identifier_id,
        'tester_name': tester_name,
        'status': 'in_progress',
        'started_at': datetime.now().strftime('%Y-%m-%dT%H:%M'),
        'completed_at': None,
        'pass_count': 0,
        'fail_count': 0,
        'comment': '',
        'action': '',
    }
    items.append(data)
    write_json(FILENAME, items)
    return data


def complete(execution_id, pass_count, fail_count):
    """결과 입력 — status=completed, completed_at=now."""
    items = read_json(FILENAME)
    for item in items:
        if item['id'] == execution_id:
            item['status'] = 'completed'
            item['completed_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M')
            item['pass_count'] = int(pass_count)
            item['fail_count'] = int(fail_count)
            write_json(FILENAME, items)
            return item
    return None


def update_comment(execution_id, comment, action):
    """특이사항/조치사항 수정."""
    items = read_json(FILENAME)
    for item in items:
        if item['id'] == execution_id:
            item['comment'] = comment
            item['action'] = action
            write_json(FILENAME, items)
            return item
    return None


def cancel(execution_id):
    """시작 취소 — status=pending, started_at 초기화."""
    items = read_json(FILENAME)
    for item in items:
        if item['id'] == execution_id:
            item['status'] = 'pending'
            item['started_at'] = None
            item['completed_at'] = None
            item['pass_count'] = 0
            item['fail_count'] = 0
            write_json(FILENAME, items)
            return item
    return None
