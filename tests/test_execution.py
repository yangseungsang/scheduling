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

    def test_start_allows_when_other_performer_is_in_progress(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository

            ex = ExecutionRepository.start('TC-OTHER', 't_other', total_count=0)
            ExecutionRepository.update_performer(ex['id'], 'alice')

        exec_client.post('/execution/api/login', json={'username': 'bob'})
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-BOB', 'task_id': 't_bob'
        })
        assert r.status_code == 201
        assert r.get_json()['performer'] == 'bob'

    def test_start_blocks_when_current_user_is_already_in_progress(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository

            ex = ExecutionRepository.start('TC-ALICE', 't_alice', total_count=0)
            ExecutionRepository.update_performer(ex['id'], 'alice')

        exec_client.post('/execution/api/login', json={'username': 'alice'})
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-NEW', 'task_id': 't_new'
        })
        assert r.status_code == 409
        assert r.get_json()['code'] == 'user_busy'

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

    def test_complete_accepts_result_counts_when_total_count_unknown(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.models import task as task_repo

            task = task_repo.create(
                doc_id=5,
                assignee_names=[],
                location_id='',
                doc_name='카운트 미정 문서',
                identifiers=[
                    {'id': 'TC-UNKNOWN', 'name': '카운트 미정 시험', 'estimated_minutes': 10},
                ],
                estimated_minutes=10,
            )

        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-UNKNOWN', 'task_id': task['id']
        })
        ex_id = r.get_json()['id']
        r2 = exec_client.post('/execution/api/complete', json={
            'execution_id': ex_id, 'fail_count': 2, 'block_count': 1
        })

        assert r2.status_code == 200
        data = r2.get_json()
        assert data['total_count'] == 0
        assert data['fail_count'] == 2
        assert data['block_count'] == 1
        assert data['pass_count'] == 0

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

    def test_total_count_uses_identifier_data_not_hardcoded_ten(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.models import task as task_repo

            task_repo.create(
                doc_id=1,
                assignee_names=[],
                location_id='',
                doc_name='카운트 문서',
                identifiers=[
                    {'id': 'TC-COUNT', 'name': '카운트 시험', 'estimated_minutes': 10, 'total_count': 7},
                ],
                estimated_minutes=10,
            )

        r = exec_client.get('/execution/api/total-count/TC-COUNT')
        assert r.status_code == 200
        assert r.get_json()['total_count'] == 7

    def test_total_count_accepts_external_aliases(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.models import task as task_repo

            task_repo.create(
                doc_id=6,
                assignee_names=[],
                location_id='',
                doc_name='별칭 카운트 문서',
                identifiers=[
                    {'id': 'TC-ALIAS', 'name': '별칭 시험', 'estimated_minutes': 10, 'total_tests': 11},
                ],
                estimated_minutes=10,
            )

        r = exec_client.get('/execution/api/total-count/TC-ALIAS')
        assert r.status_code == 200
        assert r.get_json()['total_count'] == 11

    def test_item_uses_identifier_total_count_when_execution_has_zero(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            from app.features.schedule.models import task as task_repo

            task = task_repo.create(
                doc_id=7,
                assignee_names=[],
                location_id='',
                doc_name='총 건수 보정 문서',
                identifiers=[
                    {'id': 'TC-FALLBACK', 'name': '보정 시험', 'estimated_minutes': 10, 'total_count': 6},
                ],
                estimated_minutes=10,
            )
            ExecutionRepository.start('TC-FALLBACK', task['id'], total_count=0)

        r = exec_client.get('/execution/api/item/TC-FALLBACK?task_id=' + task['id'])
        assert r.status_code == 200
        data = r.get_json()
        assert data['total_count'] == 6
        assert data['execution']['total_count'] == 6

    def test_complete_rehydrates_total_count_before_pass_calculation(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            from app.features.schedule.models import task as task_repo

            task = task_repo.create(
                doc_id=8,
                assignee_names=[],
                location_id='',
                doc_name='완료 계산 문서',
                identifiers=[
                    {'id': 'TC-REHYDRATE', 'name': '완료 계산 시험', 'estimated_minutes': 10, 'total_count': 9},
                ],
                estimated_minutes=10,
            )
            ex = ExecutionRepository.start('TC-REHYDRATE', task['id'], total_count=0)

        r = exec_client.post('/execution/api/complete', json={
            'execution_id': ex['id'], 'fail_count': 2, 'block_count': 3
        })

        assert r.status_code == 200
        data = r.get_json()
        assert data['total_count'] == 9
        assert data['pass_count'] == 4

    def test_complete_result_counts_and_completed_date_are_listed(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.models import task as task_repo
            from app.features.execution.models.execution import ExecutionRepository

            t = task_repo.create(
                doc_id=2,
                assignee_names=[],
                location_id='',
                doc_name='결과 문서',
                identifiers=[
                    {'id': 'TC-RESULT', 'name': '결과 시험', 'estimated_minutes': 10, 'total_count': 9},
                ],
                estimated_minutes=10,
            )
            ex = ExecutionRepository.start('TC-RESULT', t['id'], total_count=9)
            done = ExecutionRepository.complete(ex['id'], fail_count=2, block_count=3)

        r = exec_client.get('/execution/api/list')
        item = next(i for i in r.get_json() if i['identifier_id'] == 'TC-RESULT')
        assert item['execution']['fail_count'] == 2
        assert item['execution']['block_count'] == 3
        assert item['execution']['pass_count'] == 4
        assert item['execution']['total_count'] == 9
        assert item['execution']['completed_at'] == done['completed_at']
        assert item['display_date'] == done['completed_at']

    def test_list_uses_scheduled_block_location_per_task_identifier(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.models import location as loc_repo
            from app.features.schedule.models import schedule_block as block_repo
            from app.features.schedule.models import task as task_repo

            loc_a = loc_repo.create('시험실A', '#111111')
            loc_b = loc_repo.create('시험실B', '#222222')
            task1 = task_repo.create(
                doc_id=3,
                assignee_names=[],
                location_id=loc_a['id'],
                doc_name='원본',
                identifiers=[{'id': 'TC-SAME', 'name': '원본 시험', 'estimated_minutes': 10}],
                estimated_minutes=10,
            )
            task2 = task_repo.create(
                doc_id=4,
                assignee_names=[],
                location_id=loc_a['id'],
                doc_name='재시험',
                identifiers=[{'id': 'TC-SAME', 'name': '재시험', 'estimated_minutes': 10}],
                estimated_minutes=10,
                exam_no=2,
            )
            block_repo.create(
                task_id=task1['id'],
                assignee_names=[],
                location_id=loc_a['id'],
                date='2026-07-01',
                start_time='09:00',
                end_time='10:00',
                identifier_ids=['TC-SAME'],
            )
            block_repo.create(
                task_id=task2['id'],
                assignee_names=[],
                location_id=loc_b['id'],
                date='2026-07-01',
                start_time='10:00',
                end_time='11:00',
                identifier_ids=['TC-SAME'],
            )

        r = exec_client.get('/execution/api/list')
        items = {i['task_id']: i for i in r.get_json() if i['identifier_id'] == 'TC-SAME'}
        assert items[task1['id']]['location_name'] == '시험실A'
        assert items[task2['id']]['location_name'] == '시험실B'

    def test_execution_page(self, exec_client):
        r = exec_client.get('/execution/')
        assert r.status_code == 200

    def test_detail_count_inputs_only_cap_when_total_count_is_known(self):
        js_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'app',
            'static',
            'execution',
            'js',
            'execution-detail.js',
        )
        with open(js_path) as f:
            detail_js = f.read()

        assert 'const maxA   = total > 0 ? `max="${total}"` : \'\';' in detail_js
