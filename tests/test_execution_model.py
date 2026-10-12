"""Tests for ExecutionRepository.get_by_identifier_and_task."""
import json, os
import pytest
from app import create_app


def _make_app(tmp_path):
    data_dir = str(tmp_path / 'sched_data')
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
    return app


class TestGetByIdentifierAndTask:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.app = _make_app(tmp_path)

    def test_returns_correct_execution_by_task_scope(self):
        """동일 identifier_id가 두 태스크에 있을 때 task_id로 올바른 실행을 반환한다."""
        from app.features.execution.models.execution import ExecutionRepository
        with self.app.app_context():
            ex1 = ExecutionRepository.start('TC-001', 't_task1', total_count=10)
            ex2 = ExecutionRepository.start('TC-001', 't_task2', total_count=10)

            found1 = ExecutionRepository.get_by_identifier_and_task('TC-001', 't_task1')
            found2 = ExecutionRepository.get_by_identifier_and_task('TC-001', 't_task2')

            assert found1 is not None
            assert found1['task_id'] == 't_task1'
            assert found2 is not None
            assert found2['task_id'] == 't_task2'
            assert found1['id'] != found2['id']

    def test_returns_none_when_not_found(self):
        """일치하는 레코드가 없으면 None을 반환한다."""
        from app.features.execution.models.execution import ExecutionRepository
        with self.app.app_context():
            result = ExecutionRepository.get_by_identifier_and_task('TC-999', 't_none')
            assert result is None
