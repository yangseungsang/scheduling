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

    def test_pause_on_already_paused_returns_none(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-011', 't_001', total_count=5)
            ExecutionRepository.pause(ex['id'])
            result = ExecutionRepository.pause(ex['id'])  # already paused
            assert result is None

    def test_resume_on_non_paused_returns_none(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-012', 't_001', total_count=5)
            result = ExecutionRepository.resume(ex['id'])  # in_progress, not paused
            assert result is None

    def test_complete_on_pending_returns_none(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-013', 't_001', total_count=5)
            ExecutionRepository.reset(ex['id'])  # → pending
            result = ExecutionRepository.complete(ex['id'], fail_count=1)
            assert result is None

    def test_complete_while_paused_does_not_add_time(self, exec_app):
        """일시정지 상태에서 완료해도 세그먼트 end 시각이 변경되지 않아야 한다."""
        import json
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            from flask import current_app
            import os

            closed_end = '2026-05-13T10:00:00'
            ex = {
                'id': 'ex_test_paused',
                'identifier_id': 'TC-014',
                'task_id': 't_001',
                'status': 'paused',
                'segments': [{'start': '2026-05-13T09:00:00', 'end': closed_end}],
                'total_count': 10, 'fail_count': 0, 'block_count': 0, 'pass_count': 0,
                'comment': '', 'performer': '',
                'created_at': '2026-05-13T09:00:00', 'completed_at': None,
            }
            data_file = os.path.join(
                current_app.config['EXECUTION_DATA_DIR'], 'executions.json'
            )
            with open(data_file, 'w') as f:
                json.dump([ex], f)

            result = ExecutionRepository.complete('ex_test_paused', fail_count=1, block_count=0)
            assert result['segments'][-1]['end'] == closed_end, (
                f"Expected end={closed_end!r}, got {result['segments'][-1]['end']!r} — "
                "paused segment was overwritten with current time"
            )
            assert result['status'] == 'completed'


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
