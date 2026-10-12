"""Regression coverage for weekday overflow and execution/calendar consistency."""
import pytest
from tests.conftest import _assignee_name, _create_block, _create_procedure


def blocks_for(client, procedure_id):
    return client.get(f'/schedule/api/blocks/by-procedure/{procedure_id}').get_json()['blocks']


def test_overflow_preserves_minutes_over_weekend(client):
    pid = _create_procedure(client, 'tester')
    block, status = _create_block(client, pid, 'tester', date_str='2026-03-13', start='16:30', end='19:30')
    assert status == 201
    assert block['placement_end'] == {'date': '2026-03-16', 'end_time': '10:45'}
    assert len(blocks_for(client, pid)) == 2
    assert block['continuations'][0]['test_item_ids'] == block['test_item_ids']


def test_continuation_collision_does_not_save_partial_placement(client):
    client.post('/schedule/api/blocks', json={'is_simple': True, 'title': 'occupied', 'date': '2026-03-11', 'start_time': '08:00', 'end_time': '09:00', 'location_name': 'STE1'})
    pid = _create_procedure(client, 'tester')
    _, status = _create_block(client, pid, 'tester', start='16:00', end='19:00')
    assert status == 409
    assert blocks_for(client, pid) == []


def test_move_replaces_existing_continuations_and_delete_removes_group(client):
    pid = _create_procedure(client, 'tester')
    block, _ = _create_block(client, pid, 'tester', start='16:00', end='19:00')
    result = client.put(f'/schedule/api/blocks/{block["id"]}', json={'date': '2026-03-12', 'start_time': '08:00'})
    assert result.status_code == 200
    assert result.get_json()['end_time'] == '11:15'
    assert len(blocks_for(client, pid)) == 1
    resized = client.put(f'/schedule/api/blocks/{block["id"]}', json={'start_time': '16:00', 'end_time': '19:00'}).get_json()
    continuation_id = resized['continuations'][0]['id']
    assert client.delete(f'/schedule/api/blocks/{continuation_id}').get_json()['deleted_count'] == 2
    assert blocks_for(client, pid) == []


@pytest.mark.parametrize('status,color', [('pending','#94a3b8'), ('in_progress','#0d6efd'), ('paused','#d97706'), ('completed','#198754')])
def test_calendar_and_execution_agree_for_each_state(app, client, status, color):
    from app.features.execution.repository import ExecutionRepository
    pid = _create_procedure(client, 'tester')
    block, _ = _create_block(client, pid, 'tester', start='16:00', end='18:00', test_item_ids=['TC-001'])
    with app.app_context():
        if status != 'pending':
            ExecutionRepository.start('TC-001', pid)
        if status == 'paused':
            ExecutionRepository.pause(pid, 'TC-001')
        if status == 'completed':
            ExecutionRepository.complete(pid, 'TC-001', fail_count=0)
    execution = client.get(f'/execution/api/list?procedure_id={pid}').get_json()
    item = next(row for row in execution if row['test_item_id'] == 'TC-001')
    assert item['execution_status'] == status
    for day in ('2026-03-10', '2026-03-11'):
        calendar = client.get(f'/schedule/api/day?date={day}').get_json()
        placed = next(row for row in calendar['blocks'] if row['procedure_id'] == pid)
        assert placed['block_status'] == status
        assert placed['test_item_statuses'] == {'TC-001': status}
        assert placed['color'] == color
    assert all(row['block_status'] == status for row in blocks_for(client, pid))


def test_queue_exposes_current_execution_state(app, client):
    from app.features.execution.repository import ExecutionRepository
    pid = _create_procedure(client, 'tester')
    with app.app_context():
        ExecutionRepository.start('TC-001', pid)
        ExecutionRepository.pause(pid, 'TC-001')
    queued = next(row for row in client.get('/schedule/api/day').get_json()['queue_procedures'] if row['id'] == pid)
    assert queued['block_status'] == 'paused'
    assert queued['color'] == '#d97706'
    assert queued['test_items'][0]['execution_status'] == 'paused'


