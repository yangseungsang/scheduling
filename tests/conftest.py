import json
import re

import pytest

from app import create_app
from app.repositories import JsonDomainRepository


DEFAULT_SETTINGS = {
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
    'block_color_by': 'status',
}


def configure_test_storage(application, tmp_path, settings=None):
    data_dir = tmp_path / 'domain_data'
    application.config['DOMAIN_DATA_DIR'] = str(data_dir)
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    repository.replace_settings(settings or DEFAULT_SETTINGS)
    return application


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def app(tmp_path):
    """Create an app with an isolated domain data path."""
    application = create_app()
    application.config['TESTING'] = True
    configure_test_storage(application, tmp_path)
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


# ===========================================================================
# Helper functions
# ===========================================================================

def _assignee_name(client, name='홍길동', role='개발자', color='#4A90D9'):
    """Return an assignee name stored directly on procedures and blocks."""
    return name


def _create_location(client, name='A', color='#28a745', description='시험실'):
    """Return the location name stored directly on procedures and blocks."""
    return name


_PROCEDURE_DOCUMENT_COUNTER = [100]


def _create_procedure(client, uid_list, loc_id='', document_id=None, hours='4'):
    """Helper: create a procedure via form and return the procedure_id.

    `uid_list`는 담당자 이름 리스트다.
    """
    if isinstance(uid_list, str):
        uid_list = [uid_list]
    if document_id is None:
        _PROCEDURE_DOCUMENT_COUNTER[0] += 1
        document_id = _PROCEDURE_DOCUMENT_COUNTER[0]
    total_minutes = round(float(hours) * 60)
    test_items = [
        {'id': 'TC-001', 'estimated_minutes': total_minutes // 2, 'owners': []},
        {'id': 'TC-002', 'estimated_minutes': total_minutes - total_minutes // 2, 'owners': []},
    ]
    data = {
        'document_id': str(document_id),
        'assignee_names': uid_list,
        'location_name': loc_id,
        'document_name': '시스템',
        'test_items_json': json.dumps(test_items),
        'estimated_minutes': str(total_minutes),
        'memo': '',
    }
    client.post('/procedures/new', data=data)
    r = client.get('/procedures/')
    ids = re.findall(r'/procedures/(tp_\w+)', r.data.decode())
    return ids[-1]


def _create_block(client, tid, uid_list, date_str='2026-03-10',
                  start='09:00', end='10:00', **kwargs):
    """Helper: create a schedule block via API and return (json, status_code)."""
    if isinstance(uid_list, str):
        uid_list = [uid_list]
    payload = {
        'procedure_id': tid, 'assignee_names': uid_list,
        'date': date_str, 'start_time': start, 'end_time': end,
    }
    payload.update(kwargs)
    r = client.post('/schedule/api/blocks', json=payload)
    return r.get_json(), r.status_code
