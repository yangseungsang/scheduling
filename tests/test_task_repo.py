import json
import os
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions'):
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
    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


def test_create_task_new_fields(app):
    with app.app_context():
        from app.repositories import task_repo
        task = task_repo.create(
            procedure_id='ABC-001',
            version_id='v_test1234',
            assignee_ids=['u_aaa', 'u_bbb'],
            location_id='loc_test1234',
            section_name='3.2 통신 기능',
            procedure_owner='홍길동',
            test_list=['TC-001', 'TC-002'],
            estimated_hours=4.0,
            deadline='2026-04-15',
            memo='테스트 메모',
        )
        assert task['id'].startswith('t_')
        assert task['procedure_id'] == 'ABC-001'
        assert task['assignee_ids'] == ['u_aaa', 'u_bbb']
        assert task['location_id'] == 'loc_test1234'
        assert task['version_id'] == 'v_test1234'
        assert task['section_name'] == '3.2 통신 기능'
        assert task['procedure_owner'] == '홍길동'
        assert task['test_list'] == ['TC-001', 'TC-002']
        assert task['remaining_hours'] == 4.0
        assert task['status'] == 'waiting'
        assert task['memo'] == '테스트 메모'


def test_update_task_new_fields(app):
    with app.app_context():
        from app.repositories import task_repo
        task = task_repo.create(
            procedure_id='ABC-001', version_id='v_1',
            assignee_ids=['u_aaa'], location_id='loc_1',
            section_name='sec', procedure_owner='owner',
            test_list=['TC-001'], estimated_hours=4.0,
            deadline='2026-04-15', memo='',
        )
        updated = task_repo.update(
            task['id'],
            procedure_id='ABC-002', version_id='v_2',
            assignee_ids=['u_bbb', 'u_ccc'], location_id='loc_2',
            section_name='new sec', procedure_owner='new owner',
            test_list=['TC-003'], estimated_hours=6.0,
            remaining_hours=3.0, deadline='2026-05-01',
            status='in_progress', memo='updated',
        )
        assert updated['procedure_id'] == 'ABC-002'
        assert updated['assignee_ids'] == ['u_bbb', 'u_ccc']
        assert updated['remaining_hours'] == 3.0


def test_patch_task(app):
    with app.app_context():
        from app.repositories import task_repo
        task = task_repo.create(
            procedure_id='ABC-001', version_id='v_1',
            assignee_ids=['u_aaa'], location_id='loc_1',
            section_name='sec', procedure_owner='owner',
            test_list=[], estimated_hours=4.0,
            deadline='2026-04-15', memo='',
        )
        patched = task_repo.patch(task['id'], memo='patched memo')
        assert patched['memo'] == 'patched memo'
        assert patched['procedure_id'] == 'ABC-001'


def test_get_by_version(app):
    with app.app_context():
        from app.repositories import task_repo
        task_repo.create(
            procedure_id='ABC-001', version_id='v_1',
            assignee_ids=[], location_id='',
            section_name='', procedure_owner='',
            test_list=[], estimated_hours=2.0,
            deadline='', memo='',
        )
        task_repo.create(
            procedure_id='ABC-002', version_id='v_2',
            assignee_ids=[], location_id='',
            section_name='', procedure_owner='',
            test_list=[], estimated_hours=3.0,
            deadline='', memo='',
        )
        v1_tasks = task_repo.get_by_version('v_1')
        assert len(v1_tasks) == 1
        assert v1_tasks[0]['procedure_id'] == 'ABC-001'
