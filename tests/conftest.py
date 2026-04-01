import json
import os
import re

import pytest

from schedule import create_app


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
    """Helper: create a user via form and return the user_id."""
    client.post('/admin/users/new', data={
        'name': name, 'role': role, 'color': color,
    })
    r = client.get('/admin/users')
    ids = re.findall(r'/admin/users/(u_\w+)/edit', r.data.decode())
    return ids[-1]


def _create_location(client, name='A', color='#28a745', description='시험실'):
    """Helper: create a location via form and return the loc_id."""
    client.post('/admin/locations/new', data={
        'name': name, 'color': color, 'description': description,
    })
    r = client.get('/admin/locations')
    ids = re.findall(r'/admin/locations/(loc_\w+)/edit', r.data.decode())
    return ids[-1]


def _create_version(client, name='v1.0.0', description='테스트'):
    """Helper: create a version via form and return the version_id."""
    client.post('/admin/versions/new', data={
        'name': name, 'description': description,
    })
    r = client.get('/admin/versions')
    ids = re.findall(r'/admin/versions/(v_\w+)/edit', r.data.decode())
    return ids[-1]


def _create_task(client, uid_list, loc_id='', version_id='',
                 procedure_id='SYS-001', hours='4'):
    """Helper: create a task via form and return the task_id."""
    if isinstance(uid_list, str):
        uid_list = [uid_list]
    data = {
        'procedure_id': procedure_id,
        'version_id': version_id,
        'assignee_ids': uid_list,
        'location_id': loc_id,
        'section_name': '3.1 시스템',
        'procedure_owner': '담당자',
        'test_list': 'TC-001, TC-002',
        'estimated_hours': hours,
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
        'task_id': tid, 'assignee_ids': uid_list,
        'date': date_str, 'start_time': start, 'end_time': end,
    }
    payload.update(kwargs)
    r = client.post('/schedule/api/blocks', json=payload)
    return r.get_json(), r.status_code
