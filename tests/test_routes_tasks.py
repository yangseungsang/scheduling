"""Tests for task routes."""
from tests.conftest import (
    _create_user, _create_task, _create_version,
)


class TestTaskCRUD:
    def test_create_task(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/new', data={
            'procedure_id': 'SYS-001',
            'version_id': '',
            'assignee_ids': [uid],
            'location_id': '',
            'section_name': '3.1 시스템',
            'procedure_owner': '담당자',
            'test_list': 'TC-001',
            'estimated_hours': '4',
            'deadline': '2026-03-15',
            'memo': '',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert 'SYS-001' in r.data.decode()

    def test_create_task_empty_procedure_id(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/new', data={
            'procedure_id': '',
            'version_id': '',
            'assignee_ids': [uid],
            'location_id': '',
            'section_name': '',
            'procedure_owner': '',
            'test_list': '',
            'estimated_hours': '1',
            'deadline': '',
            'memo': '',
        }, follow_redirects=True)
        assert '절차서 식별자를 입력' in r.data.decode()

    def test_task_detail(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.get(f'/tasks/{tid}')
        assert r.status_code == 200
        assert 'SYS-001' in r.data.decode()

    def test_task_detail_nonexistent(self, client):
        r = client.get('/tasks/t_nonexist')
        assert r.status_code == 404

    def test_task_edit(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post(f'/tasks/{tid}/edit', data={
            'procedure_id': 'SYS-002',
            'version_id': '',
            'assignee_ids': [uid],
            'location_id': '',
            'section_name': '4.1 수정',
            'procedure_owner': '수정자',
            'test_list': 'TC-003',
            'estimated_hours': '2',
            'remaining_hours': '2',
            'deadline': '2026-03-20',
            'status': 'in_progress',
            'memo': '',
        }, follow_redirects=True)
        assert 'SYS-002' in r.data.decode()

    def test_task_delete(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post(f'/tasks/{tid}/delete', follow_redirects=True)
        assert r.status_code == 200
        assert 'SYS-001' not in r.data.decode()

    def test_task_filter_by_status(self, client):
        uid = _create_user(client)
        _create_task(client, uid, procedure_id='SYS-FILTER-001')
        r = client.get('/tasks/?status=waiting')
        assert r.status_code == 200
        assert 'SYS-FILTER-001' in r.data.decode()
        r = client.get('/tasks/?status=completed')
        assert 'SYS-FILTER-001' not in r.data.decode()

    def test_task_filter_by_version(self, client):
        uid = _create_user(client)
        vid = _create_version(client, name='v1.0.0')
        _create_task(client, uid, version_id=vid, procedure_id='VER-001')
        _create_task(client, uid, procedure_id='NOVER-001')
        r = client.get(f'/tasks/?version={vid}')
        assert 'VER-001' in r.data.decode()
        assert 'NOVER-001' not in r.data.decode()

    def test_api_create_task(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/api/create', json={
            'procedure_id': 'API-001',
            'assignee_ids': [uid],
            'estimated_hours': 3,
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['procedure_id'] == 'API-001'
        assert data['remaining_hours'] == 3

    def test_api_create_task_missing_procedure_id(self, client):
        r = client.post('/tasks/api/create', json={'procedure_id': ''})
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
            'procedure_id': 'SYS-API-EDIT',
            'assignee_ids': [uid],
            'estimated_hours': 2,
            'remaining_hours': 1,
            'status': 'in_progress',
        })
        assert r.status_code == 200
        assert r.get_json()['procedure_id'] == 'SYS-API-EDIT'

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
