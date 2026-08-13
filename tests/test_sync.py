"""Tests for external test-data synchronization."""
import pytest

from app import create_app
from app.features.schedule.services import test_procedures as procedure, blocks as schedule_block
from app.features.schedule.services.sync import SyncService
from app.repositories import JsonDomainRepository
from tests.conftest import configure_test_storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(tmp_path):
    """Create a fresh app with temporary data directory."""
    application = create_app()
    application.config['TESTING'] = True
    configure_test_storage(application, tmp_path)
    return application


# ===========================================================================
# TestSyncTestData
# ===========================================================================

class TestSyncTestData:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.app = _make_app(tmp_path)

    def test_sync_creates_new_procedures(self):
        class MockProvider:
            def get_test_data_all(self):
                return [
                    {
                        'document_id': 1,
                        'document_name': '시스템',
                        'test_items': [
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

            procedures = procedure.get_all()
            assert len(procedures) == 1
            t = procedures[0]
            assert t['document_id'] == '1'
            assert t['document_name'] == '시스템'
            assert t['estimated_minutes'] == 210
            assert len(t['test_items']) == 2

    def test_sync_sets_one_version_for_the_test_cycle(self):
        class MockProvider:
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            SyncService.sync_test_data(MockProvider(), 'CYCLE-2026-08')

            repository = JsonDomainRepository(
                self.app.config['DOMAIN_DATA_DIR'],
            )
            assert repository.load_operations().version_id == 'CYCLE-2026-08'

    def test_sync_updates_existing_procedure_test_items(self):
        class MockProvider:
            def get_test_data_all(self):
                return [
                    {
                        'document_id': 1,
                        'document_name': '시스템',
                        'test_items': [
                            {'id': 'TC-001', 'estimated_minutes': 300, 'owners': ['Alice']},
                        ],
                    },
                ]

        with self.app.app_context():
            # Pre-create a procedure with assignee and location set
            procedure.create(
                document_id=1,
                assignee_names=['홍길동'],
                location_name='loc_xyz',
                document_name='시스템',
                test_items=[{'id': 'TC-OLD', 'estimated_minutes': 60, 'owners': []}],
                estimated_minutes=60,
            )

            result = SyncService.sync_test_data(MockProvider())
            assert result['updated'] == 1
            assert result['added'] == 0

            t = procedure.get_by_document_id(1)
            # test_items and estimated_minutes should be updated
            assert len(t['test_items']) == 1
            assert t['test_items'][0]['id'] == 'TC-001'
            assert t['estimated_minutes'] == 300
            # assignee_names and location_name should be preserved
            assert t['assignee_names'] == ['홍길동']
            assert t['location_name'] == 'loc_xyz'

    def test_sync_deletes_removed_unscheduled_procedure(self):
        class MockProvider:
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            procedure.create(
                document_id=1,
                assignee_names=[],
                location_name='',
                document_name='시스템',
                test_items=[{'id': 'TC-EMPTY', 'estimated_minutes': 0}],
                estimated_minutes=0,
            )

            result = SyncService.sync_test_data(MockProvider())
            assert result['deleted'] == 1

            assert procedure.get_by_document_id(1) is None

    def test_sync_keeps_removed_procedure_when_scheduled_and_warns(self):
        class MockProvider:
            def get_test_data_all(self):
                return []

        with self.app.app_context():
            t = procedure.create(
                document_id=1,
                assignee_names=[],
                location_name='',
                document_name='시스템',
                test_items=[{'id': 'TC-001', 'estimated_minutes': 60, 'owners': []}],
                estimated_minutes=60,
            )
            schedule_block.create(
                procedure_id=t['id'],
                assignee_names=[],
                location_name='',
                date='2026-07-07',
                start_time='09:00',
                end_time='10:00',
            )

            result = SyncService.sync_test_data(MockProvider())
            assert result['deleted'] == 0
            assert procedure.get_by_document_id(1) is not None
            assert any('이미 스케줄 블록에 배치' in w for w in result['warnings'])

    def test_sync_removes_deleted_queue_test_item(self):
        class MockProvider:
            def get_test_data_all(self):
                return [{
                    'document_id': 1,
                    'document_name': '시스템',
                    'test_items': [
                        {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    ],
                }]

        with self.app.app_context():
            procedure.create(
                document_id=1,
                assignee_names=[],
                location_name='',
                document_name='시스템',
                test_items=[
                    {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    {'id': 'TC-002', 'estimated_minutes': 30, 'owners': []},
                ],
                estimated_minutes=90,
            )

            result = SyncService.sync_test_data(MockProvider())
            assert result['warnings'] == []
            t = procedure.get_by_document_id(1)
            assert [i['id'] for i in t['test_items']] == ['TC-001']
            assert t['estimated_minutes'] == 60

    def test_sync_keeps_deleted_scheduled_test_item_and_warns(self):
        class MockProvider:
            def get_test_data_all(self):
                return [{
                    'document_id': 1,
                    'document_name': '시스템',
                    'test_items': [
                        {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    ],
                }]

        with self.app.app_context():
            t = procedure.create(
                document_id=1,
                assignee_names=[],
                location_name='',
                document_name='시스템',
                test_items=[
                    {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    {'id': 'TC-002', 'estimated_minutes': 30, 'owners': []},
                ],
                estimated_minutes=90,
            )
            schedule_block.create(
                procedure_id=t['id'],
                assignee_names=[],
                location_name='',
                date='2026-07-07',
                start_time='09:00',
                end_time='10:00',
                test_item_ids=['TC-002'],
            )

            result = SyncService.sync_test_data(MockProvider())
            t = procedure.get_by_document_id(1)
            assert [i['id'] for i in t['test_items']] == ['TC-001', 'TC-002']
            assert t['estimated_minutes'] == 90
            assert any('TC-002' in w and '이미 스케줄 블록에 배치' in w
                       for w in result['warnings'])

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

    def test_sync_test_data_api(self, client):
        from unittest.mock import Mock, patch

        integration = Mock()
        integration.get_test_data_all.return_value = []
        with self.app.app_context(), patch(
            'app.features.schedule.routes.sync.DynReadyClient',
            return_value=integration,
        ):
            resp = client.post('/api/sync/test-data')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'added' in data

    def test_sync_status_api(self, client):
        with self.app.app_context():
            resp = client.get('/api/sync/status')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'test_procedures' in data
