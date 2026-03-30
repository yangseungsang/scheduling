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


def test_create_block_new_fields(app):
    with app.app_context():
        from app.repositories import schedule_repo
        block = schedule_repo.create(
            task_id='t_test',
            assignee_ids=['u_aaa', 'u_bbb'],
            location_id='loc_test',
            version_id='v_test',
            date='2026-04-01',
            start_time='08:30',
            end_time='12:00',
        )
        assert block['id'].startswith('sb_')
        assert block['assignee_ids'] == ['u_aaa', 'u_bbb']
        assert block['location_id'] == 'loc_test'
        assert block['version_id'] == 'v_test'


def test_get_by_version(app):
    with app.app_context():
        from app.repositories import schedule_repo
        schedule_repo.create(
            task_id='t_1', assignee_ids=['u_a'], location_id='loc_1',
            version_id='v_1', date='2026-04-01',
            start_time='08:30', end_time='10:00',
        )
        schedule_repo.create(
            task_id='t_2', assignee_ids=['u_b'], location_id='loc_2',
            version_id='v_2', date='2026-04-01',
            start_time='10:00', end_time='12:00',
        )
        v1_blocks = schedule_repo.get_by_version('v_1')
        assert len(v1_blocks) == 1


def test_get_by_location_and_date(app):
    with app.app_context():
        from app.repositories import schedule_repo
        schedule_repo.create(
            task_id='t_1', assignee_ids=['u_a'], location_id='loc_1',
            version_id='v_1', date='2026-04-01',
            start_time='08:30', end_time='10:00',
        )
        schedule_repo.create(
            task_id='t_2', assignee_ids=['u_b'], location_id='loc_2',
            version_id='v_1', date='2026-04-01',
            start_time='08:30', end_time='10:00',
        )
        loc1 = schedule_repo.get_by_location_and_date('loc_1', '2026-04-01')
        assert len(loc1) == 1


def test_update_block_allowed_fields(app):
    with app.app_context():
        from app.repositories import schedule_repo
        block = schedule_repo.create(
            task_id='t_1', assignee_ids=['u_a'], location_id='loc_1',
            version_id='v_1', date='2026-04-01',
            start_time='08:30', end_time='10:00',
        )
        updated = schedule_repo.update(block['id'], location_id='loc_2', start_time='09:00')
        assert updated['location_id'] == 'loc_2'
        assert updated['start_time'] == '09:00'
