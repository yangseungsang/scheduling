"""Tests for calendar API endpoints: blocks CRUD, split, shift, simple-blocks, by-task."""
import json

from tests.conftest import (
    _create_block,
    _create_location,
    _create_task,
    _create_user,
    _create_version,
)


class TestBlockCreate:
    def test_create_normal_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        data, status = _create_block(client, tid, uid)
        assert status == 201
        assert data['task_id'] == tid
        assert uid in data['assignee_ids']

    def test_create_simple_block(self, client):
        r = client.post('/schedule/api/simple-blocks', json={
            'title': '회의',
            'estimated_minutes': 90,
        })
        assert r.status_code == 201
        t = r.get_json()
        assert t['section_name'] == '회의'
        # Verify the task was marked as simple
        task_r = client.get(f'/tasks/api/{t["id"]}')
        assert task_r.get_json()['task']['is_simple'] is True

    def test_create_overlap_rejected(self, client):
        uid = _create_user(client)
        lid = _create_location(client, name='Lab1')
        tid = _create_task(client, uid, loc_id=lid)
        _create_block(client, tid, uid, start='09:00', end='10:00')
        # Same task, same location, overlapping time
        _, status = _create_block(client, tid, uid, start='09:30', end='10:30')
        assert status == 409

    def test_create_block_with_identifier_ids(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        payload = {
            'task_id': tid,
            'assignee_ids': [uid],
            'date': '2026-03-10',
            'start_time': '09:00',
            'end_time': '11:00',
            'identifier_ids': ['TC-001'],
        }
        r = client.post('/schedule/api/blocks', json=payload)
        assert r.status_code == 201
        block = r.get_json()
        assert block['identifier_ids'] == ['TC-001']


class TestBlockUpdate:
    def test_move_block_change_date(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'date': '2026-03-11',
            'start_time': '09:00',
            'end_time': '10:00',
        })
        assert r.status_code == 200
        assert r.get_json()['date'] == '2026-03-11'

    def test_resize_syncs_remaining(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        task_before = client.get(f'/tasks/api/{tid}').get_json()['task']
        rem_before = task_before['remaining_minutes']
        # Resize block shorter — remaining should increase (no split block)
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '09:00',
            'end_time': '10:00',
            'resize': True,
        })
        data = r.get_json()
        assert 'split_block' not in data
        task_after = client.get(f'/tasks/api/{tid}').get_json()['task']
        assert task_after['estimated_minutes'] == 240
        assert task_after['remaining_minutes'] > rem_before


class TestBlockDelete:
    def test_delete_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.delete(f'/schedule/api/blocks/{block["id"]}')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_restore_clears_location_id(self, client):
        uid = _create_user(client)
        lid = _create_location(client, name='RestoreLab')
        tid = _create_task(client, uid, loc_id=lid)
        block, _ = _create_block(client, tid, uid)
        # Delete with restore flag
        r = client.delete(f'/schedule/api/blocks/{block["id"]}?restore=1')
        assert r.status_code == 200
        # Task's location_id should be cleared
        task_data = client.get(f'/tasks/api/{tid}').get_json()['task']
        assert task_data['location_id'] == ''


class TestBlockSplit:
    def test_split_keeps_selected_identifiers(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        r = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={
            'keep_identifier_ids': ['TC-001'],
        })
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        # Verify block now only has TC-001
        blocks_r = client.get(f'/schedule/api/blocks/by-task/{tid}')
        blocks = blocks_r.get_json()['blocks']
        updated = [b for b in blocks if b['id'] == block['id']]
        assert len(updated) == 1
        assert updated[0]['identifier_ids'] == ['TC-001']

    def test_split_empty_identifiers_returns_400(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        r = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={
            'keep_identifier_ids': [],
        })
        assert r.status_code == 400


class TestBlockShift:
    def test_shift_forward(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        # Tuesday 2026-03-10
        _create_block(client, tid, uid, date_str='2026-03-10',
                      start='09:00', end='10:00')
        r = client.post('/schedule/api/blocks/shift', json={
            'from_date': '2026-03-10',
            'direction': 1,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert data['shifted_count'] == 1
        # Verify block moved to Wednesday 2026-03-11
        blocks = client.get(f'/schedule/api/blocks/by-task/{tid}').get_json()['blocks']
        assert blocks[0]['date'] == '2026-03-11'

    def test_shift_skips_weekends(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        # Friday 2026-03-13
        _create_block(client, tid, uid, date_str='2026-03-13',
                      start='09:00', end='10:00')
        r = client.post('/schedule/api/blocks/shift', json={
            'from_date': '2026-03-13',
            'direction': 1,
        })
        assert r.status_code == 200
        blocks = client.get(f'/schedule/api/blocks/by-task/{tid}').get_json()['blocks']
        # Friday + 1 = Saturday → skip to Monday 2026-03-16
        assert blocks[0]['date'] == '2026-03-16'


class TestBlocksByTask:
    def test_get_blocks_by_task_correct_count(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        _create_block(client, tid, uid, start='09:00', end='10:00')
        _create_block(client, tid, uid, start='10:00', end='11:00')
        r = client.get(f'/schedule/api/blocks/by-task/{tid}')
        assert r.status_code == 200
        assert len(r.get_json()['blocks']) == 2
