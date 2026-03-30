"""Tests for admin routes."""
from tests.conftest import (
    _create_user, _create_location, _create_version,
)


class TestPageRoutes:
    def test_admin_users(self, client):
        r = client.get('/admin/users')
        assert r.status_code == 200

    def test_admin_locations(self, client):
        r = client.get('/admin/locations')
        assert r.status_code == 200

    def test_admin_versions(self, client):
        r = client.get('/admin/versions')
        assert r.status_code == 200

    def test_admin_settings(self, client):
        r = client.get('/admin/settings')
        assert r.status_code == 200


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


class TestLocationCRUD:
    def test_create_location(self, client):
        r = client.post('/admin/locations/new', data={
            'name': '시험실A', 'color': '#28a745', 'description': '1층',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '시험실A' in r.data.decode()

    def test_edit_location(self, client):
        lid = _create_location(client)
        r = client.post(f'/admin/locations/{lid}/edit', data={
            'name': '시험실B', 'color': '#FF00FF', 'description': '2층',
        }, follow_redirects=True)
        assert '시험실B' in r.data.decode()

    def test_delete_location(self, client):
        lid = _create_location(client)
        r = client.post(f'/admin/locations/{lid}/delete', follow_redirects=True)
        assert r.status_code == 200

    def test_api_create_location(self, client):
        r = client.post('/admin/api/locations', json={
            'name': 'API장소', 'color': '#abcdef', 'description': '테스트',
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['id'].startswith('loc_')
        assert data['name'] == 'API장소'

    def test_api_create_location_missing_name(self, client):
        r = client.post('/admin/api/locations', json={'color': '#fff'})
        assert r.status_code == 400

    def test_api_get_locations(self, client):
        _create_location(client)
        r = client.get('/admin/api/locations')
        assert r.status_code == 200
        assert len(r.get_json()) == 1

    def test_api_update_location(self, client):
        lid = _create_location(client)
        r = client.put(f'/admin/api/locations/{lid}', json={'name': '수정된장소'})
        assert r.status_code == 200
        assert r.get_json()['name'] == '수정된장소'

    def test_api_delete_location(self, client):
        lid = _create_location(client)
        r = client.delete(f'/admin/api/locations/{lid}')
        assert r.status_code == 200
        assert r.get_json()['success'] is True


class TestVersionCRUD:
    def test_create_version(self, client):
        r = client.post('/admin/versions/new', data={
            'name': 'v1.0.0', 'description': '최초 버전',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert 'v1.0.0' in r.data.decode()

    def test_edit_version(self, client):
        vid = _create_version(client)
        r = client.post(f'/admin/versions/{vid}/edit', data={
            'name': 'v2.0.0', 'description': '업데이트',
        }, follow_redirects=True)
        assert 'v2.0.0' in r.data.decode()

    def test_delete_version(self, client):
        vid = _create_version(client)
        r = client.post(f'/admin/versions/{vid}/delete', follow_redirects=True)
        assert r.status_code == 200

    def test_api_create_version(self, client):
        r = client.post('/admin/api/versions', json={
            'name': 'v3.0.0', 'description': 'API버전',
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['id'].startswith('v_')
        assert data['name'] == 'v3.0.0'

    def test_api_create_version_missing_name(self, client):
        r = client.post('/admin/api/versions', json={'description': '없음'})
        assert r.status_code == 400

    def test_api_get_versions(self, client):
        _create_version(client)
        r = client.get('/admin/api/versions')
        assert r.status_code == 200
        assert len(r.get_json()) == 1

    def test_api_update_version(self, client):
        vid = _create_version(client)
        r = client.put(f'/admin/api/versions/{vid}', json={'name': 'v1.1.0'})
        assert r.status_code == 200
        assert r.get_json()['name'] == 'v1.1.0'

    def test_api_delete_version(self, client):
        vid = _create_version(client)
        r = client.delete(f'/admin/api/versions/{vid}')
        assert r.status_code == 200
        assert r.get_json()['success'] is True


class TestSettings:
    def test_update_settings_form(self, client):
        r = client.post('/admin/settings', data={
            'work_start': '08:00',
            'work_end': '17:00',
            'actual_work_start': '08:30',
            'actual_work_end': '16:30',
            'lunch_start': '12:00',
            'lunch_end': '13:00',
            'grid_interval_minutes': '15',
            'max_schedule_days': '7',
            'block_color_by': 'location',
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_api_get_settings(self, client):
        r = client.get('/admin/api/settings')
        assert r.status_code == 200
        data = r.get_json()
        assert data['work_start'] == '08:00'
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
            'work_end': '17:00',
            'actual_work_start': '08:30',
            'actual_work_end': '16:30',
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
