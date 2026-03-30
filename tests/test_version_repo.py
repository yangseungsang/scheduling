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


def test_create_version(app):
    with app.app_context():
        from app.repositories import version_repo
        v = version_repo.create(name='v1.0.0', description='Initial')
        assert v['id'].startswith('v_')
        assert v['name'] == 'v1.0.0'
        assert v['is_active'] is True


def test_get_all_versions(app):
    with app.app_context():
        from app.repositories import version_repo
        version_repo.create(name='v1.0.0', description='')
        version_repo.create(name='v2.0.0', description='')
        assert len(version_repo.get_all()) == 2


def test_get_by_id(app):
    with app.app_context():
        from app.repositories import version_repo
        v = version_repo.create(name='v1.0.0', description='test')
        found = version_repo.get_by_id(v['id'])
        assert found['name'] == 'v1.0.0'
        assert version_repo.get_by_id('v_nonexist') is None


def test_update_version(app):
    with app.app_context():
        from app.repositories import version_repo
        v = version_repo.create(name='v1.0.0', description='old')
        updated = version_repo.update(v['id'], name='v1.1.0', description='new', is_active=False)
        assert updated['name'] == 'v1.1.0'
        assert updated['is_active'] is False


def test_delete_version(app):
    with app.app_context():
        from app.repositories import version_repo
        v = version_repo.create(name='v1.0.0', description='')
        version_repo.delete(v['id'])
        assert len(version_repo.get_all()) == 0


def test_get_active_versions(app):
    with app.app_context():
        from app.repositories import version_repo
        version_repo.create(name='v1.0.0', description='')
        v2 = version_repo.create(name='v2.0.0', description='')
        version_repo.update(v2['id'], name='v2.0.0', description='', is_active=False)
        active = version_repo.get_active()
        assert len(active) == 1
        assert active[0]['name'] == 'v1.0.0'
