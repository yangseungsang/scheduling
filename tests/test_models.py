"""Tests for schedule.models (repositories)."""
import pytest
from app import create_app
from tests.conftest import configure_test_storage


@pytest.fixture
def app(tmp_path):
    application = create_app()
    application.config['TESTING'] = True
    configure_test_storage(application, tmp_path, {
        'work_start': '08:00', 'work_end': '17:00',
        'actual_work_start': '08:30', 'actual_work_end': '16:30',
        'lunch_start': '12:00', 'lunch_end': '13:00',
        'breaks': [], 'grid_interval_minutes': 15,
        'max_schedule_days': 14, 'block_color_by': 'assignee',
    })
    yield application


# ===========================================================================
# TestProcedure model
# ===========================================================================

class TestTestProcedureModel:
    def test_create_procedure_new_fields(self, app):
        with app.app_context():
            from app.features.schedule.services import test_procedures as procedure
            t = procedure.create(
                document_id=1001,
                assignee_names=['홍길동', '김민수'],
                location_name='loc_test1234',
                document_name='통신 기능',

                test_items=['TC-001', 'TC-002'],
                estimated_minutes=240,
                memo='테스트 메모',
            )
            assert t['id'].startswith('tp_')
            assert t['document_id'] == '1001'
            assert t['assignee_names'] == ['홍길동', '김민수']
            assert t['location_name'] == 'loc_test1234'
            assert t['document_name'] == '통신 기능'
            assert True
            assert [item['id'] for item in t['test_items']] == ['TC-001', 'TC-002']
            assert t['remaining_minutes'] == 240
            assert t['memo'] == '테스트 메모'

    def test_update_procedure_new_fields(self, app):
        with app.app_context():
            from app.features.schedule.services import test_procedures as procedure
            t = procedure.create(
                document_id=1001,
                assignee_names=['홍길동'], location_name='loc_1',
                document_name='sec',
                test_items=['TC-001'], estimated_minutes=240,
                memo='',
            )
            updated = procedure.update(
                t['id'],
                document_id=1002,
                assignee_names=['이지은', '박준혁'], location_name='loc_2',
                document_name='new sec',
                test_items=['TC-003'], estimated_minutes=360,
                memo='updated',
            )
            assert updated['document_id'] == '1002'
            assert updated['assignee_names'] == ['이지은', '박준혁']
            assert updated['remaining_minutes'] == 360

    def test_patch_procedure(self, app):
        with app.app_context():
            from app.features.schedule.services import test_procedures as procedure
            t = procedure.create(
                document_id=1001,
                assignee_names=['홍길동'], location_name='loc_1',
                document_name='sec',
                test_items=['TC-001'], estimated_minutes=240,
                memo='',
            )
            patched = procedure.patch(t['id'], memo='patched memo')
            assert patched['memo'] == 'patched memo'
            assert patched['document_id'] == '1001'

# ===========================================================================
# Schedule block model
# ===========================================================================

class TestScheduleBlockModel:
    def test_get_by_location_and_date(self, app):
        with app.app_context():
            from app.features.schedule.services import blocks as schedule_block
            schedule_block.create(
                procedure_id=None, assignee_names=['A'], location_name='loc_1',
                date='2026-04-01',
                start_time='08:30', end_time='10:00',
                is_simple=True, title='A',
            )
            schedule_block.create(
                procedure_id=None, assignee_names=['B'], location_name='loc_2',
                date='2026-04-01',
                start_time='08:30', end_time='10:00',
                is_simple=True, title='B',
            )
            loc1 = schedule_block.get_by_location_and_date('loc_1', '2026-04-01')
            assert len(loc1) == 1

    def test_update_block_allowed_fields(self, app):
        with app.app_context():
            from app.features.schedule.services import blocks as schedule_block
            block = schedule_block.create(
                procedure_id=None, assignee_names=['A'], location_name='loc_1',
                date='2026-04-01',
                start_time='08:30', end_time='10:00',
                is_simple=True, title='A',
            )
            updated = schedule_block.update(block['id'], location_name='loc_2', start_time='09:00')
            assert updated['location_name'] == 'loc_2'
            assert updated['start_time'] == '09:00'
