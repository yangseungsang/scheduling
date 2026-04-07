"""Tests for schedule.services (procedure lookup)."""
import json
import os
import pytest
from schedule import create_app


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
                'procedure_id': 'SYS-001',
                'section_name': '3.1 시스템 초기화',
                'procedure_owner': '김민수',
                'test_list': [
                    {'id': 'TC-001', 'estimated_minutes': 0},
                    {'id': 'TC-002', 'estimated_minutes': 0},
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
            from schedule.services.procedure import lookup
            result = lookup('SYS-001')
            assert result is not None
            assert result['section_name'] == '3.1 시스템 초기화'

    def test_lookup_missing(self, app):
        with app.app_context():
            from schedule.services.procedure import lookup
            result = lookup('NONEXIST-001')
            assert result is None
