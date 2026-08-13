"""Tests for procedure routes."""
import pytest
from tests.conftest import _assignee_name, _create_procedure


class TestTestProcedureCRUD:
    def test_create_procedure(self, client):
        uid = _assignee_name(client)
        r = client.post('/procedures/new', data={
            'document_id': '100',
            'assignee_names': [uid],
            'location_name': '',
            'document_name': '시스템',
            'test_items_json': '[{"id":"TC-001","owners":[],"estimated_minutes":120}]',
            'estimated_minutes': '120',
            'memo': '',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert '시스템' in r.data.decode()

    def test_create_procedure_empty_document_id(self, client):
        uid = _assignee_name(client)
        r = client.post('/procedures/new', data={
            'document_id': '',
            'assignee_names': [uid],
            'location_name': '',
            'document_name': '',
            'test_items_json': '',
            'estimated_minutes': '60',
            'memo': '',
        }, follow_redirects=True)
        assert '문서 ID' in r.data.decode()

    def test_procedure_detail(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        r = client.get(f'/procedures/{tid}')
        assert r.status_code == 200
        assert '시스템' in r.data.decode()

    def test_procedure_detail_nonexistent(self, client):
        r = client.get('/procedures/t_nonexist')
        assert r.status_code == 404

    def test_procedure_edit(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        r = client.post(f'/procedures/{tid}/edit', data={
            'document_id': '200',
            'assignee_names': [uid],
            'location_name': '',
            'document_name': '수정됨',
            'test_items_json': '[{"id":"TC-003","owners":[],"estimated_minutes":60}]',
            'estimated_minutes': '60',
            'memo': '',
        }, follow_redirects=True)
        assert '수정됨' in r.data.decode()

    def test_procedure_delete(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        r = client.post(f'/procedures/{tid}/delete', follow_redirects=True)
        assert r.status_code == 200

    def test_api_create_procedure(self, client):
        uid = _assignee_name(client)
        r = client.post('/procedures/api/create', json={
            'document_id': 300,
            'assignee_names': [uid],
            'test_items': [{'id': 'TC-X', 'owners': [], 'estimated_minutes': 180}],
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['estimated_minutes'] == 180
        assert data['remaining_minutes'] == 180

    def test_api_create_procedure_missing_document_id(self, client):
        r = client.post('/procedures/api/create', json={'document_id': ''})
        assert r.status_code == 400

    def test_api_procedure_detail(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        r = client.get(f'/procedures/api/{tid}')
        assert r.status_code == 200
        data = r.get_json()
        assert data['procedure']['id'] == tid
        # execution_status 필드 포함 여부 확인
        assert 'execution_status' in data['procedure']['test_items'][0]

    def test_api_procedure_detail_nonexistent(self, client):
        r = client.get('/procedures/api/t_nonexist')
        assert r.status_code == 404

    def test_api_update_procedure(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        r = client.put(f'/procedures/api/{tid}/update', json={
            'document_id': 400,
            'assignee_names': [uid],
            'test_items': [{'id': 'TC-E', 'owners': [], 'estimated_minutes': 120}],
        })
        assert r.status_code == 200
        assert r.get_json()['estimated_minutes'] == 120

    def test_api_delete_procedure(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        r = client.delete(f'/procedures/api/{tid}/delete')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_procedures_list(self, client):
        r = client.get('/procedures/')
        assert r.status_code == 200

    def test_procedures_new_form(self, client):
        r = client.get('/procedures/new')
        assert r.status_code == 200


class TestTestProcedureExamNo:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from app import create_app
        self.app = create_app()
        self.app.config['TESTING'] = True
        from tests.conftest import configure_test_storage
        configure_test_storage(self.app, tmp_path)

    def test_create_procedure_with_test_round(self):
        """test_round가 있는 태스크를 생성하면 해당 필드가 저장된다."""
        from app.features.schedule.services import test_procedures as procedure
        with self.app.app_context():
            t = procedure.create(
                document_id=1, assignee_names=[], location_name='',
                document_name='시스템 초기화',
                test_items=[{'id': 'TC-001', 'estimated_minutes': 60, 'owners': []}],
                estimated_minutes=60, test_round=2,
            )
            assert t['test_round'] == 2

    def test_get_by_document_and_round(self):
        """(document_id, test_round) 조합으로 태스크를 조회한다."""
        from app.features.schedule.services import test_procedures as procedure
        with self.app.app_context():
            test_items = [{'id': 'TC-001', 'estimated_minutes': 0}]
            procedure.create(document_id=1, assignee_names=[], location_name='',
                        document_name='시스템', test_items=test_items, estimated_minutes=0,
                        test_round=1)
            procedure.create(document_id=1, assignee_names=[], location_name='',
                        document_name='시스템', test_items=test_items, estimated_minutes=0,
                        test_round=2)
            t1 = procedure.get_by_document_and_round(1, 1)
            t2 = procedure.get_by_document_and_round(1, 2)
            assert t1 is not None and t1['test_round'] == 1
            assert t2 is not None and t2['test_round'] == 2
            assert procedure.get_by_document_and_round(1, 99) is None

    def test_display_name_with_test_round(self):
        """test_round가 있으면 display_name에 차수 접미사가 붙는다."""
        from app.features.schedule.services import test_procedures as procedure_repo
        with self.app.app_context():
            t = {'document_name': '시스템 초기화', 'test_round': 3}
            assert procedure_repo.display_name(t) == '시스템 초기화 (3차)'

    def test_display_name_without_test_round(self):
        """test_round가 없으면 document_name 그대로 반환한다."""
        from app.features.schedule.services import test_procedures as procedure_repo
        with self.app.app_context():
            t = {'document_name': '항법 연산', 'test_round': None}
            assert procedure_repo.display_name(t) == '항법 연산'
