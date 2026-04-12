"""Tests for schedule.services (procedure lookup)."""
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
    with open(os.path.join(data_dir, 'procedures.json'), 'w') as f:
        json.dump([
            {
                'version_id': 'MAE31F',
                'doc_id': 1,
                'doc_name': '시스템 초기화',
                'identifiers': [
                    {'id': 'TC-001', 'name': '전원 투입', 'owners': ['김민수'], 'estimated_minutes': 12},
                    {'id': 'TC-002', 'name': '초기화 검증', 'owners': ['김민수'], 'estimated_minutes': 45},
                ],
            }
        ], f)
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


class TestProcedureLookup:
    def test_lookup_existing(self, app):
        with app.app_context():
            from app.features.schedule.services.procedure import lookup
            result = lookup(1)
            assert result is not None
            assert result['doc_id'] == 1
            assert result['doc_name'] == '시스템 초기화'
            assert result['version_id'] == 'MAE31F'
            assert len(result['identifiers']) == 2
            assert result['identifiers'][0]['owners'] == ['김민수']

    def test_lookup_missing(self, app):
        with app.app_context():
            from app.features.schedule.services.procedure import lookup
            assert lookup(9999) is None
            assert lookup('not-a-number') is None
