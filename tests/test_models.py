"""Tests for schedule.models (repositories)."""
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


# ===========================================================================
# Location model
# ===========================================================================

class TestLocationModel:
    def test_create_location(self, app):
        with app.app_context():
            from app.features.schedule.models import location
            loc = location.create(name='A', color='#28a745', description='1층 시험실')
            assert loc['id'].startswith('loc_')
            assert loc['name'] == 'A'
            assert loc['description'] == '1층 시험실'

    def test_get_all_locations(self, app):
        with app.app_context():
            from app.features.schedule.models import location
            location.create(name='A', color='#28a745')
            location.create(name='B', color='#6f42c1')
            assert len(location.get_all()) == 2

    def test_update_location(self, app):
        with app.app_context():
            from app.features.schedule.models import location
            loc = location.create(name='A', color='#28a745')
            updated = location.update(loc['id'], name='A-1', color='#ff0000', description='updated')
            assert updated['name'] == 'A-1'
            assert updated['description'] == 'updated'

    def test_delete_location(self, app):
        with app.app_context():
            from app.features.schedule.models import location
            loc = location.create(name='A', color='#28a745')
            location.delete(loc['id'])
            assert len(location.get_all()) == 0


# ===========================================================================
# Version model
# ===========================================================================

class TestVersionModel:
    def test_create_version(self, app):
        with app.app_context():
            from app.features.schedule.models import version
            v = version.create(name='v1.0.0', description='Initial')
            assert v['id'].startswith('v_')
            assert v['name'] == 'v1.0.0'
            assert v['is_active'] is True

    def test_get_all_versions(self, app):
        with app.app_context():
            from app.features.schedule.models import version
            version.create(name='v1.0.0', description='')
            version.create(name='v2.0.0', description='')
            assert len(version.get_all()) == 2

    def test_get_by_id(self, app):
        with app.app_context():
            from app.features.schedule.models import version
            v = version.create(name='v1.0.0', description='test')
            found = version.get_by_id(v['id'])
            assert found['name'] == 'v1.0.0'
            assert version.get_by_id('v_nonexist') is None

    def test_update_version(self, app):
        with app.app_context():
            from app.features.schedule.models import version
            v = version.create(name='v1.0.0', description='old')
            updated = version.update(v['id'], name='v1.1.0', description='new', is_active=False)
            assert updated['name'] == 'v1.1.0'
            assert updated['is_active'] is False

    def test_delete_version(self, app):
        with app.app_context():
            from app.features.schedule.models import version
            v = version.create(name='v1.0.0', description='')
            version.delete(v['id'])
            assert len(version.get_all()) == 0

    def test_get_active_versions(self, app):
        with app.app_context():
            from app.features.schedule.models import version
            version.create(name='v1.0.0', description='')
            v2 = version.create(name='v2.0.0', description='')
            version.update(v2['id'], name='v2.0.0', description='', is_active=False)
            active = version.get_active()
            assert len(active) == 1
            assert active[0]['name'] == 'v1.0.0'


# ===========================================================================
# Task model
# ===========================================================================

class TestTaskModel:
    def test_create_task_new_fields(self, app):
        with app.app_context():
            from app.features.schedule.models import task
            t = task.create(
                doc_id=1001,
                version_id='v_test1234',
                assignee_names=['홍길동', '김민수'],
                location_id='loc_test1234',
                doc_name='통신 기능',
                
                identifiers=['TC-001', 'TC-002'],
                estimated_minutes=240,
                memo='테스트 메모',
            )
            assert t['id'].startswith('t_')
            assert t['doc_id'] == 1001
            assert t['assignee_names'] == ['홍길동', '김민수']
            assert t['location_id'] == 'loc_test1234'
            assert t['version_id'] == 'v_test1234'
            assert t['doc_name'] == '통신 기능'
            assert True
            assert t['identifiers'] == ['TC-001', 'TC-002']
            assert t['remaining_minutes'] == 240
            assert t['status'] == 'waiting'
            assert t['memo'] == '테스트 메모'

    def test_update_task_new_fields(self, app):
        with app.app_context():
            from app.features.schedule.models import task
            t = task.create(
                doc_id=1001, version_id='v_1',
                assignee_names=['홍길동'], location_id='loc_1',
                doc_name='sec', 
                identifiers=['TC-001'], estimated_minutes=240,
                memo='',
            )
            updated = task.update(
                t['id'],
                doc_id=1002, version_id='v_2',
                assignee_names=['이지은', '박준혁'], location_id='loc_2',
                doc_name='new sec', 
                identifiers=['TC-003'], estimated_minutes=360,
                remaining_minutes=180,
                status='in_progress', memo='updated',
            )
            assert updated['doc_id'] == 1002
            assert updated['assignee_names'] == ['이지은', '박준혁']
            assert updated['remaining_minutes'] == 180

    def test_patch_task(self, app):
        with app.app_context():
            from app.features.schedule.models import task
            t = task.create(
                doc_id=1001, version_id='v_1',
                assignee_names=['홍길동'], location_id='loc_1',
                doc_name='sec', 
                identifiers=[], estimated_minutes=240,
                memo='',
            )
            patched = task.patch(t['id'], memo='patched memo')
            assert patched['memo'] == 'patched memo'
            assert patched['doc_id'] == 1001

# ===========================================================================
# Schedule block model
# ===========================================================================

class TestScheduleBlockModel:
    def test_get_by_location_and_date(self, app):
        with app.app_context():
            from app.features.schedule.models import schedule_block
            schedule_block.create(
                task_id='t_1', assignee_names=['A'], location_id='loc_1',
                date='2026-04-01',
                start_time='08:30', end_time='10:00',
            )
            schedule_block.create(
                task_id='t_2', assignee_names=['B'], location_id='loc_2',
                date='2026-04-01',
                start_time='08:30', end_time='10:00',
            )
            loc1 = schedule_block.get_by_location_and_date('loc_1', '2026-04-01')
            assert len(loc1) == 1

    def test_update_block_allowed_fields(self, app):
        with app.app_context():
            from app.features.schedule.models import schedule_block
            block = schedule_block.create(
                task_id='t_1', assignee_names=['A'], location_id='loc_1',
                date='2026-04-01',
                start_time='08:30', end_time='10:00',
            )
            updated = schedule_block.update(block['id'], location_id='loc_2', start_time='09:00')
            assert updated['location_id'] == 'loc_2'
            assert updated['start_time'] == '09:00'
