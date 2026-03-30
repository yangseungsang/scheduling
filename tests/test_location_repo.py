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


def test_create_location(app):
    with app.app_context():
        from app.repositories import location_repo
        loc = location_repo.create(name='A', color='#28a745', description='1층 시험실')
        assert loc['id'].startswith('loc_')
        assert loc['name'] == 'A'
        assert loc['description'] == '1층 시험실'


def test_get_all_locations(app):
    with app.app_context():
        from app.repositories import location_repo
        location_repo.create(name='A', color='#28a745')
        location_repo.create(name='B', color='#6f42c1')
        assert len(location_repo.get_all()) == 2


def test_update_location(app):
    with app.app_context():
        from app.repositories import location_repo
        loc = location_repo.create(name='A', color='#28a745')
        updated = location_repo.update(loc['id'], name='A-1', color='#ff0000', description='updated')
        assert updated['name'] == 'A-1'
        assert updated['description'] == 'updated'


def test_delete_location(app):
    with app.app_context():
        from app.repositories import location_repo
        loc = location_repo.create(name='A', color='#28a745')
        location_repo.delete(loc['id'])
        assert len(location_repo.get_all()) == 0
