import json
import os
import shutil
import tempfile

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    """Create app with a temporary data directory."""
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)

    # Seed default files
    for name in ('users', 'categories', 'tasks', 'schedule_blocks'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)

    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '09:00',
            'work_end': '18:00',
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


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

class TestPageRoutes:
    def test_index_redirect(self, client):
        r = client.get('/')
        assert r.status_code == 302

    def test_day_view(self, client):
        r = client.get('/schedule/')
        assert r.status_code == 200
        assert '일간' in r.data.decode() or '오늘' in r.data.decode()

    def test_week_view(self, client):
        r = client.get('/schedule/week')
        assert r.status_code == 200

    def test_month_view(self, client):
        r = client.get('/schedule/month')
        assert r.status_code == 200

    def test_tasks_list(self, client):
        r = client.get('/tasks/')
        assert r.status_code == 200

    def test_admin_users(self, client):
        r = client.get('/admin/users')
        assert r.status_code == 200

    def test_admin_categories(self, client):
        r = client.get('/admin/categories')
        assert r.status_code == 200

    def test_admin_settings(self, client):
        r = client.get('/admin/settings')
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

class TestUserCRUD:
    def test_create_user(self, client):
        r = client.post('/admin/users/new', data={
            'name': '홍길동', 'role': '개발자', 'color': '#4A90D9'
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '홍길동' in r.data.decode()

    def test_edit_user(self, client):
        # Create first
        client.post('/admin/users/new', data={
            'name': '홍길동', 'role': '개발자', 'color': '#4A90D9'
        })
        # Get user id
        r = client.get('/admin/users')
        html = r.data.decode()
        import re
        uid = re.search(r'/admin/users/(u_\w+)/edit', html).group(1)

        r = client.post(f'/admin/users/{uid}/edit', data={
            'name': '김철수', 'role': 'PM', 'color': '#FF0000'
        }, follow_redirects=True)
        assert '김철수' in r.data.decode()


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------

class TestCategoryCRUD:
    def test_create_category(self, client):
        r = client.post('/admin/categories/new', data={
            'name': '개발', 'color': '#28a745'
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '개발' in r.data.decode()


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

class TestTaskCRUD:
    def _create_user(self, client):
        client.post('/admin/users/new', data={
            'name': '홍길동', 'role': '개발자', 'color': '#4A90D9'
        })
        r = client.get('/admin/users')
        import re
        return re.search(r'u_\w+', r.data.decode()).group()

    def test_create_task(self, client):
        uid = self._create_user(client)
        r = client.post('/tasks/new', data={
            'title': '테스트 업무',
            'description': '설명',
            'assignee_id': uid,
            'category_id': '',
            'priority': 'high',
            'estimated_hours': '4',
            'deadline': '2026-03-15',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '테스트 업무' in r.data.decode()

    def test_task_detail(self, client):
        uid = self._create_user(client)
        client.post('/tasks/new', data={
            'title': '테스트 업무',
            'description': '설명',
            'assignee_id': uid,
            'category_id': '',
            'priority': 'high',
            'estimated_hours': '4',
            'deadline': '2026-03-15',
        })
        r = client.get('/tasks/')
        import re
        tid = re.search(r'/tasks/(t_\w+)', r.data.decode()).group(1)
        r = client.get(f'/tasks/{tid}')
        assert r.status_code == 200
        assert '테스트 업무' in r.data.decode()


# ---------------------------------------------------------------------------
# Schedule API
# ---------------------------------------------------------------------------

class TestScheduleAPI:
    def _setup_task(self, client):
        """Create a user and task, return (user_id, task_id)."""
        client.post('/admin/users/new', data={
            'name': '홍길동', 'role': '개발자', 'color': '#4A90D9'
        })
        r = client.get('/admin/users')
        import re
        uid = re.search(r'u_\w+', r.data.decode()).group()

        client.post('/tasks/new', data={
            'title': '테스트 업무',
            'description': '',
            'assignee_id': uid,
            'category_id': '',
            'priority': 'high',
            'estimated_hours': '4',
            'deadline': '2026-03-15',
        })
        r = client.get('/tasks/')
        tid = re.search(r't_\w+', r.data.decode()).group()
        return uid, tid

    def test_create_block(self, client):
        uid, tid = self._setup_task(client)
        r = client.post('/schedule/api/blocks',
                        json={
                            'task_id': tid,
                            'assignee_id': uid,
                            'date': '2026-03-10',
                            'start_time': '09:00',
                            'end_time': '10:00',
                        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['task_id'] == tid

    def test_update_block(self, client):
        uid, tid = self._setup_task(client)
        r = client.post('/schedule/api/blocks',
                        json={
                            'task_id': tid,
                            'assignee_id': uid,
                            'date': '2026-03-10',
                            'start_time': '09:00',
                            'end_time': '10:00',
                        })
        block_id = r.get_json()['id']

        r = client.put(f'/schedule/api/blocks/{block_id}',
                       json={'start_time': '10:00', 'end_time': '11:00'})
        assert r.status_code == 200
        assert r.get_json()['start_time'] == '10:00'

    def test_delete_block(self, client):
        uid, tid = self._setup_task(client)
        r = client.post('/schedule/api/blocks',
                        json={
                            'task_id': tid,
                            'assignee_id': uid,
                            'date': '2026-03-10',
                            'start_time': '09:00',
                            'end_time': '10:00',
                        })
        block_id = r.get_json()['id']

        r = client.delete(f'/schedule/api/blocks/{block_id}')
        assert r.status_code == 200

    def test_lock_toggle(self, client):
        uid, tid = self._setup_task(client)
        r = client.post('/schedule/api/blocks',
                        json={
                            'task_id': tid,
                            'assignee_id': uid,
                            'date': '2026-03-10',
                            'start_time': '09:00',
                            'end_time': '10:00',
                        })
        block_id = r.get_json()['id']

        r = client.put(f'/schedule/api/blocks/{block_id}/lock')
        assert r.get_json()['is_locked'] is True

        r = client.put(f'/schedule/api/blocks/{block_id}/lock')
        assert r.get_json()['is_locked'] is False

    def test_draft_generate(self, client):
        uid, tid = self._setup_task(client)
        r = client.post('/schedule/api/draft/generate')
        assert r.status_code == 200
        data = r.get_json()
        assert 'placed_count' in data

    def test_draft_approve(self, client):
        uid, tid = self._setup_task(client)
        client.post('/schedule/api/draft/generate')
        r = client.post('/schedule/api/draft/approve')
        assert r.status_code == 200

    def test_draft_discard(self, client):
        uid, tid = self._setup_task(client)
        client.post('/schedule/api/draft/generate')
        r = client.post('/schedule/api/draft/discard')
        assert r.status_code == 200
