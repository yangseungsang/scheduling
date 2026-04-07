"""Tests for SyncService — version and test-data synchronization."""
import json
import os

import pytest

from schedule import create_app
from schedule.models import version, task
from schedule.providers.base import BaseProvider
from schedule.services.sync import SyncService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(tmp_path):
    """Create a fresh app with temporary data directory."""
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
            'breaks': [],
            'grid_interval_minutes': 15,
            'max_schedule_days': 14,
            'block_color_by': 'assignee',
        }, f)

    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    return application


# ===========================================================================
# TestSyncVersions
# ===========================================================================

class TestSyncVersions:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.app = _make_app(tmp_path)

    def test_sync_adds_new_versions(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return [
                    {'id': 'VER-001', 'name': 'v1.0', 'description': 'First'},
                    {'id': 'VER-002', 'name': 'v2.0', 'description': 'Second'},
                ]
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            result = SyncService.sync_versions(MockProvider())
            assert result['added'] == 2
            assert result['updated'] == 0
            assert result['deactivated'] == 0

            v1 = version.get_by_id('VER-001')
            assert v1 is not None
            assert v1['name'] == 'v1.0'

            v2 = version.get_by_id('VER-002')
            assert v2 is not None
            assert v2['name'] == 'v2.0'

    def test_sync_updates_existing_version(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return [
                    {'id': 'VER-001', 'name': 'v1.0-updated', 'description': 'Updated'},
                ]
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            version.create(name='v1.0-old', description='Old', id='VER-001')

            result = SyncService.sync_versions(MockProvider())
            assert result['added'] == 0
            assert result['updated'] == 1

            v = version.get_by_id('VER-001')
            assert v['name'] == 'v1.0-updated'
            assert v['description'] == 'Updated'

    def test_sync_deactivates_removed_version(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return [
                    {'id': 'VER-NEW', 'name': 'New Version'},
                ]
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            version.create(name='Old Version', description='', id='VER-OLD')

            result = SyncService.sync_versions(MockProvider())
            assert result['added'] == 1
            assert result['deactivated'] == 1

            old = version.get_by_id('VER-OLD')
            assert old['is_active'] is False

            new = version.get_by_id('VER-NEW')
            assert new['is_active'] is True


# ===========================================================================
# TestSyncTestData
# ===========================================================================

class TestSyncTestData:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.app = _make_app(tmp_path)

    def test_sync_creates_new_tasks(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return [
                    {
                        'section_name': '3.1 시스템',
                        'version_id': 'VER-001',
                        'identifiers': [
                            {'id': 'TC-001', 'estimated_minutes': 120, 'owners': []},
                            {'id': 'TC-002', 'estimated_minutes': 90, 'owners': []},
                        ],
                    },
                ]

        with self.app.app_context():
            result = SyncService.sync_test_data(MockProvider())
            assert result['added'] == 1
            assert result['updated'] == 0
            assert result['cancelled'] == 0

            tasks = task.get_all()
            assert len(tasks) == 1
            t = tasks[0]
            assert t['source'] == 'external'
            assert t['external_key'] == '3.1 시스템::VER-001'
            assert t['estimated_minutes'] == 210
            assert len(t['test_list']) == 2

    def test_sync_updates_existing_task_identifiers(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return [
                    {
                        'section_name': '3.1 시스템',
                        'version_id': 'VER-001',
                        'identifiers': [
                            {'id': 'TC-001', 'estimated_minutes': 300, 'owners': ['Alice']},
                        ],
                    },
                ]
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            # Pre-create a task with assignee and location set
            task.create(
                procedure_id='EXT-001',
                version_id='VER-001',
                assignee_ids=['u_abc'],
                location_id='loc_xyz',
                section_name='3.1 시스템',
                procedure_owner='Owner',
                test_list=[{'id': 'TC-OLD', 'estimated_minutes': 60, 'owners': []}],
                estimated_minutes=60,
                source='external',
                external_key='3.1 시스템::VER-001',
            )

            result = SyncService.sync_test_data(MockProvider(), version_id='VER-001')
            assert result['updated'] == 1
            assert result['added'] == 0

            t = task.get_by_external_key('3.1 시스템::VER-001')
            # test_list and estimated_minutes should be updated
            assert len(t['test_list']) == 1
            assert t['test_list'][0]['id'] == 'TC-001'
            assert t['estimated_minutes'] == 300
            # assignee_ids and location_id should be preserved
            assert t['assignee_ids'] == ['u_abc']
            assert t['location_id'] == 'loc_xyz'

    def test_sync_cancels_removed_task(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            task.create(
                procedure_id='EXT-001',
                version_id='VER-001',
                assignee_ids=[],
                location_id='',
                section_name='3.1 시스템',
                procedure_owner='',
                test_list=[],
                estimated_minutes=0,
                source='external',
                external_key='3.1 시스템::VER-001',
            )

            result = SyncService.sync_test_data(MockProvider())
            assert result['cancelled'] == 1

            t = task.get_by_external_key('3.1 시스템::VER-001')
            assert t['status'] == 'cancelled'


# ===========================================================================
# TestSyncAPI
# ===========================================================================

class TestSyncAPI:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.app = _make_app(tmp_path)

    @pytest.fixture
    def client(self):
        return self.app.test_client()

    def test_sync_versions_api(self, client):
        with self.app.app_context():
            resp = client.post('/api/sync/versions')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'added' in data

    def test_sync_test_data_api(self, client):
        with self.app.app_context():
            resp = client.post('/api/sync/test-data', json={})
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'added' in data

    def test_sync_status_api(self, client):
        with self.app.app_context():
            resp = client.get('/api/sync/status')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'versions' in data
            assert 'external_tasks' in data
