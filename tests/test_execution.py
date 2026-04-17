import json
import os
import pytest
from app import create_app


@pytest.fixture
def exec_app(tmp_path):
    data_dir = str(tmp_path / 'data')
    exec_dir = str(tmp_path / 'exec_data')
    os.makedirs(data_dir)
    os.makedirs(exec_dir)

    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions', 'procedures'):
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
    with open(os.path.join(exec_dir, 'executions.json'), 'w') as f:
        json.dump([], f)

    app = create_app()
    app.config['DATA_DIR'] = data_dir
    app.config['EXECUTION_DATA_DIR'] = exec_dir
    app.config['TESTING'] = True
    yield app


@pytest.fixture
def exec_client(exec_app):
    return exec_app.test_client()


class TestExecutionRepository:
    def test_start_creates_record(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-001', 't_001', total_count=5)
            assert ex['identifier_id'] == 'TC-001'
            assert ex['status'] == 'in_progress'
            assert len(ex['segments']) == 1
            assert ex['segments'][0]['end'] is None
            assert ex['total_count'] == 5

    def test_pause_closes_segment(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-002', 't_001', total_count=5)
            paused = ExecutionRepository.pause(ex['id'])
            assert paused['status'] == 'paused'
            assert paused['segments'][0]['end'] is not None

    def test_resume_adds_segment(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-003', 't_001', total_count=5)
            paused = ExecutionRepository.pause(ex['id'])
            resumed = ExecutionRepository.resume(paused['id'])
            assert resumed['status'] == 'in_progress'
            assert len(resumed['segments']) == 2
            assert resumed['segments'][1]['end'] is None

    def test_complete_saves_result(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-004', 't_001', total_count=8)
            done = ExecutionRepository.complete(ex['id'], fail_count=2)
            assert done['status'] == 'completed'
            assert done['fail_count'] == 2
            assert done['pass_count'] == 6
            assert done['completed_at'] is not None
            assert done['segments'][0]['end'] is not None

    def test_reset_clears_record(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-005', 't_001', total_count=5)
            ExecutionRepository.complete(ex['id'], fail_count=1)
            reset = ExecutionRepository.reset(ex['id'])
            assert reset['status'] == 'pending'
            assert reset['segments'] == []
            assert reset['fail_count'] == 0
            assert reset['completed_at'] is None

    def test_compute_elapsed_seconds(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            segments = [
                {'start': '2026-04-17T09:00:00', 'end': '2026-04-17T09:30:00'},
                {'start': '2026-04-17T10:00:00', 'end': '2026-04-17T10:15:00'},
            ]
            assert ExecutionRepository.compute_elapsed_seconds(segments) == 2700


class TestExecutionAPI:
    def test_start(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['status'] == 'in_progress'

    def test_pause(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        ex_id = r.get_json()['id']
        r2 = exec_client.post('/execution/api/pause', json={'execution_id': ex_id})
        assert r2.status_code == 200
        assert r2.get_json()['status'] == 'paused'

    def test_resume(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        ex_id = r.get_json()['id']
        exec_client.post('/execution/api/pause', json={'execution_id': ex_id})
        r3 = exec_client.post('/execution/api/resume', json={'execution_id': ex_id})
        assert r3.status_code == 200
        assert r3.get_json()['status'] == 'in_progress'

    def test_complete(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        ex_id = r.get_json()['id']
        r2 = exec_client.post('/execution/api/complete', json={
            'execution_id': ex_id, 'fail_count': 3
        })
        assert r2.status_code == 200
        data = r2.get_json()
        assert data['status'] == 'completed'
        assert data['fail_count'] == 3

    def test_reset(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        ex_id = r.get_json()['id']
        exec_client.post('/execution/api/complete', json={
            'execution_id': ex_id, 'fail_count': 1
        })
        r2 = exec_client.post('/execution/api/reset', json={'execution_id': ex_id})
        assert r2.status_code == 200
        assert r2.get_json()['status'] == 'pending'

    def test_list(self, exec_client):
        r = exec_client.get('/execution/api/list')
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_total_count(self, exec_client):
        r = exec_client.get('/execution/api/total-count/TC-001')
        assert r.status_code == 200
        assert 'total_count' in r.get_json()

    def test_execution_page(self, exec_client):
        r = exec_client.get('/execution/')
        assert r.status_code == 200
