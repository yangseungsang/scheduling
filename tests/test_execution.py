import os
import pytest
from app import create_app
from tests.conftest import configure_test_storage


@pytest.fixture
def exec_app(tmp_path):
    app = create_app()
    app.config['TESTING'] = True
    configure_test_storage(app, tmp_path)
    with app.app_context():
        from app.features.schedule.services.test_procedures import TestProcedureService
        from app.repositories import get_repository

        service = TestProcedureService(get_repository())
        service.create_procedure({
            'id': 't_001', 'document_id': 1, 'document_name': '기본 시험',
            'test_items': [
                {'id': f'TC-{number:03d}', 'total_count': 10}
                for number in range(1, 15)
            ],
        })
        for procedure_id, test_item_id, document_id in (
            ('t_alice', 'TC-ALICE', 2),
            ('t_bob', 'TC-BOB', 3),
            ('t_new', 'TC-NEW', 4),
            ('t_other', 'TC-OTHER', 5),
        ):
            service.create_procedure({
                'id': procedure_id, 'document_id': document_id, 'document_name': procedure_id,
                'test_items': [{'id': test_item_id}],
            })
    yield app


@pytest.fixture
def exec_client(exec_app):
    return exec_app.test_client()


class TestExecutionRepository:
    def test_uses_configured_json_storage(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.storage import get_execution_storage

            storage = get_execution_storage()
            assert storage.get_all() == []

    def test_uses_alternate_json_directory(self, exec_app, tmp_path):
        configure_test_storage(exec_app, tmp_path / 'alternate')
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            from app.features.execution.storage import get_execution_storage
            from app.features.schedule.services.test_procedures import TestProcedureService
            from app.repositories import get_repository

            TestProcedureService(get_repository()).create_procedure({
                'id': 't_json', 'document_id': 100, 'document_name': 'JSON',
                'test_items': [{'id': 'TC-JSON'}],
            })

            ex = ExecutionRepository.start('TC-JSON', 't_json', total_count=4)
            assert ex['status'] == 'in_progress'
            ExecutionRepository.pause('t_json', 'TC-JSON')
            stored = get_execution_storage().get_all()
            assert stored[0]['test_item_id'] == 'TC-JSON'
            assert stored[0]['status'] == 'paused'

    def test_start_creates_record(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = ExecutionRepository.start('TC-001', 't_001', total_count=5)
            assert ex['test_item_id'] == 'TC-001'
            assert ex['status'] == 'in_progress'
            assert ex['started_at']
            assert ex['active_started_at'] == ex['started_at']
            assert ex['actual_seconds'] == 0
            assert ex['total_count'] == 5

    def test_pause_closes_segment(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = ExecutionRepository.start('TC-002', 't_001', total_count=5)
            paused = ExecutionRepository.pause('t_001', 'TC-002')
            assert paused['status'] == 'paused'
            assert paused['active_started_at'] is None
            assert paused['actual_seconds'] >= 0

    def test_resume_adds_segment(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = ExecutionRepository.start('TC-003', 't_001', total_count=5)
            paused = ExecutionRepository.pause('t_001', 'TC-003')
            resumed = ExecutionRepository.resume('t_001', 'TC-003')
            assert resumed['status'] == 'in_progress'
            assert resumed['active_started_at']
            assert resumed['started_at'] == ex['started_at']
            assert resumed['actual_seconds'] == paused['actual_seconds']

    def test_complete_saves_result(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = ExecutionRepository.start('TC-004', 't_001', total_count=8)
            done = ExecutionRepository.complete('t_001', 'TC-004', fail_count=2)
            assert done['status'] == 'completed'
            assert done['fail_count'] == 2
            assert done['pass_count'] == 6
            assert done['completed_at'] is not None
            assert done['ended_at'] == done['completed_at']
            assert done['active_started_at'] is None

    def test_reset_clears_record(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = ExecutionRepository.start('TC-005', 't_001', total_count=5)
            ExecutionRepository.complete('t_001', 'TC-005', fail_count=1)
            reset = ExecutionRepository.reset('t_001', 'TC-005')
            assert reset['status'] == 'pending'
            assert reset['started_at'] is None
            assert reset['ended_at'] is None
            assert reset['actual_seconds'] == 0
            assert reset['fail_count'] == 0
            assert reset['completed_at'] is None

    def test_paused_elapsed_seconds_is_accumulated_value(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.domain import ExecutionRun
            run = ExecutionRun(
                procedure_id='t_001', test_item_id='TC-006',
                status='paused', actual_seconds=2700,
            )
            assert run.elapsed_seconds == 2700

    def test_pause_on_already_paused_returns_none(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = ExecutionRepository.start('TC-011', 't_001', total_count=5)
            ExecutionRepository.pause('t_001', 'TC-011')
            result = ExecutionRepository.pause('t_001', 'TC-011')  # already paused
            assert result is None

    def test_resume_on_non_paused_returns_none(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = ExecutionRepository.start('TC-012', 't_001', total_count=5)
            result = ExecutionRepository.resume('t_001', 'TC-012')  # in_progress, not paused
            assert result is None

    def test_complete_on_pending_returns_none(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = ExecutionRepository.start('TC-013', 't_001', total_count=5)
            ExecutionRepository.reset('t_001', 'TC-013')  # → pending
            result = ExecutionRepository.complete('t_001', 'TC-013', fail_count=1)
            assert result is None

    def test_complete_while_paused_does_not_add_time(self, exec_app):
        """일시정지 상태에서 완료해도 정지 이후 시간이 추가되지 않아야 한다."""
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository
            ex = {
                'test_item_id': 'TC-014',
                'procedure_id': 't_001',
                'status': 'paused',
                'started_at': '2026-05-13T09:00:00',
                'actual_seconds': 3600,
                'total_count': 10, 'fail_count': 0, 'block_count': 0, 'pass_count': 0,
                'comment': '', 'performer': '',
            }
            from app.features.execution.storage import get_execution_storage
            get_execution_storage().save_all([ex])

            result = ExecutionRepository.complete(
                't_001', 'TC-014', fail_count=1, block_count=0,
            )
            assert result['actual_seconds'] == 3600
            assert result['status'] == 'completed'
            assert result['ended_at']


class TestExecutionAPI:
    def test_start(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'test_item_id': 'TC-001', 'procedure_id': 't_001'
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['status'] == 'in_progress'

    def test_start_allows_when_other_performer_is_in_progress(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository

            ex = ExecutionRepository.start('TC-OTHER', 't_other', total_count=0)
            ExecutionRepository.update_performer('t_other', 'TC-OTHER', 'alice')

        exec_client.post('/execution/api/login', json={'username': 'bob'})
        r = exec_client.post('/execution/api/start', json={
            'test_item_id': 'TC-BOB', 'procedure_id': 't_bob'
        })
        assert r.status_code == 201
        assert r.get_json()['performer'] == 'bob'

    def test_start_blocks_when_current_user_is_already_in_progress(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.execution.repository import ExecutionRepository

            ex = ExecutionRepository.start('TC-ALICE', 't_alice', total_count=0)
            ExecutionRepository.update_performer('t_alice', 'TC-ALICE', 'alice')

        exec_client.post('/execution/api/login', json={'username': 'alice'})
        r = exec_client.post('/execution/api/start', json={
            'test_item_id': 'TC-NEW', 'procedure_id': 't_new'
        })
        assert r.status_code == 409
        assert r.get_json()['code'] == 'user_busy'

    def test_pause(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'test_item_id': 'TC-001', 'procedure_id': 't_001'
        })
        key = {'procedure_id': 't_001', 'test_item_id': 'TC-001'}
        r2 = exec_client.post('/execution/api/pause', json=key)
        assert r2.status_code == 200
        assert r2.get_json()['status'] == 'paused'

    def test_resume(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'test_item_id': 'TC-001', 'procedure_id': 't_001'
        })
        key = {'procedure_id': 't_001', 'test_item_id': 'TC-001'}
        exec_client.post('/execution/api/pause', json=key)
        r3 = exec_client.post('/execution/api/resume', json=key)
        assert r3.status_code == 200
        assert r3.get_json()['status'] == 'in_progress'

    def test_complete(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'test_item_id': 'TC-001', 'procedure_id': 't_001'
        })
        r2 = exec_client.post('/execution/api/complete', json={
            'procedure_id': 't_001', 'test_item_id': 'TC-001', 'fail_count': 3
        })
        assert r2.status_code == 200
        data = r2.get_json()
        assert data['status'] == 'completed'
        assert data['fail_count'] == 3

    def test_complete_accepts_result_counts_when_total_count_unknown(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.services import test_procedures as procedure_repo

            procedure = procedure_repo.create(
                document_id=5,
                assignee_names=[],
                location_name='',
                document_name='카운트 미정 문서',
                test_items=[
                    {'id': 'TC-UNKNOWN', 'name': '카운트 미정 시험', 'estimated_minutes': 10},
                ],
                estimated_minutes=10,
            )

        r = exec_client.post('/execution/api/start', json={
            'test_item_id': 'TC-UNKNOWN', 'procedure_id': procedure['id']
        })
        r2 = exec_client.post('/execution/api/complete', json={
            'procedure_id': procedure['id'], 'test_item_id': 'TC-UNKNOWN',
            'fail_count': 2, 'block_count': 1
        })

        assert r2.status_code == 200
        data = r2.get_json()
        assert data['total_count'] == 0
        assert data['fail_count'] == 2
        assert data['block_count'] == 1
        assert data['pass_count'] == 0

    def test_reset(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'test_item_id': 'TC-001', 'procedure_id': 't_001'
        })
        exec_client.post('/execution/api/complete', json={
            'procedure_id': 't_001', 'test_item_id': 'TC-001', 'fail_count': 1
        })
        r2 = exec_client.post('/execution/api/reset', json={
            'procedure_id': 't_001', 'test_item_id': 'TC-001',
        })
        assert r2.status_code == 200
        assert r2.get_json()['status'] == 'pending'

    def test_list(self, exec_client):
        r = exec_client.get('/execution/api/list')
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_list_includes_test_item_owners_for_author_column(
        self, exec_app, exec_client
    ):
        with exec_app.app_context():
            from app.features.schedule.services import test_procedures as procedure_repo

            procedure_repo.create(
                document_id=1,
                assignee_names=['테스트 담당자'],
                location_name='',
                document_name='작성자 문서',
                test_items=[
                    {
                        'id': 'TC-OWNER',
                        'name': '작성자 시험',
                        'estimated_minutes': 10,
                        'owners': ['Alice', 'Bob'],
                    },
                ],
                estimated_minutes=10,
            )

        r = exec_client.get('/execution/api/list')
        assert r.status_code == 200
        item = next(i for i in r.get_json() if i['test_item_id'] == 'TC-OWNER')
        assert item['owners'] == ['Alice', 'Bob']
        assert item['assignee_names'] == ['테스트 담당자']
        assert item['execution_status'] == 'pending'
        assert item['result_counts'] == {
            'fail_count': 0,
            'block_count': 0,
            'pass_count': 0,
            'total_count': 0,
        }

    def test_total_count(self, exec_client):
        r = exec_client.get('/execution/api/total-count/TC-001')
        assert r.status_code == 200
        assert 'total_count' in r.get_json()

    def test_total_count_uses_test_item_data_not_hardcoded_ten(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.services import test_procedures as procedure_repo

            procedure_repo.create(
                document_id=1,
                assignee_names=[],
                location_name='',
                document_name='카운트 문서',
                test_items=[
                    {'id': 'TC-COUNT', 'name': '카운트 시험', 'estimated_minutes': 10, 'total_count': 7},
                ],
                estimated_minutes=10,
            )

        r = exec_client.get('/execution/api/total-count/TC-COUNT')
        assert r.status_code == 200
        assert r.get_json()['total_count'] == 7

    def test_pending_item_uses_pf_num_as_total_count(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.services import test_procedures as procedure_repo

            procedure = procedure_repo.create(
                document_id=1,
                assignee_names=[],
                location_name='',
                document_name='PF 문서',
                test_items=[
                    {
                        'id': 'TC-PF',
                        'name': 'PF 시험',
                        'estimated_minutes': 10,
                        'pf_num': 12,
                    },
                ],
                estimated_minutes=10,
            )

        list_response = exec_client.get('/execution/api/list')
        item = next(i for i in list_response.get_json() if i['test_item_id'] == 'TC-PF')
        assert item['execution'] is None
        assert item['total_count'] == 12

        detail_response = exec_client.get(f'/execution/api/item/TC-PF?procedure_id={procedure["id"]}')
        assert detail_response.status_code == 200
        assert detail_response.get_json()['total_count'] == 12

        total_response = exec_client.get(
            f'/execution/api/total-count/TC-PF?procedure_id={procedure["id"]}'
        )
        assert total_response.status_code == 200
        assert total_response.get_json()['total_count'] == 12

    def test_complete_result_counts_and_completed_date_are_listed(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.services import test_procedures as procedure_repo
            from app.features.execution.repository import ExecutionRepository

            t = procedure_repo.create(
                document_id=2,
                assignee_names=[],
                location_name='',
                document_name='결과 문서',
                test_items=[
                    {'id': 'TC-RESULT', 'name': '결과 시험', 'estimated_minutes': 10, 'total_count': 9},
                ],
                estimated_minutes=10,
            )
            ex = ExecutionRepository.start('TC-RESULT', t['id'], total_count=9)
            done = ExecutionRepository.complete(
                t['id'], 'TC-RESULT', fail_count=2, block_count=3,
            )

        r = exec_client.get('/execution/api/list')
        item = next(i for i in r.get_json() if i['test_item_id'] == 'TC-RESULT')
        assert item['execution']['fail_count'] == 2
        assert item['execution']['block_count'] == 3
        assert item['execution']['pass_count'] == 4
        assert item['execution']['total_count'] == 9
        assert item['execution']['completed_at'] == done['completed_at']
        assert item['execution_status'] == 'completed'
        assert item['performer_name'] == ''
        assert item['result_counts'] == {
            'fail_count': 2,
            'block_count': 3,
            'pass_count': 4,
            'total_count': 9,
        }
        assert item['status_order'] == 3
        assert item['display_date'] == done['completed_at']
        assert item['actual_start_at'] == done['started_at']
        assert item['actual_end_at'] == done['completed_at']

        completed_items = exec_client.get(
            '/execution/api/list?status=completed'
        ).get_json()
        pending_items = exec_client.get(
            '/execution/api/list?status=pending'
        ).get_json()
        assert any(i['test_item_id'] == 'TC-RESULT' for i in completed_items)
        assert not any(i['test_item_id'] == 'TC-RESULT' for i in pending_items)
        multi_status_items = exec_client.get(
            '/execution/api/list?status=pending&status=completed'
        ).get_json()
        assert any(i['test_item_id'] == 'TC-RESULT' for i in multi_status_items)
        assert {
            item['execution_status'] for item in multi_status_items
        } <= {'pending', 'completed'}

    def test_list_uses_scheduled_block_location_per_procedure_test_item(self, exec_app, exec_client):
        with exec_app.app_context():
            from app.features.schedule.services import blocks as block_repo
            from app.features.schedule.services import test_procedures as procedure_repo

            loc_a = 'STE1'
            loc_b = 'STE2'
            procedure1 = procedure_repo.create(
                document_id=3,
                assignee_names=[],
                document_name='원본',
                test_items=[{'id': 'TC-SAME', 'name': '원본 시험', 'estimated_minutes': 10}],
                estimated_minutes=10,
            )
            procedure2 = procedure_repo.create(
                document_id=4,
                assignee_names=[],
                document_name='재시험',
                test_items=[{'id': 'TC-SAME', 'name': '재시험', 'estimated_minutes': 10}],
                estimated_minutes=10,
                test_round=2,
            )
            block_repo.create(
                procedure_id=procedure1['id'],
                assignee_names=[],
                location_name=loc_a,
                date='2026-07-01',
                start_time='09:00',
                end_time='10:00',
                test_item_ids=['TC-SAME'],
            )
            block_repo.create(
                procedure_id=procedure2['id'],
                assignee_names=[],
                location_name=loc_b,
                date='2026-07-01',
                start_time='10:00',
                end_time='11:00',
                test_item_ids=['TC-SAME'],
            )

        r = exec_client.get('/execution/api/list')
        items = {i['procedure_id']: i for i in r.get_json() if i['test_item_id'] == 'TC-SAME'}
        assert items[procedure1['id']]['location_name'] == 'STE1'
        assert items[procedure2['id']]['location_name'] == 'STE2'
        assert items[procedure1['id']]['scheduled_date'] == '2026-07-01'
        assert items[procedure1['id']]['scheduled_start_time'] == '09:00'
        assert items[procedure1['id']]['scheduled_end_time'] == '10:15'
        assert items[procedure2['id']]['scheduled_start_time'] == '10:00'
        assert items[procedure2['id']]['scheduled_end_time'] == '11:00'

        filtered = exec_client.get(
            f'/execution/api/list?procedure_id={procedure2["id"]}'
            '&location=STE2&status=pending'
        ).get_json()
        same_items = [i for i in filtered if i['test_item_id'] == 'TC-SAME']
        assert [item['procedure_id'] for item in same_items] == [procedure2['id']]

        multi_filtered = exec_client.get(
            f'/execution/api/list?procedure_id={procedure1["id"]}'
            f'&procedure_id={procedure2["id"]}'
            '&location=STE1&location=STE2&status=pending'
        ).get_json()
        same_items = [
            item for item in multi_filtered
            if item['test_item_id'] == 'TC-SAME'
        ]
        assert {item['procedure_id'] for item in same_items} == {
            procedure1['id'], procedure2['id'],
        }

    def test_execution_page(self, exec_client):
        r = exec_client.get('/execution/')
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert 'id="filter-document"' not in html
        assert 'id="col-toggle-menu"' in html
        assert 'openProcedureMetricsModal()' in html
        assert 'id="procedureMetricsModal"' in html

    def test_daily_procedure_metrics_use_unique_procedure_and_completion_date(
        self, exec_app, exec_client,
    ):
        with exec_app.app_context():
            from app.features.execution.domain import ExecutionRun, Executions
            from app.features.schedule.services.blocks import ScheduleBlockService
            from app.features.schedule.services.test_procedures import TestProcedureService
            from app.repositories import JsonDomainRepository, get_repository

            TestProcedureService(get_repository()).create_procedure({
                'id': 't_metrics', 'document_id': 20, 'document_name': '실적 집계',
                'test_items': [{'id': 'TC-M1'}, {'id': 'TC-M2'}],
            })
            TestProcedureService(get_repository()).create_procedure({
                'id': 't_partial', 'document_id': 21, 'document_name': '일부 실행',
                'test_items': [{'id': 'TC-P1'}, {'id': 'TC-P2'}],
            })
            blocks = ScheduleBlockService(get_repository())
            blocks.create({
                'procedure_id': 't_metrics', 'test_item_ids': ['TC-M1'],
                'date': '2026-08-10',
                'start_time': '09:00', 'end_time': '10:00', 'location_name': 'STE1',
            })
            # 같은 날짜에 같은 절차서가 여러 블록이어도 예정 수는 한 건이다.
            blocks.create({
                'procedure_id': 't_metrics', 'test_item_ids': ['TC-M2'],
                'date': '2026-08-10',
                'start_time': '10:00', 'end_time': '11:00', 'location_name': 'STE3',
            })
            blocks.create({
                'procedure_id': 't_bob', 'date': '2026-08-10',
                'start_time': '09:00', 'end_time': '10:00', 'location_name': 'STE2',
            })
            JsonDomainRepository(exec_app.config['DOMAIN_DATA_DIR']).replace_executions(
                Executions(runs=(
                    ExecutionRun(
                        procedure_id='t_metrics', test_item_id='TC-M1',
                        status='completed', started_at='2026-08-11T09:00:00',
                        ended_at='2026-08-12T15:00:00', fail_count=1,
                    ),
                    ExecutionRun(
                        procedure_id='t_metrics', test_item_id='TC-M2',
                        status='completed', started_at='2026-08-11T09:30:00',
                        ended_at='2026-08-12T16:00:00',
                        block_count=1,
                    ),
                    # 다음 날 재개하여 끝난 절차서는 실제 종료일에 완료로 집계한다.
                    ExecutionRun(
                        procedure_id='t_bob', test_item_id='TC-BOB',
                        status='completed', started_at='2026-08-11T10:00:00',
                        ended_at='2026-08-13T11:00:00',
                    ),
                    # 형제 항목이 미실행이어도 완료된 실행이 있으면 절차서를 집계한다.
                    ExecutionRun(
                        procedure_id='t_partial', test_item_id='TC-P1',
                        status='completed', started_at='2026-08-12T10:00:00',
                        ended_at='2026-08-13T12:00:00', fail_count=1,
                    ),
                ))
            )

        response = exec_client.get(
            '/execution/api/analytics/daily-procedures'
            '?start_date=2026-08-10&end_date=2026-08-13'
        )
        assert response.status_code == 200
        data = response.get_json()
        by_date = {day['date']: day for day in data['days']}
        assert by_date['2026-08-10']['planned_count'] == 2
        assert by_date['2026-08-11']['started_count'] == 2
        assert by_date['2026-08-12']['completed_procedure_ids'] == ['t_metrics']
        assert by_date['2026-08-12']['failed_count'] == 1
        assert by_date['2026-08-12']['blocked_count'] == 1
        assert by_date['2026-08-12']['failed_or_blocked_count'] == 1
        assert by_date['2026-08-13']['completed_procedure_ids'] == ['t_bob', 't_partial']
        assert by_date['2026-08-13']['failed_procedure_ids'] == ['t_partial']

    def test_daily_procedure_metrics_reject_reversed_range(self, exec_client):
        response = exec_client.get(
            '/execution/api/analytics/daily-procedures'
            '?start_date=2026-08-13&end_date=2026-08-10'
        )
        assert response.status_code == 400

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
