"""Tests for task routes."""
from tests.conftest import (
    _create_user, _create_task, _create_version,
)


class TestTaskCRUD:
    def test_create_task(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/new', data={
            'doc_id': '100',
            'version_id': '',
            'assignee_names': [uid],
            'location_id': '',
            'doc_name': '시스템',
            'identifiers_json': '[{"id":"TC-001","owners":[],"estimated_minutes":120}]',
            'estimated_minutes': '120',
            'memo': '',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '시스템' in r.data.decode()

    def test_create_task_empty_doc_id(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/new', data={
            'doc_id': '',
            'version_id': '',
            'assignee_names': [uid],
            'location_id': '',
            'doc_name': '',
            'identifiers_json': '',
            'estimated_minutes': '60',
            'memo': '',
        }, follow_redirects=True)
        assert '문서 ID' in r.data.decode()

    def test_task_detail(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.get(f'/tasks/{tid}')
        assert r.status_code == 200
        assert '시스템' in r.data.decode()

    def test_task_detail_nonexistent(self, client):
        r = client.get('/tasks/t_nonexist')
        assert r.status_code == 404

    def test_task_edit(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post(f'/tasks/{tid}/edit', data={
            'doc_id': '200',
            'version_id': '',
            'assignee_names': [uid],
            'location_id': '',
            'doc_name': '수정됨',
            'identifiers_json': '[{"id":"TC-003","owners":[],"estimated_minutes":60}]',
            'estimated_minutes': '60',
            'remaining_minutes': '60',
            'status': 'in_progress',
            'memo': '',
        }, follow_redirects=True)
        assert '수정됨' in r.data.decode()

    def test_task_delete(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post(f'/tasks/{tid}/delete', follow_redirects=True)
        assert r.status_code == 200

    def test_task_filter_by_status(self, client):
        uid = _create_user(client)
        _create_task(client, uid)
        r = client.get('/tasks/?status=waiting')
        assert r.status_code == 200
        assert '시스템' in r.data.decode()
        r = client.get('/tasks/?status=completed')
        assert '시스템' not in r.data.decode()

    def test_task_filter_by_version(self, client):
        uid = _create_user(client)
        vid = _create_version(client, name='v1.0.0')
        _create_task(client, uid, version_id=vid)
        r = client.get(f'/tasks/?version={vid}')
        assert '시스템' in r.data.decode()

    def test_api_create_task(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/api/create', json={
            'doc_id': 300,
            'assignee_names': [uid],
            'identifiers': [{'id': 'TC-X', 'owners': [], 'estimated_minutes': 180}],
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['estimated_minutes'] == 180
        assert data['remaining_minutes'] == 180

    def test_api_create_task_missing_doc_id(self, client):
        r = client.post('/tasks/api/create', json={'doc_id': ''})
        assert r.status_code == 400

    def test_api_task_detail(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.get(f'/tasks/api/{tid}')
        assert r.status_code == 200
        assert r.get_json()['task']['id'] == tid

    def test_api_task_detail_nonexistent(self, client):
        r = client.get('/tasks/api/t_nonexist')
        assert r.status_code == 404

    def test_api_update_task(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.put(f'/tasks/api/{tid}/update', json={
            'doc_id': 400,
            'assignee_names': [uid],
            'identifiers': [{'id': 'TC-E', 'owners': [], 'estimated_minutes': 120}],
            'remaining_minutes': 60,
            'status': 'in_progress',
        })
        assert r.status_code == 200
        assert r.get_json()['estimated_minutes'] == 120

    def test_api_delete_task(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.delete(f'/tasks/api/{tid}/delete')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_tasks_list(self, client):
        r = client.get('/tasks/')
        assert r.status_code == 200

    def test_tasks_new_form(self, client):
        r = client.get('/tasks/new')
        assert r.status_code == 200
