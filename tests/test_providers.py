"""Tests for schedule.providers (BaseProvider / JsonFileProvider)."""
import json
import os
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    """Create a Flask app with tmp data dir containing versions and procedures."""
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)

    # Seed versions
    versions = [
        {'id': 'v_aaa', 'name': 'v1.0', 'description': 'First release'},
        {'id': 'v_bbb', 'name': 'v2.0', 'description': 'Second release'},
    ]
    with open(os.path.join(data_dir, 'versions.json'), 'w') as f:
        json.dump(versions, f)

    # Seed procedures (new format with version_id + identifiers)
    procedures = [
        {
            'section_name': 'Navigation',
            'version_id': 'v_aaa',
            'identifiers': [
                {'id': 'TC-001', 'estimated_minutes': 120, 'owners': ['Alice']},
                {'id': 'TC-002', 'estimated_minutes': 60, 'owners': ['Bob']},
            ],
        },
        {
            'section_name': 'Communication',
            'version_id': 'v_bbb',
            'identifiers': [
                {'id': 'TC-100', 'estimated_minutes': 180, 'owners': ['Charlie']},
            ],
        },
    ]
    with open(os.path.join(data_dir, 'procedures.json'), 'w') as f:
        json.dump(procedures, f)

    # Minimal required data files
    for name in ('users', 'locations', 'tasks', 'schedule_blocks'):
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


class TestJsonFileProvider:
    def test_get_versions(self, app):
        with app.app_context():
            from app.features.schedule.providers.json_file import JsonFileProvider
            provider = JsonFileProvider()
            versions = provider.get_versions()
            assert len(versions) == 2
            assert versions[0] == {'id': 'v_aaa', 'name': 'v1.0', 'description': 'First release'}
            assert versions[1] == {'id': 'v_bbb', 'name': 'v2.0', 'description': 'Second release'}

    def test_get_test_data_by_version(self, app):
        with app.app_context():
            from app.features.schedule.providers.json_file import JsonFileProvider
            provider = JsonFileProvider()
            data = provider.get_test_data('v_aaa')
            assert len(data) == 1
            assert data[0]['section_name'] == 'Navigation'
            assert data[0]['version_id'] == 'v_aaa'
            assert len(data[0]['identifiers']) == 2
            assert data[0]['identifiers'][0]['id'] == 'TC-001'

    def test_get_test_data_all(self, app):
        with app.app_context():
            from app.features.schedule.providers.json_file import JsonFileProvider
            provider = JsonFileProvider()
            data = provider.get_test_data_all()
            assert len(data) == 2
            version_ids = {item['version_id'] for item in data}
            assert version_ids == {'v_aaa', 'v_bbb'}

    def test_get_test_data_nonexistent_version(self, app):
        with app.app_context():
            from app.features.schedule.providers.json_file import JsonFileProvider
            provider = JsonFileProvider()
            data = provider.get_test_data('v_nonexistent')
            assert data == []
