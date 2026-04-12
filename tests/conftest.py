import json
import os
import re

import pytest

from app import create_app


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def app(tmp_path):
    """Create app with a temporary data directory."""
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)

    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions', 'procedures'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)

    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00',
            'work_end': '17:00',
            'actual_work_start': '08:30',
            'actual_work_end': '16:30',
            'lunch_start': '12:00',
            'lunch_end': '13:00',
            'breaks': [
                {'start': '09:45', 'end': '10:00'},
                {'start': '14:45', 'end': '15:00'},
            ],
            'grid_interval_minutes': 15,
            'max_schedule_days': 14,
            'block_color_by': 'assignee',
        }, f)

    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


# ===========================================================================
# Helper functions
# ===========================================================================

def _create_user(client, name='홍길동', role='개발자', color='#4A90D9'):
    """Helper: create a user via form and return the user **name**.

    신 스키마에서는 담당자 참조가 이름 기반이므로 id 대신 name을 반환한다.
    기존 테스트에서 `uid = _create_user(client)`로 받은 값은 그대로
    assignee_names 리스트에 넣을 수 있다.
    """
    client.post('/admin/users/new', data={
        'name': name, 'role': role, 'color': color,
    })
    return name


def _create_location(client, name='A', color='#28a745', description='시험실'):
    """Helper: create a location via form and return the loc_id."""
    client.post('/admin/locations/new', data={
        'name': name, 'color': color, 'description': description,
    })
    r = client.get('/admin/locations')
    ids = re.findall(r'/admin/locations/(loc_\w+)/edit', r.data.decode())
    return ids[-1]


def _create_version(client, name='v1.0.0', description='테스트'):
    """Helper: create a version via API and return the version_id."""
    r = client.post('/admin/api/versions', json={
        'name': name, 'description': description,
    })
    return r.get_json()['id']


_TASK_DOC_COUNTER = [100]


def _create_task(client, uid_list, loc_id='', version_id='',
                 doc_id=None, hours='4', **_legacy):
    """Helper: create a task via form and return the task_id.

    `uid_list`는 과거엔 사용자 ID 리스트였지만 신 스키마에서는 담당자 **이름** 리스트다.
    테스트 호환을 위해 값은 그대로 넘긴다 — users 픽스처는 실제 이름을 만든다.
    """
    if isinstance(uid_list, str):
        uid_list = [uid_list]
    if doc_id is None:
        _TASK_DOC_COUNTER[0] += 1
        doc_id = _TASK_DOC_COUNTER[0]
    total_minutes = round(float(hours) * 60)
    identifiers = [
        {'id': 'TC-001', 'estimated_minutes': total_minutes // 2, 'owners': []},
        {'id': 'TC-002', 'estimated_minutes': total_minutes - total_minutes // 2, 'owners': []},
    ]
    data = {
        'doc_id': str(doc_id),
        'version_id': version_id,
        'assignee_names': uid_list,
        'location_id': loc_id,
        'doc_name': '시스템',
        'identifiers_json': json.dumps(identifiers),
        'estimated_minutes': str(total_minutes),
        'memo': '',
    }
    client.post('/tasks/new', data=data)
    r = client.get('/tasks/')
    ids = re.findall(r'/tasks/(t_\w+)', r.data.decode())
    return ids[-1]


def _create_block(client, tid, uid_list, date_str='2026-03-10',
                  start='09:00', end='10:00', **kwargs):
    """Helper: create a schedule block via API and return (json, status_code)."""
    if isinstance(uid_list, str):
        uid_list = [uid_list]
    payload = {
        'task_id': tid, 'assignee_names': uid_list,
        'date': date_str, 'start_time': start, 'end_time': end,
    }
    payload.update(kwargs)
    r = client.post('/schedule/api/blocks', json=payload)
    return r.get_json(), r.status_code
