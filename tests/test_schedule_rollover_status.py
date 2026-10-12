"""Regression coverage for workday rollover and shared execution status."""
import pytest

from app.features.execution.models.execution import ExecutionRepository
from app.features.schedule.helpers.enrichment import build_maps, enrich_blocks
from app.features.schedule.helpers.time_utils import work_minutes_in_range
from app.features.schedule.models import schedule_block, settings, task
from tests.conftest import _create_block, _create_task, _create_user, _create_location


@pytest.fixture
def workday(app):
    with app.app_context():
        settings.update({'actual_work_start': '08:30', 'actual_work_end': '17:00', 'breaks': []})


def test_create_rolls_over_without_losing_minutes(client, app, workday):
    uid = _create_user(client)
    tid = _create_task(client, uid)
    block, code = _create_block(client, tid, uid, date_str='2026-10-09',
                                start='16:30', end='18:00', identifier_ids=['TC-001'])
    assert code == 201
    assert block['end_time'] == '17:00'
    following = block['continuations'][0]
    assert (following['date'], following['start_time'], following['end_time']) == (
        '2026-10-12', '08:30', '09:30')
    assert following['identifier_ids'] == ['TC-001']
    with app.app_context():
        total = sum(work_minutes_in_range(b['start_time'], b['end_time'], settings.get())
                    for b in schedule_block.get_all())
        assert total == 90


@pytest.mark.parametrize('changes,expected', [
    ({'start_time': '16:30', 'end_time': '18:00'}, 60),
    ({'end_time': '18:00', 'resize': True}, 90),
    ({'duration_minutes': 120}, 120),
])
def test_update_rolls_over(client, app, workday, changes, expected):
    uid = _create_user(client)
    tid = _create_task(client, uid)
    start = '16:30' if 'start_time' not in changes else '09:00'
    end = '17:00' if start == '16:30' else '10:00'
    block, _ = _create_block(client, tid, uid, start=start, end=end)
    r = client.put('/schedule/api/blocks/' + block['id'], json=changes)
    assert r.status_code == 200
    assert r.json['end_time'] == '17:00'
    assert r.json['continuation']['date'] == '2026-03-11'
    with app.app_context():
        assert sum(work_minutes_in_range(b['start_time'], b['end_time'], settings.get())
                   for b in schedule_block.get_all()) == expected


@pytest.mark.parametrize('update', [False, True])
def test_conflict_keeps_original_schedule(client, app, workday, update):
    uid = _create_user(client)
    lid = _create_location(client)
    tid = _create_task(client, uid, loc_id=lid)
    _create_block(client, tid, uid, date_str='2026-03-11', start='08:30', end='09:30')
    if update:
        block, _ = _create_block(client, tid, uid, start='15:30', end='16:30')
    with app.app_context():
        before = schedule_block.get_all()
    payload = {'date': '2026-03-10', 'start_time': '16:30', 'end_time': '18:00'}
    if update:
        r = client.put('/schedule/api/blocks/' + block['id'], json=payload)
    else:
        r = client.post('/schedule/api/blocks', json=dict(payload, task_id=tid, assignee_names=[uid]))
    assert r.status_code == 409
    with app.app_context():
        assert schedule_block.get_all() == before


def test_simple_block_and_start_after_end_roll_over(client, workday):
    r = client.post('/schedule/api/blocks', json={
        'is_simple': True, 'title': '회의', 'date': '2026-03-10',
        'start_time': '17:00', 'end_time': '18:00'})
    assert r.status_code == 201
    assert (r.json['date'], r.json['start_time'], r.json['end_time']) == (
        '2026-03-11', '08:30', '09:30')
    assert r.json['title'] == '회의'


def test_multiple_days_preserve_lunch_and_work_duration(client, app, workday):
    uid = _create_user(client)
    tid = _create_task(client, uid)
    block, code = _create_block(client, tid, uid, start='16:00', end='34:00')
    assert code == 201
    assert len(block['continuations']) == 3
    with app.app_context():
        assert sum(work_minutes_in_range(b['start_time'], b['end_time'], settings.get())
                   for b in schedule_block.get_all()) == 1080


def test_block_status_updates_execution_and_all_calendar_views(client, app):
    uid = _create_user(client)
    tid = _create_task(client, uid)
    lid = _create_location(client)
    block, _ = _create_block(client, tid, uid, identifier_ids=['TC-001'], location_id=lid)
    url = '/schedule/api/blocks/' + block['id'] + '/status'
    with app.app_context():
        def displayed():
            return enrich_blocks([schedule_block.get_by_id(block['id'])], *build_maps(), 'status')[0]
        assert displayed()['color'] == '#d97706'
    for status, color in [('in_progress', '#0d6efd'), ('completed', '#198754'), ('pending', '#d97706')]:
        assert client.put(url, json={'block_status': status}).status_code == 200
        with app.app_context():
            assert ExecutionRepository.get_by_identifier_and_task('TC-001', tid)['status'] == status
            assert ExecutionRepository.get_by_identifier_and_task('TC-002', tid) is None
            assert displayed()['block_status'] == status
            assert displayed()['color'] == color
        item = client.get('/execution/api/item/TC-001?task_id=' + tid)
        assert item.status_code == 200
        assert item.json['execution']['status'] == status
        for view in ['/schedule/?date=2026-03-10', '/schedule/week?date=2026-03-10', '/schedule/month?date=2026-03-10']:
            response = client.get(view)
            assert response.status_code == 200
            assert color in response.get_data(as_text=True)
    with app.app_context():
        ExecutionRepository.start('TC-001', tid)
        assert displayed()['block_status'] == 'in_progress'
        ex = ExecutionRepository.get_by_identifier_and_task('TC-001', tid)
        ExecutionRepository.pause(ex['id'])
        assert displayed()['block_status'] == 'in_progress'
        ExecutionRepository.complete(ex['id'], 0)
        assert displayed()['block_status'] == 'completed'


def test_empty_identifiers_do_not_imply_completed(client, app):
    uid = _create_user(client)
    tid = _create_task(client, uid)
    with app.app_context():
        task.patch(tid, identifiers=[])
    block, _ = _create_block(client, tid, uid)
    with app.app_context():
        enriched = enrich_blocks([block], *build_maps(), 'status')[0]
        assert enriched['block_status'] == 'pending'
