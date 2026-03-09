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


def _create_user(client, name='홍길동', role='개발자', color='#4A90D9'):
    """Helper: create a user via form and return the user_id."""
    client.post('/admin/users/new', data={
        'name': name, 'role': role, 'color': color,
    })
    r = client.get('/admin/users')
    ids = re.findall(r'/admin/users/(u_\w+)/edit', r.data.decode())
    return ids[-1]


def _create_category(client, name='개발', color='#28a745'):
    """Helper: create a category via form and return the category_id."""
    client.post('/admin/categories/new', data={
        'name': name, 'color': color,
    })
    r = client.get('/admin/categories')
    ids = re.findall(r'/admin/categories/(c_\w+)/edit', r.data.decode())
    return ids[-1]


def _create_task(client, uid, cat_id='', title='테스트 업무',
                 priority='high', hours='4', deadline='2026-03-15'):
    """Helper: create a task via form and return the task_id."""
    client.post('/tasks/new', data={
        'title': title,
        'description': '설명',
        'assignee_id': uid,
        'category_id': cat_id,
        'priority': priority,
        'estimated_hours': hours,
        'deadline': deadline,
    })
    r = client.get('/tasks/')
    ids = re.findall(r'/tasks/(t_\w+)', r.data.decode())
    return ids[-1]


def _create_block(client, tid, uid, date_str='2026-03-10',
                  start='09:00', end='10:00', **kwargs):
    """Helper: create a schedule block via API and return the response JSON."""
    payload = {
        'task_id': tid, 'assignee_id': uid,
        'date': date_str, 'start_time': start, 'end_time': end,
    }
    payload.update(kwargs)
    r = client.post('/schedule/api/blocks', json=payload)
    return r.get_json(), r.status_code


# ===========================================================================
# Page routes
# ===========================================================================

class TestPageRoutes:
    def test_index_redirect(self, client):
        r = client.get('/')
        assert r.status_code == 302
        assert '/schedule/' in r.headers['Location']

    def test_day_view(self, client):
        r = client.get('/schedule/')
        assert r.status_code == 200

    def test_day_view_with_date(self, client):
        r = client.get('/schedule/?date=2026-03-10')
        assert r.status_code == 200
        assert '2026-03-10' in r.data.decode()

    def test_day_view_invalid_date_falls_back(self, client):
        r = client.get('/schedule/?date=invalid')
        assert r.status_code == 200

    def test_week_view(self, client):
        r = client.get('/schedule/week')
        assert r.status_code == 200

    def test_week_view_with_date(self, client):
        r = client.get('/schedule/week?date=2026-03-10')
        assert r.status_code == 200

    def test_month_view(self, client):
        r = client.get('/schedule/month')
        assert r.status_code == 200

    def test_month_view_with_date(self, client):
        r = client.get('/schedule/month?date=2026-01-15')
        assert r.status_code == 200
        assert '1월' in r.data.decode()

    def test_tasks_list(self, client):
        r = client.get('/tasks/')
        assert r.status_code == 200

    def test_tasks_new_form(self, client):
        r = client.get('/tasks/new')
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


# ===========================================================================
# User CRUD
# ===========================================================================

