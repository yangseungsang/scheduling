"""Tests for SyncService — version and test-data synchronization."""
import json
import os
import pytest

from app import create_app
from app.features.schedule.models import version, task, schedule_block
from app.features.schedule.providers.base import BaseProvider
from app.features.schedule.services.sync import SyncService


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
                        'doc_id': 1,
                        'doc_name': '시스템',
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
            assert t['doc_id'] == 1
            assert t['doc_name'] == '시스템'
            assert t['estimated_minutes'] == 210
            assert len(t['identifiers']) == 2

    def test_sync_updates_existing_task_identifiers(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return [
                    {
                        'doc_id': 1,
                        'doc_name': '시스템',
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
                doc_id=1,
                version_id='VER-001',
                assignee_names=['홍길동'],
                location_id='loc_xyz',
                doc_name='시스템',
                identifiers=[{'id': 'TC-OLD', 'estimated_minutes': 60, 'owners': []}],
                estimated_minutes=60,
            )

            result = SyncService.sync_test_data(MockProvider(), version_id='VER-001')
            assert result['updated'] == 1
            assert result['added'] == 0

            t = task.get_by_doc_id(1)
            # identifiers and estimated_minutes should be updated
            assert len(t['identifiers']) == 1
            assert t['identifiers'][0]['id'] == 'TC-001'
            assert t['estimated_minutes'] == 300
            # assignee_names and location_id should be preserved
            assert t['assignee_names'] == ['홍길동']
            assert t['location_id'] == 'loc_xyz'

    def test_sync_freezes_existing_full_block_before_adding_identifiers(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return [
                    {
                        'doc_id': 1,
                        'doc_name': '시스템',
                        'version_id': 'VER-001',
                        'identifiers': [
                            {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                            {'id': 'TC-002', 'estimated_minutes': 60, 'owners': []},
                            {'id': 'TC-003', 'estimated_minutes': 30, 'owners': []},
                        ],
                    },
                ]

        with self.app.app_context():
            existing = task.create(
                doc_id=1,
                version_id='VER-001',
                assignee_names=[],
                location_id='',
                doc_name='시스템',
                identifiers=[
                    {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    {'id': 'TC-002', 'estimated_minutes': 60, 'owners': []},
                ],
                estimated_minutes=120,
            )
            block = schedule_block.create(
                task_id=existing['id'],
                assignee_names=[],
                location_id='',
                date='2026-03-10',
                start_time='09:00',
                end_time='10:00',
                identifier_ids=None,
            )

            result = SyncService.sync_test_data(MockProvider())

            assert result['updated'] == 1
            updated_block = schedule_block.get_by_id(block['id'])
            assert updated_block['identifier_ids'] == ['TC-001', 'TC-002']

            updated_task = task.get_by_doc_id(1)
            assert [i['id'] for i in updated_task['identifiers']] == [
                'TC-001',
                'TC-002',
                'TC-003',
            ]

    def test_sync_deletes_removed_unscheduled_task(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            task.create(
                doc_id=1,
                version_id='VER-001',
                assignee_names=[],
                location_id='',
                doc_name='시스템',
                identifiers=[],
                estimated_minutes=0,
            )

            result = SyncService.sync_test_data(MockProvider())
            assert result['deleted'] == 1

            assert task.get_by_doc_id(1) is None

    def test_sync_keeps_removed_task_when_scheduled_and_warns(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            t = task.create(
                doc_id=1,
                version_id='VER-001',
                assignee_names=[],
                location_id='',
                doc_name='시스템',
                identifiers=[{'id': 'TC-001', 'estimated_minutes': 60, 'owners': []}],
                estimated_minutes=60,
            )
            schedule_block.create(
                task_id=t['id'],
                assignee_names=[],
                location_id='',
                date='2026-07-07',
                start_time='09:00',
                end_time='10:00',
            )

            result = SyncService.sync_test_data(MockProvider())
            assert result['deleted'] == 0
            assert task.get_by_doc_id(1) is not None
            assert any('이미 스케줄 블록에 배치' in w for w in result['warnings'])

    def test_sync_removes_deleted_queue_identifier(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return [{
                    'doc_id': 1,
                    'doc_name': '시스템',
                    'version_id': 'VER-001',
                    'identifiers': [
                        {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    ],
                }]

        with self.app.app_context():
            task.create(
                doc_id=1,
                version_id='VER-001',
                assignee_names=[],
                location_id='',
                doc_name='시스템',
                identifiers=[
                    {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    {'id': 'TC-002', 'estimated_minutes': 30, 'owners': []},
                ],
                estimated_minutes=90,
            )

            result = SyncService.sync_test_data(MockProvider())
            assert result['warnings'] == []
            t = task.get_by_doc_id(1)
            assert [i['id'] for i in t['identifiers']] == ['TC-001']
            assert t['estimated_minutes'] == 60

    def test_sync_keeps_deleted_scheduled_identifier_and_warns(self):
        class MockProvider(BaseProvider):
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                return [{
                    'doc_id': 1,
                    'doc_name': '시스템',
                    'version_id': 'VER-001',
                    'identifiers': [
                        {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    ],
                }]

        with self.app.app_context():
            t = task.create(
                doc_id=1,
                version_id='VER-001',
                assignee_names=[],
                location_id='',
                doc_name='시스템',
                identifiers=[
                    {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    {'id': 'TC-002', 'estimated_minutes': 30, 'owners': []},
                ],
                estimated_minutes=90,
            )
            schedule_block.create(
                task_id=t['id'],
                assignee_names=[],
                location_id='',
                date='2026-07-07',
                start_time='09:00',
                end_time='10:00',
                identifier_ids=['TC-002'],
            )

            result = SyncService.sync_test_data(MockProvider())
            t = task.get_by_doc_id(1)
            assert [i['id'] for i in t['identifiers']] == ['TC-001', 'TC-002']
            assert t['estimated_minutes'] == 90
            assert any('TC-002' in w and '이미 스케줄 블록에 배치' in w
                       for w in result['warnings'])

    def test_sync_creates_exam_no_tasks_from_cache(self):
        """std_list 캐시가 있으면 (doc_id, exam_no) 조합별로 태스크를 생성한다."""
        from unittest.mock import patch

        class MockProvider(BaseProvider):
            def get_versions(self): return []
            def get_test_data(self, version_id): return []
            def get_test_data_all(self):
                return [{
                    'doc_id': 1,
                    'doc_name': '시스템 초기화',
                    'version_id': 'VER-001',
                    'identifiers': [
                        {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                        {'id': 'TC-002', 'estimated_minutes': 90, 'owners': []},
                    ],
                }]

        fake_cache = [
            {'test_info': 'TC-001', 'exam_no': 1},
            {'test_info': 'TC-001', 'exam_no': 2},
            {'test_info': 'TC-002', 'exam_no': 1},
        ]

        with self.app.app_context():
            with patch(
                'app.features.schedule.services.sync.load_std_list_cache',
                return_value=fake_cache,
            ):
                result = SyncService.sync_test_data(MockProvider())

            assert result['added'] == 2  # exam_no=1(TC-001,TC-002), exam_no=2(TC-001)
            tasks = task.get_all()
            assert len(tasks) == 2

            exam1 = next(t for t in tasks if t.get('exam_no') == 1)
            exam2 = next(t for t in tasks if t.get('exam_no') == 2)

            assert len(exam1['identifiers']) == 2  # TC-001, TC-002
            assert len(exam2['identifiers']) == 1  # TC-001만

    def test_sync_no_cache_creates_single_task(self):
        """std_list 캐시가 비어 있으면 exam_no=None 태스크 1개를 생성한다."""
        from unittest.mock import patch

        class MockProvider(BaseProvider):
            def get_versions(self): return []
            def get_test_data(self, version_id): return []
            def get_test_data_all(self):
                return [{
                    'doc_id': 2,
                    'doc_name': '항법 연산',
                    'version_id': 'VER-001',
                    'identifiers': [
                        {'id': 'TC-010', 'estimated_minutes': 30, 'owners': []},
                    ],
                }]

        with self.app.app_context():
            with patch(
                'app.features.schedule.services.sync.load_std_list_cache',
                return_value=[],
            ):
                result = SyncService.sync_test_data(MockProvider())

            assert result['added'] == 1
            tasks = task.get_all()
            assert len(tasks) == 1
            assert tasks[0].get('exam_no') is None

    def test_sync_cancels_old_exam_no_none_when_cache_appears(self):
        """기존 exam_no=None 태스크가 있을 때 캐시가 생기면 자동 cancelled 처리한다."""
        from unittest.mock import patch

        class MockProvider(BaseProvider):
            def get_versions(self): return []
            def get_test_data(self, version_id): return []
            def get_test_data_all(self):
                return [{
                    'doc_id': 1,
                    'doc_name': '시스템',
                    'version_id': 'VER-001',
                    'identifiers': [
                        {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    ],
                }]

        with self.app.app_context():
            # 먼저 exam_no=None 태스크 생성
            with patch('app.features.schedule.services.sync.load_std_list_cache',
                       return_value=[]):
                SyncService.sync_test_data(MockProvider())

            old_task = task.get_all()[0]
            assert old_task.get('exam_no') is None

            # 이번에는 캐시에 exam_no 데이터가 생김
            fake_cache = [{'test_info': 'TC-001', 'exam_no': 1}]
            with patch('app.features.schedule.services.sync.load_std_list_cache',
                       return_value=fake_cache):
                SyncService.sync_test_data(MockProvider())

            tasks = task.get_all()
            # exam_no=None 태스크는 삭제되고, exam_no=1 태스크가 새로 생성됨
            assert len(tasks) == 1
            assert tasks[0]['exam_no'] == 1


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
            assert 'tasks' in data

    def test_reset_and_sync_clears_provider_meta_cache(self):
        """reset-and-sync는 provider 메타 캐시를 초기화해 NoChangesError를 우회한다.

        이전에 동기화한 타임스탬프가 남아 있어도 reset-and-sync가 메타를
        초기화하므로 provider가 NoChangesError를 발생시키지 않는다.
        """
        import json
        import os
        from unittest.mock import patch
        from app.features.schedule.providers.base import BaseProvider, NoChangesError

        data_dir = self.app.config['DATA_DIR']
        meta_path = os.path.join(data_dir, 'dyn_ready_meta.json')

        # 이전 동기화로 남은 타임스탬프를 시뮬레이션
        with open(meta_path, 'w') as f:
            json.dump({'updated_at': '2026-01-01T00:00:00'}, f)

        class MetaAwareProvider(BaseProvider):
            """메타 파일에 타임스탬프가 있으면 NoChangesError를 발생시킨다."""
            def get_versions(self):
                return []
            def get_test_data(self, version_id):
                return []
            def get_test_data_all(self):
                if os.path.exists(meta_path):
                    with open(meta_path) as f:
                        meta = json.load(f)
                    if meta.get('updated_at'):
                        raise NoChangesError(meta['updated_at'])
                return [{
                    'doc_id': 1,
                    'doc_name': '테스트 항목',
                    'version_id': 'VER-001',
                    'identifiers': [
                        {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    ],
                }]

        with self.app.test_client() as c:
            with patch('app.features.schedule.routes.sync.get_provider',
                       return_value=MetaAwareProvider()):
                r = c.post('/api/sync/reset-and-sync', json={})
        assert r.status_code == 200
        d = r.get_json()
        assert d['tasks'].get('added') == 1, (
            '메타 캐시 미초기화로 NoChangesError 발생 — '
            'reset-and-sync 후 태스크가 생성되지 않음'
        )


# ===========================================================================
# TestSyncStdListAPI (추가)
# ===========================================================================

class TestSyncStdListAPI:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.app = _make_app(tmp_path)

    def test_sync_std_list_success(self):
        """MySQL 조회 성공 시 캐시를 저장하고 200을 반환한다."""
        from unittest.mock import patch
        fake_rows = [
            {'test_info': 'TC-001', 'exam_no': 1},
            {'test_info': 'TC-001', 'exam_no': 2},
        ]
        with self.app.test_client() as c:
            with patch(
                'app.features.schedule.models.std_list.fetch_from_mysql',
                return_value=fake_rows,
            ):
                r = c.post('/api/sync/std-list')
        assert r.status_code == 200
        data = r.get_json()
        assert data['cached'] == 2

    def test_sync_std_list_mysql_failure(self):
        """MySQL 접속 실패 시 503을 반환한다."""
        from unittest.mock import patch
        with self.app.test_client() as c:
            with patch(
                'app.features.schedule.models.std_list.fetch_from_mysql',
                side_effect=Exception('connection refused'),
            ):
                r = c.post('/api/sync/std-list')
        assert r.status_code == 503
