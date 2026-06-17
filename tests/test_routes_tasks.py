"""Tests for task routes."""
import pytest
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
            'memo': '',
        }, follow_redirects=True)
        assert '수정됨' in r.data.decode()

    def test_task_delete(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post(f'/tasks/{tid}/delete', follow_redirects=True)
        assert r.status_code == 200

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
        data = r.get_json()
        assert data['task']['id'] == tid
        # execution_status 필드 포함 여부 확인
        assert 'execution_status' in data['task']['identifiers'][0]

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


class TestTaskExamNo:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        import os, json
        from app import create_app
        data_dir = str(tmp_path / 'data')
        os.makedirs(data_dir)
        for name in ('users', 'locations', 'tasks', 'schedule_blocks',
                     'versions', 'procedures'):
            with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
                json.dump([], f)
        with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
            json.dump({
                'work_start': '08:00', 'work_end': '17:00',
                'actual_work_start': '08:30', 'actual_work_end': '16:30',
                'lunch_start': '12:00', 'lunch_end': '13:00',
                'breaks': [], 'grid_interval_minutes': 15,
                'max_schedule_days': 14, 'block_color_by': 'assignee',
            }, f)
        self.app = create_app()
        self.app.config['DATA_DIR'] = data_dir
        self.app.config['TESTING'] = True

    def test_create_task_with_exam_no(self):
        """exam_no가 있는 태스크를 생성하면 해당 필드가 저장된다."""
        from app.features.schedule.models import task
        with self.app.app_context():
            t = task.create(
                doc_id=1, assignee_names=[], location_id='',
                doc_name='시스템 초기화',
                identifiers=[{'id': 'TC-001', 'estimated_minutes': 60, 'owners': []}],
                estimated_minutes=60, exam_no=2,
            )
            assert t['exam_no'] == 2

    def test_get_by_doc_and_exam(self):
        """(doc_id, exam_no) 조합으로 태스크를 조회한다."""
        from app.features.schedule.models import task
        with self.app.app_context():
            task.create(doc_id=1, assignee_names=[], location_id='',
                        doc_name='시스템', identifiers=[], estimated_minutes=0,
                        exam_no=1)
            task.create(doc_id=1, assignee_names=[], location_id='',
                        doc_name='시스템', identifiers=[], estimated_minutes=0,
                        exam_no=2)
            t1 = task.get_by_doc_and_exam(1, 1)
            t2 = task.get_by_doc_and_exam(1, 2)
            assert t1 is not None and t1['exam_no'] == 1
            assert t2 is not None and t2['exam_no'] == 2
            assert task.get_by_doc_and_exam(1, 99) is None

    def test_display_name_with_exam_no(self):
        """exam_no가 있으면 display_name에 차수 접미사가 붙는다."""
        from app.features.schedule.models import task as task_repo
        with self.app.app_context():
            t = task_repo.create(doc_id=1, assignee_names=[], location_id='',
                                 doc_name='시스템 초기화', identifiers=[],
                                 estimated_minutes=0, exam_no=3)
            assert task_repo.display_name(t) == '시스템 초기화 (3차)'

    def test_display_name_without_exam_no(self):
        """exam_no가 없으면 doc_name 그대로 반환한다."""
        from app.features.schedule.models import task as task_repo
        with self.app.app_context():
            t = task_repo.create(doc_id=2, assignee_names=[], location_id='',
                                 doc_name='항법 연산', identifiers=[],
                                 estimated_minutes=0)
            assert task_repo.display_name(t) == '항법 연산'