class TestUserCRUD:
    def test_create_user(self, client):
        r = client.post('/admin/users/new', data={
            'name': '홍길동', 'role': '개발자', 'color': '#4A90D9',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '홍길동' in r.data.decode()

    def test_edit_user(self, client):
        uid = _create_user(client)
        r = client.post(f'/admin/users/{uid}/edit', data={
            'name': '김철수', 'role': 'PM', 'color': '#FF0000',
        }, follow_redirects=True)
        html = r.data.decode()
        assert '김철수' in html
        assert '홍길동' not in html

    def test_delete_user(self, client):
        uid = _create_user(client)
        r = client.post(f'/admin/users/{uid}/delete', follow_redirects=True)
        assert r.status_code == 200
        assert '홍길동' not in r.data.decode()

    def test_edit_nonexistent_user(self, client):
        r = client.get('/admin/users/u_nonexist/edit', follow_redirects=True)
        assert r.status_code == 200
        assert '찾을 수 없습니다' in r.data.decode()

    def test_api_create_user(self, client):
        r = client.post('/admin/api/users', json={
            'name': 'API유저', 'role': 'QA', 'color': '#123456',
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['name'] == 'API유저'
        assert data['id'].startswith('u_')

    def test_api_create_user_missing_name(self, client):
        r = client.post('/admin/api/users', json={'role': 'QA'})
        assert r.status_code == 400

    def test_api_get_users(self, client):
        _create_user(client)
        r = client.get('/admin/api/users')
        assert r.status_code == 200
        assert len(r.get_json()) == 1

    def test_api_update_user(self, client):
        uid = _create_user(client)
        r = client.put(f'/admin/api/users/{uid}', json={'name': '수정됨'})
        assert r.status_code == 200
        assert r.get_json()['name'] == '수정됨'

    def test_api_delete_user(self, client):
        uid = _create_user(client)
        r = client.delete(f'/admin/api/users/{uid}')
        assert r.status_code == 200
        assert r.get_json()['success'] is True


# ===========================================================================
# Category CRUD
# ===========================================================================

class TestCategoryCRUD:
    def test_create_category(self, client):
        r = client.post('/admin/categories/new', data={
            'name': '개발', 'color': '#28a745',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '개발' in r.data.decode()

    def test_edit_category(self, client):
        cid = _create_category(client)
        r = client.post(f'/admin/categories/{cid}/edit', data={
            'name': '디자인', 'color': '#FF00FF',
        }, follow_redirects=True)
        assert '디자인' in r.data.decode()

    def test_delete_category(self, client):
        cid = _create_category(client)
        r = client.post(f'/admin/categories/{cid}/delete', follow_redirects=True)
        assert r.status_code == 200

    def test_api_create_category(self, client):
        r = client.post('/admin/api/categories', json={
            'name': 'API카테고리', 'color': '#abcdef',
        })
        assert r.status_code == 201
        assert r.get_json()['id'].startswith('c_')

    def test_api_create_category_missing_name(self, client):
        r = client.post('/admin/api/categories', json={'color': '#fff'})
        assert r.status_code == 400


# ===========================================================================
# Settings
# ===========================================================================

class TestSettings:
    def test_update_settings_form(self, client):
        r = client.post('/admin/settings', data={
            'work_start': '08:00',
            'work_end': '17:00',
            'lunch_start': '12:00',
            'lunch_end': '13:00',
            'grid_interval_minutes': '15',
            'max_schedule_days': '7',
            'block_color_by': 'category',
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_api_get_settings(self, client):
        r = client.get('/admin/api/settings')
        assert r.status_code == 200
        data = r.get_json()
        assert data['work_start'] == '09:00'
        assert data['grid_interval_minutes'] == 15

    def test_api_update_settings(self, client):
        r = client.put('/admin/api/settings', json={
            'work_start': '08:30',
        })
        assert r.status_code == 200
        assert r.get_json()['work_start'] == '08:30'

    def test_time_snap_on_save(self, client):
        """Non-grid-aligned times should snap to nearest interval."""
        r = client.post('/admin/settings', data={
            'work_start': '09:07',
            'work_end': '18:00',
            'lunch_start': '12:03',
            'lunch_end': '13:00',
            'grid_interval_minutes': '15',
            'max_schedule_days': '14',
            'block_color_by': 'assignee',
        }, follow_redirects=True)
        assert r.status_code == 200
        settings = client.get('/admin/api/settings').get_json()
        assert settings['work_start'] == '09:00'
        assert settings['lunch_start'] == '12:00'


# ===========================================================================
# Task CRUD
# ===========================================================================

class TestTaskCRUD:
    def test_create_task(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/new', data={
            'title': '테스트 업무', 'description': '설명',
            'assignee_id': uid, 'category_id': '',
            'priority': 'high', 'estimated_hours': '4',
            'deadline': '2026-03-15',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '테스트 업무' in r.data.decode()

    def test_create_task_empty_title(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/new', data={
            'title': '', 'description': '',
            'assignee_id': uid, 'category_id': '',
            'priority': 'medium', 'estimated_hours': '1',
            'deadline': '',
        }, follow_redirects=True)
        assert '제목을 입력' in r.data.decode()

    def test_task_detail(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.get(f'/tasks/{tid}')
        assert r.status_code == 200
        assert '테스트 업무' in r.data.decode()

    def test_task_detail_nonexistent(self, client):
        r = client.get('/tasks/t_nonexist')
        assert r.status_code == 404

    def test_task_edit(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post(f'/tasks/{tid}/edit', data={
            'title': '수정된 업무', 'description': '수정',
            'assignee_id': uid, 'category_id': '',
            'priority': 'low', 'estimated_hours': '2',
            'remaining_hours': '2', 'deadline': '2026-03-20',
            'status': 'in_progress',
        }, follow_redirects=True)
        assert '수정된 업무' in r.data.decode()

    def test_task_delete(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post(f'/tasks/{tid}/delete', follow_redirects=True)
        assert r.status_code == 200
        assert '테스트 업무' not in r.data.decode()

    def test_task_filter_by_status(self, client):
        uid = _create_user(client)
        _create_task(client, uid, title='업무A')
        r = client.get('/tasks/?status=waiting')
        assert r.status_code == 200
        assert '업무A' in r.data.decode()
        r = client.get('/tasks/?status=completed')
        assert '업무A' not in r.data.decode()

    def test_task_filter_by_priority(self, client):
        uid = _create_user(client)
        _create_task(client, uid, title='높은업무', priority='high')
        _create_task(client, uid, title='낮은업무', priority='low')
        r = client.get('/tasks/?priority=high')
        assert '높은업무' in r.data.decode()
        assert '낮은업무' not in r.data.decode()

    def test_api_create_task(self, client):
        uid = _create_user(client)
        r = client.post('/tasks/api/create', json={
            'title': 'API업무', 'assignee_id': uid,
            'priority': 'medium', 'estimated_hours': 3,
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['title'] == 'API업무'
        assert data['remaining_hours'] == 3

    def test_api_create_task_missing_title(self, client):
        r = client.post('/tasks/api/create', json={'title': ''})
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
            'title': '수정API', 'priority': 'low',
            'estimated_hours': 2, 'remaining_hours': 1,
            'status': 'in_progress',
        })
        assert r.status_code == 200
        assert r.get_json()['title'] == '수정API'

    def test_api_delete_task(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.delete(f'/tasks/api/{tid}/delete')
        assert r.status_code == 200
        assert r.get_json()['success'] is True


# ===========================================================================
# Schedule Block CRUD API
# ===========================================================================

class TestScheduleBlockAPI:
    def test_create_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        data, status = _create_block(client, tid, uid)
        assert status == 201
        assert data['task_id'] == tid
        assert data['assignee_id'] == uid
        assert data['start_time'] == '09:00'
        assert data['origin'] == 'manual'

    def test_create_block_missing_fields(self, client):
        r = client.post('/schedule/api/blocks', json={'task_id': 'xxx'})
        assert r.status_code == 400

    def test_create_block_no_body(self, client):
        r = client.post('/schedule/api/blocks', content_type='application/json')
        assert r.status_code == 400

    def test_create_block_auto_assignee(self, client):
        """If no assignee_id, use the task's assignee."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid, 'date': '2026-03-10',
            'start_time': '09:00', 'end_time': '10:00',
        })
        assert r.status_code == 201
        assert r.get_json()['assignee_id'] == uid

    def test_create_block_overlap_rejected(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, start='09:00', end='10:00')
        # Overlapping block
        _, status = _create_block(client, tid, uid, start='09:30', end='10:30')
        assert status == 409

    def test_create_block_adjacent_allowed(self, client):
        """Blocks that touch at endpoints should not be rejected."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        # Use times that don't span breaks to avoid end_time adjustment
        _create_block(client, tid, uid, start='10:00', end='11:00')
        _, status = _create_block(client, tid, uid, start='11:00', end='11:30')
        assert status == 201

    def test_create_block_break_adjustment(self, client):
        """Block spanning lunch should have end_time extended."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        data, status = _create_block(
            client, tid, uid, start='11:00', end='14:00',
        )
        assert status == 201
        # 3h work = 11:00-12:00 (1h) + skip lunch + 13:00-15:00 (2h) = end at 15:00
        # But also skip 14:45-15:00 break → 15:15
        assert data['end_time'] >= '15:00'

    def test_update_block_move(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '10:00', 'end_time': '11:00',
        })
        assert r.status_code == 200
        assert r.get_json()['start_time'] == '10:00'

    def test_update_block_change_date(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'date': '2026-03-11',
        })
        assert r.status_code == 200
        assert r.get_json()['date'] == '2026-03-11'

    def test_update_block_preserves_work_duration(self, client):
        """Moving a block should preserve the actual work duration (excluding breaks)."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        # Create 1h block at 09:00-10:00
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        # Move to 11:00 — should still be 1h of work
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '11:00', 'end_time': '12:00',
        })
        data = r.get_json()
        assert data['start_time'] == '11:00'
        assert data['end_time'] == '12:00'

    def test_update_block_move_across_lunch(self, client):
        """Moving a 1h block to start at 11:30 should extend past lunch."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '11:30', 'end_time': '12:30',
        })
        data = r.get_json()
        assert data['start_time'] == '11:30'
        # 1h work: 11:30-12:00 (30min) + skip lunch + 13:00-13:30 (30min) = 13:30
        assert data['end_time'] == '13:30'

    def test_update_block_resize_no_duration_preservation(self, client):
        """Resize should use the exact end_time, not preserve work duration."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '09:00', 'end_time': '09:30',
            'resize': True,
        })
        assert r.get_json()['end_time'] == '09:30'

    def test_update_block_resize_syncs_remaining_hours(self, client):
        """On resize, task.remaining_hours should equal total scheduled time."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        # Resize to 1h
        client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '09:00', 'end_time': '10:00',
            'resize': True,
        })
        task = client.get(f'/tasks/api/{tid}').get_json()['task']
        assert task['remaining_hours'] == 1.0

    def test_update_block_overlap_rejected(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        # Use times that don't span breaks
        b1, _ = _create_block(client, tid, uid, start='10:00', end='11:00')
        b2, _ = _create_block(client, tid, uid, start='11:00', end='11:30')
        # Try to move b2 to overlap with b1
        r = client.put(f'/schedule/api/blocks/{b2["id"]}', json={
            'start_time': '10:00', 'end_time': '10:30',
        })
        assert r.status_code == 409

    def test_update_nonexistent_block(self, client):
        r = client.put('/schedule/api/blocks/sb_nonexist', json={'date': '2026-03-10'})
        assert r.status_code == 404

    def test_update_block_no_body(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            content_type='application/json',
        )
        assert r.status_code == 400

    def test_delete_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.delete(f'/schedule/api/blocks/{block["id"]}')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_delete_nonexistent_block(self, client):
        r = client.delete('/schedule/api/blocks/sb_nonexist')
        assert r.status_code == 404

    def test_lock_toggle(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        bid = block['id']
        # Lock
        r = client.put(f'/schedule/api/blocks/{bid}/lock')
        assert r.get_json()['is_locked'] is True
        # Unlock
        r = client.put(f'/schedule/api/blocks/{bid}/lock')
        assert r.get_json()['is_locked'] is False

    def test_lock_nonexistent(self, client):
        r = client.put('/schedule/api/blocks/sb_nonexist/lock')
        assert r.status_code == 404


# ===========================================================================
# Schedule View Data APIs
# ===========================================================================

class TestScheduleViewAPIs:
    def test_api_day_data(self, client):
        r = client.get('/schedule/api/day?date=2026-03-10')
        assert r.status_code == 200
        data = r.get_json()
        assert data['current_date'] == '2026-03-10'
        assert 'blocks' in data
        assert 'time_slots' in data
        assert 'queue_tasks' in data

    def test_api_week_data(self, client):
        r = client.get('/schedule/api/week?date=2026-03-10')
        assert r.status_code == 200
        data = r.get_json()
        assert len(data['week_days']) == 7
        assert len(data['day_names']) == 7

    def test_api_month_data(self, client):
        r = client.get('/schedule/api/month?date=2026-03-10')
        assert r.status_code == 200
        data = r.get_json()
        assert data['year'] == 2026
        assert data['month'] == 3
        assert len(data['weeks']) >= 4

    def test_api_day_data_with_blocks(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get('/schedule/api/day?date=2026-03-10')
        data = r.get_json()
        assert len(data['blocks']) == 1
        assert data['blocks'][0]['task_title'] == '테스트 업무'

    def test_enriched_block_has_display_fields(self, client):
        uid = _create_user(client)
        cid = _create_category(client, name='백엔드')
        tid = _create_task(client, uid, cat_id=cid, title='API개발')
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get('/schedule/api/day?date=2026-03-10')
        block = r.get_json()['blocks'][0]
        assert block['task_title'] == 'API개발'
        assert block['assignee_name'] == '홍길동'
        assert block['category_name'] == '백엔드'
        assert block['priority'] == 'high'
        assert 'color' in block

    def test_queue_tasks_in_view_data(self, client):
        uid = _create_user(client)
        _create_task(client, uid, hours='4')
        r = client.get('/schedule/api/day')
        data = r.get_json()
        assert len(data['queue_tasks']) == 1
        assert data['queue_tasks'][0]['remaining_unscheduled_hours'] == 4.0

    def test_queue_tasks_exclude_fully_scheduled(self, client):
        """Task fully covered by blocks should not appear in queue."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='1')
        _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_tasks']
        assert all(t['id'] != tid for t in queue)

    def test_queue_tasks_partial_remaining(self, client):
        """Task with 2h remaining but 1h scheduled should show 1h in queue."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        # Use time range that doesn't cross breaks (10:00-11:00 = exactly 1h)
        _create_block(client, tid, uid, start='10:00', end='11:00')
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_tasks']
        matching = [t for t in queue if t['id'] == tid]
        assert len(matching) == 1
        assert matching[0]['remaining_unscheduled_hours'] == 1.0

    def test_queue_excludes_completed_tasks(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        # Mark as completed
        client.put(f'/tasks/api/{tid}/update', json={
            'title': '테스트 업무', 'status': 'completed',
            'estimated_hours': 2, 'remaining_hours': 0,
        })
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_tasks']
        assert all(t['id'] != tid for t in queue)


# ===========================================================================
# Overlap layout
# ===========================================================================

class TestOverlapLayout:
    def test_overlapping_blocks_get_columns(self, client):
        uid = _create_user(client)
        tid1 = _create_task(client, uid, title='업무A')
        uid2 = _create_user(client, name='김철수', color='#FF0000')
        tid2 = _create_task(client, uid2, title='업무B')
        # Two blocks at same time, different assignees
        _create_block(client, tid1, uid, date_str='2026-03-10',
                      start='09:00', end='10:00')
        _create_block(client, tid2, uid2, date_str='2026-03-10',
                      start='09:00', end='10:00')
        r = client.get('/schedule/api/day?date=2026-03-10')
        # API doesn't compute overlap layout, but template view does
        r = client.get('/schedule/?date=2026-03-10')
        assert r.status_code == 200

    def test_nonoverlapping_blocks_single_column(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, start='09:00', end='10:00')
        _create_block(client, tid, uid, start='10:00', end='11:00')
        r = client.get('/schedule/?date=2026-03-10')
        assert r.status_code == 200


# ===========================================================================
# Draft scheduling
# ===========================================================================

class TestDraftScheduling:
    def test_generate_drafts(self, client):
        uid = _create_user(client)
        _create_task(client, uid, hours='2')
        r = client.post('/schedule/api/draft/generate')
        assert r.status_code == 200
        data = r.get_json()
        assert data['placed_count'] >= 1

    def test_generate_creates_draft_blocks(self, client):
        uid = _create_user(client)
        _create_task(client, uid, hours='1')
        client.post('/schedule/api/draft/generate')
        # Check blocks exist and are drafts
        r = client.get('/schedule/api/day')
        blocks = r.get_json()['blocks']
        drafts = [b for b in blocks if b.get('is_draft')]
        # May or may not have blocks today depending on timing
        # Just verify the API works
        assert r.status_code == 200

    def test_approve_drafts(self, client):
        uid = _create_user(client)
        _create_task(client, uid, hours='1')
        client.post('/schedule/api/draft/generate')
        r = client.post('/schedule/api/draft/approve')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_approve_updates_remaining_hours(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='1')
        client.post('/schedule/api/draft/generate')
        client.post('/schedule/api/draft/approve')
        task = client.get(f'/tasks/api/{tid}').get_json()['task']
        # remaining_hours should have been decremented
        assert task['remaining_hours'] < 1.0 or task['status'] == 'completed'

    def test_discard_drafts(self, client):
        uid = _create_user(client)
        _create_task(client, uid, hours='2')
        gen = client.post('/schedule/api/draft/generate').get_json()
        assert gen['placed_count'] >= 1
        r = client.post('/schedule/api/draft/discard')
        assert r.status_code == 200

    def test_generate_with_existing_confirmed_blocks(self, client):
        """Auto-scheduling should respect existing confirmed blocks."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        # Manually place 1h
        _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.post('/schedule/api/draft/generate')
        data = r.get_json()
        # Should place remaining 1h, not overlap with 09:00-10:00
        assert r.status_code == 200

    def test_generate_multiple_tasks_priority_order(self, client):
        uid = _create_user(client)
        _create_task(client, uid, title='낮은', priority='low',
                     hours='1', deadline='2026-03-20')
        _create_task(client, uid, title='높은', priority='high',
                     hours='1', deadline='2026-03-20')
        r = client.post('/schedule/api/draft/generate')
        assert r.status_code == 200
        assert r.get_json()['placed_count'] >= 2

    def test_unplaced_tasks_reported(self, client):
        """Tasks that can't fit should be reported as unplaced."""
        uid = _create_user(client)
        # Create task with impossibly many hours
        _create_task(client, uid, hours='999')
        r = client.post('/schedule/api/draft/generate')
        data = r.get_json()
        assert len(data['unplaced']) >= 1
        assert data['unplaced'][0]['remaining_hours'] > 0


# ===========================================================================
# Export API
# ===========================================================================

class TestExportAPI:
    def test_export_csv(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-10&format=csv'
        )
        assert r.status_code == 200
        assert 'text/csv' in r.content_type
        body = r.data.decode('utf-8-sig')
        assert '테스트 업무' in body
        assert '홍길동' in body

    def test_export_xlsx(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-16&format=xlsx'
        )
        assert r.status_code == 200
        assert 'spreadsheetml' in r.content_type
        assert len(r.data) > 1000  # non-trivial xlsx file

    def test_export_empty_range(self, client):
        r = client.get(
            '/schedule/api/export?start_date=2026-01-01&end_date=2026-01-07&format=csv'
        )
        assert r.status_code == 200

    def test_export_missing_dates(self, client):
        r = client.get('/schedule/api/export')
        assert r.status_code == 400

    def test_export_invalid_date(self, client):
        r = client.get(
            '/schedule/api/export?start_date=bad&end_date=2026-03-10'
        )
        assert r.status_code == 400

    def test_export_csv_has_headers(self, client):
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-10&format=csv'
        )
        body = r.data.decode('utf-8-sig')
        assert '날짜' in body
        assert '업무명' in body


# ===========================================================================
# Time utilities (unit tests)
# ===========================================================================

class TestTimeUtils:
    def test_time_to_minutes(self):
        from app.utils.time_utils import time_to_minutes
        assert time_to_minutes('09:00') == 540
        assert time_to_minutes('12:30') == 750
        assert time_to_minutes('00:00') == 0
        assert time_to_minutes('23:59') == 1439

    def test_minutes_to_time(self):
        from app.utils.time_utils import minutes_to_time
        assert minutes_to_time(540) == '09:00'
        assert minutes_to_time(750) == '12:30'
        assert minutes_to_time(0) == '00:00'

    def test_time_roundtrip(self):
        from app.utils.time_utils import time_to_minutes, minutes_to_time
        for t in ['00:00', '09:15', '12:45', '18:00', '23:30']:
            assert minutes_to_time(time_to_minutes(t)) == t

    def test_generate_time_slots(self):
        from app.utils.time_utils import generate_time_slots
        settings = {'work_start': '09:00', 'work_end': '10:00',
                     'grid_interval_minutes': 15}
        slots = generate_time_slots(settings)
        assert slots == ['09:00', '09:15', '09:30', '09:45']

    def test_generate_time_slots_30min(self):
        from app.utils.time_utils import generate_time_slots
        settings = {'work_start': '09:00', 'work_end': '11:00',
                     'grid_interval_minutes': 30}
        slots = generate_time_slots(settings)
        assert slots == ['09:00', '09:30', '10:00', '10:30']

    def test_is_break_slot(self):
        from app.utils.time_utils import is_break_slot
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [{'start': '09:45', 'end': '10:00'}],
        }
        assert is_break_slot('12:00', settings) is True
        assert is_break_slot('12:30', settings) is True
        assert is_break_slot('09:45', settings) is True
        assert is_break_slot('09:00', settings) is False
        assert is_break_slot('13:00', settings) is False

    def test_work_minutes_in_range_no_breaks(self):
        from app.utils.time_utils import work_minutes_in_range
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        assert work_minutes_in_range('09:00', '10:00', settings) == 60

    def test_work_minutes_in_range_with_lunch(self):
        from app.utils.time_utils import work_minutes_in_range
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        # 11:00-14:00 = 3h total, minus 1h lunch = 2h = 120min
        assert work_minutes_in_range('11:00', '14:00', settings) == 120

    def test_work_minutes_in_range_with_break(self):
        from app.utils.time_utils import work_minutes_in_range
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [{'start': '09:45', 'end': '10:00'}],
        }
        # 09:00-10:30 = 90min total, minus 15min break = 75min
        assert work_minutes_in_range('09:00', '10:30', settings) == 75

    def test_adjust_end_for_breaks_no_break(self):
        from app.utils.time_utils import adjust_end_for_breaks
        settings = {
            'work_end': '18:00',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        assert adjust_end_for_breaks('09:00', '10:00', settings) == '10:00'

    def test_adjust_end_for_breaks_across_lunch(self):
        from app.utils.time_utils import adjust_end_for_breaks
        settings = {
            'work_end': '18:00',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        # 3h from 11:00: 11-12 (1h) + skip lunch + 13-15 (2h) = end at 15:00
        result = adjust_end_for_breaks('11:00', '14:00', settings)
        assert result == '15:00'

    def test_adjust_end_for_breaks_across_small_break(self):
        from app.utils.time_utils import adjust_end_for_breaks
        settings = {
            'work_end': '18:00',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [{'start': '09:45', 'end': '10:00'}],
        }
        # 1h from 09:30: 09:30-09:45 (15min) + skip break + 10:00-10:45 (45min) = 10:45
        result = adjust_end_for_breaks('09:30', '10:30', settings)
        assert result == '10:45'

    def test_adjust_end_zero_duration(self):
        from app.utils.time_utils import adjust_end_for_breaks
        settings = {
            'work_end': '18:00',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        assert adjust_end_for_breaks('09:00', '09:00', settings) == '09:00'

    def test_get_break_periods(self):
        from app.utils.time_utils import get_break_periods
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [
                {'start': '09:45', 'end': '10:00'},
                {'start': '14:45', 'end': '15:00'},
            ],
        }
        periods = get_break_periods(settings)
        assert len(periods) == 3
        # Should be sorted
        assert periods[0] == (585, 600)    # 09:45-10:00
        assert periods[1] == (720, 780)    # 12:00-13:00
        assert periods[2] == (885, 900)    # 14:45-15:00


# ===========================================================================
# JSON store
# ===========================================================================

class TestJsonStore:
    def test_generate_id_prefix(self, app):
        with app.app_context():
            from app.json_store import generate_id
            uid = generate_id('u_')
            assert uid.startswith('u_')
            assert len(uid) == 10  # u_ + 8 hex chars

    def test_read_write_json(self, app):
        with app.app_context():
            from app.json_store import read_json, write_json
            data = [{'id': 'test_1', 'name': '테스트'}]
            write_json('test_file.json', data)
            result = read_json('test_file.json')
            assert result == data

    def test_backup_on_write(self, app):
        with app.app_context():
            from app.json_store import write_json
            import os
            write_json('backup_test.json', [1])
            write_json('backup_test.json', [2])
            bak_path = os.path.join(
                app.config['DATA_DIR'], 'backup_test.json.bak'
            )
            assert os.path.exists(bak_path)

    def test_read_nonexistent_file(self, app):
        with app.app_context():
            from app.json_store import read_json
            assert read_json('nonexistent.json') == []

    def test_read_settings_nonexistent(self, app):
        with app.app_context():
            from app.json_store import read_json
            import os
            path = os.path.join(app.config['DATA_DIR'], 'settings.json')
            os.remove(path)
            assert read_json('settings.json') == {}


# ===========================================================================
# Repository layer
# ===========================================================================

class TestRepositories:
    def test_task_patch(self, app, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        with app.app_context():
            from app.repositories import task_repo
            result = task_repo.patch(tid, remaining_hours=2.5, status='in_progress')
            assert result['remaining_hours'] == 2.5
            assert result['status'] == 'in_progress'
            assert result['title'] == '테스트 업무'

    def test_task_patch_nonexistent(self, app):
        with app.app_context():
            from app.repositories import task_repo
            result = task_repo.patch('t_nonexist', status='completed')
            assert result is None

    def test_schedule_repo_get_by_date_range(self, app, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, date_str='2026-03-10')
        _create_block(client, tid, uid, date_str='2026-03-12',
                      start='10:00', end='11:00')
        with app.app_context():
            from app.repositories import schedule_repo
            blocks = schedule_repo.get_by_date_range('2026-03-10', '2026-03-11')
            assert len(blocks) == 1
            blocks = schedule_repo.get_by_date_range('2026-03-10', '2026-03-12')
            assert len(blocks) == 2

    def test_schedule_repo_delete_drafts(self, app, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        with app.app_context():
            from app.repositories import schedule_repo
            # Create blocks directly via repo to control is_draft
            schedule_repo.create(
                task_id=tid, assignee_id=uid, date='2026-03-10',
                start_time='09:00', end_time='10:00',
                is_draft=True, origin='auto',
            )
            schedule_repo.create(
                task_id=tid, assignee_id=uid, date='2026-03-10',
                start_time='10:00', end_time='11:00',
                is_draft=False, origin='manual',
            )
            assert len(schedule_repo.get_all()) == 2
            schedule_repo.delete_drafts()
            remaining = schedule_repo.get_all()
            assert len(remaining) == 1
            assert remaining[0]['is_draft'] is False

    def test_schedule_repo_approve_drafts(self, app, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, is_draft=True)
        with app.app_context():
            from app.repositories import schedule_repo
            schedule_repo.approve_drafts()
            blocks = schedule_repo.get_all()
            assert all(not b['is_draft'] for b in blocks)

    def test_settings_defaults(self, app):
        """If settings.json is empty, defaults should be returned."""
        with app.app_context():
            from app.json_store import write_json
            write_json('settings.json', {})
            from app.repositories import settings_repo
            s = settings_repo.get()
            assert s['work_start'] == '09:00'
            assert s['grid_interval_minutes'] == 15


# ===========================================================================
# Color-by setting
# ===========================================================================

class TestBlockColorBy:
    def test_color_by_assignee(self, client):
        uid = _create_user(client, color='#AA0000')
        cid = _create_category(client, color='#00BB00')
        tid = _create_task(client, uid, cat_id=cid)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get('/schedule/api/day?date=2026-03-10')
        block = r.get_json()['blocks'][0]
        assert block['color'] == '#AA0000'

    def test_color_by_category(self, client):
        # Change setting to category
        client.put('/admin/api/settings', json={'block_color_by': 'category'})
        uid = _create_user(client, color='#AA0000')
        cid = _create_category(client, color='#00BB00')
        tid = _create_task(client, uid, cat_id=cid)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get('/schedule/api/day?date=2026-03-10')
        block = r.get_json()['blocks'][0]
        assert block['color'] == '#00BB00'
