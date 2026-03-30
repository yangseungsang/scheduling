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
            'breaks': [],
            'grid_interval_minutes': 15,
            'max_schedule_days': 14,
            'block_color_by': 'assignee',
        }, f)
    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


def _make_task(app, procedure_id='ABC-001', version_id='v_1',
               assignee_ids=None, location_id='loc_1',
               hours=3.0, deadline='2026-04-15'):
    with app.app_context():
        from app.repositories import task_repo
        return task_repo.create(
            procedure_id=procedure_id, version_id=version_id,
            assignee_ids=assignee_ids or ['u_a'],
            location_id=location_id,
            section_name='test', procedure_owner='owner',
            test_list=[], estimated_hours=hours,
            deadline=deadline, memo='',
        )


def test_same_day_completion(app):
    task = _make_task(app, hours=3.0)
    with app.app_context():
        from app.services.scheduler import generate_draft_schedule
        result = generate_draft_schedule(version_id='v_1')
        assert len(result['placed']) >= 1
        dates = set(b['date'] for b in result['placed'] if b['task_id'] == task['id'])
        assert len(dates) == 1


def test_task_exceeding_daily_hours_unplaced(app):
    _make_task(app, hours=20.0)
    with app.app_context():
        from app.services.scheduler import generate_draft_schedule
        result = generate_draft_schedule(version_id='v_1')
        assert len(result['unplaced']) == 1


def test_version_filter(app):
    _make_task(app, procedure_id='ABC-001', version_id='v_1', hours=2.0)
    _make_task(app, procedure_id='DEF-001', version_id='v_2', hours=2.0)
    with app.app_context():
        from app.services.scheduler import generate_draft_schedule
        result = generate_draft_schedule(version_id='v_1')
        task_ids_placed = set(b['task_id'] for b in result['placed'])
        from app.repositories import task_repo
        for tid in task_ids_placed:
            t = task_repo.get_by_id(tid)
            assert t['version_id'] == 'v_1'


def test_location_conflict_prevention(app):
    _make_task(app, procedure_id='ABC-001', version_id='v_1',
               assignee_ids=['u_a'], location_id='loc_1', hours=3.0)
    _make_task(app, procedure_id='ABC-002', version_id='v_1',
               assignee_ids=['u_b'], location_id='loc_1', hours=3.0)
    with app.app_context():
        from app.services.scheduler import generate_draft_schedule
        from app.utils.time_utils import time_to_minutes
        result = generate_draft_schedule(version_id='v_1')
        blocks_by_date_loc = {}
        for b in result['placed']:
            key = (b['date'], b['location_id'])
            blocks_by_date_loc.setdefault(key, []).append(b)
        for key, blist in blocks_by_date_loc.items():
            for i, b1 in enumerate(blist):
                for b2 in blist[i+1:]:
                    s1, e1 = time_to_minutes(b1['start_time']), time_to_minutes(b1['end_time'])
                    s2, e2 = time_to_minutes(b2['start_time']), time_to_minutes(b2['end_time'])
                    assert not (s1 < e2 and s2 < e1), f"Location overlap: {b1} vs {b2}"