def test_split_at_work_end_preserves_both_item_durations(client):
    pid = _create_procedure(client, 'tester', hours='4')
    block, _ = _create_block(client, pid, 'tester', start='15:30', end='19:30')
    result = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={'keep_test_item_ids': ['TC-001']})
    assert result.status_code == 200
    assert result.get_json()['new_block']['date'] == '2026-03-11'
    assert result.get_json()['new_block']['start_time'] == '08:30'
    assert result.get_json()['new_block']['end_time'] == '10:45'


def test_old_manual_status_cannot_hide_actual_execution(app, client):
    from app.features.execution.repository import ExecutionRepository
    pid = _create_procedure(client, 'tester')
    block, _ = _create_block(client, pid, 'tester', test_item_ids=['TC-001'], block_status='cancelled')
    with app.app_context():
        ExecutionRepository.start('TC-001', pid)
        ExecutionRepository.complete(pid, 'TC-001', fail_count=0)
    assert blocks_for(client, pid)[0]['block_status'] == 'completed'


def test_update_collision_keeps_entire_previous_placement(client):
    client.post('/schedule/api/blocks', json={'is_simple': True, 'title': 'occupied', 'date': '2026-03-12', 'start_time': '08:00', 'end_time': '09:00', 'location_name': 'STE1'})
    pid = _create_procedure(client, 'tester')
    block, _ = _create_block(client, pid, 'tester', start='16:00', end='19:00')
    before = blocks_for(client, pid)
    result = client.put(f'/schedule/api/blocks/{block["id"]}', json={'date': '2026-03-11'})
    assert result.status_code == 409
    assert blocks_for(client, pid) == before


def test_preview_overflow_reports_weekday_without_saving(client):
    pid = _create_procedure(client, 'tester')
    result = client.post('/schedule/api/blocks/preview', json={
        'action': 'create', 'data': {'procedure_id': pid, 'date': '2026-03-13',
        'start_time': '16:30', 'end_time': '19:30', 'location_name': 'STE1'},
    })
    assert result.status_code == 200
    assert result.get_json() == {'requires_confirmation': True, 'segments': [
        {'date': '2026-03-16', 'start_time': '08:00', 'end_time': '10:45'},
    ]}
    assert blocks_for(client, pid) == []


def test_preview_move_and_split_keep_original_schedule(client):
    pid = _create_procedure(client, 'tester', hours='4')
    block, _ = _create_block(client, pid, 'tester', start='09:00', end='13:00')
    before = blocks_for(client, pid)
    moved = client.post('/schedule/api/blocks/preview', json={
        'action': 'update', 'block_id': block['id'],
        'data': {'start_time': '16:00', 'end_time': '20:00'},
    })
    assert moved.status_code == 200
    assert moved.get_json()['requires_confirmation'] is True
    assert blocks_for(client, pid) == before
    split = client.post('/schedule/api/blocks/preview', json={
        'action': 'split', 'block_id': block['id'], 'data': {'keep_test_item_ids': ['TC-001']},
    })
    assert split.status_code == 200
    assert split.get_json()['requires_confirmation'] is False
    assert blocks_for(client, pid) == before


def test_preview_inside_workday_needs_no_confirmation(client):
    pid = _create_procedure(client, 'tester')
    result = client.post('/schedule/api/blocks/preview', json={
        'action': 'create', 'data': {'procedure_id': pid, 'date': '2026-03-13',
        'start_time': '16:00', 'end_time': '17:00', 'location_name': 'STE1'},
    })
    assert result.get_json() == {'requires_confirmation': False, 'segments': []}
    assert blocks_for(client, pid) == []


def test_preview_split_reports_next_day_without_modifying_groups(client):
    pid = _create_procedure(client, 'tester', hours='4')
    block, _ = _create_block(client, pid, 'tester', start='15:30', end='19:30')
    before = blocks_for(client, pid)
    result = client.post('/schedule/api/blocks/preview', json={
        'action': 'split', 'block_id': block['id'], 'data': {'keep_test_item_ids': ['TC-001']},
    })
    assert result.status_code == 200
    assert result.get_json()['requires_confirmation'] is True
    assert blocks_for(client, pid) == before
