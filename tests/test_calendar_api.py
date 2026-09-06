"""Tests for calendar API endpoints: blocks CRUD, split, shift, simple-blocks, by-procedure."""
import json

from tests.conftest import (
    _create_block,
    _create_location,
    _create_procedure,
    _assignee_name,
)


class TestBlockCreate:
    def test_create_normal_block(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        data, status = _create_block(client, tid, uid)
        assert status == 201
        assert data['procedure_id'] == tid
        assert uid in data['assignee_names']

    def test_create_simple_block(self, client):
        r = client.post('/schedule/api/simple-blocks', json={
            'title': '회의',
            'estimated_minutes': 90,
        })
        assert r.status_code == 201
        t = r.get_json()
        assert t['document_name'] == '회의'
        # Verify the procedure was marked as simple
        procedure_r = client.get(f'/procedures/api/{t["id"]}')
        assert procedure_r.get_json()['procedure']['is_simple'] is True

    def test_create_overlap_rejected(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        _create_block(client, tid, uid, start='09:00', end='10:00', location_name='STE1')
        # Same procedure, same location, overlapping time
        _, status = _create_block(client, tid, uid, start='09:30', end='10:30', location_name='STE1')
        assert status == 409

    def test_create_rejects_unknown_location(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        data, status = _create_block(
            client, tid, uid, location_name='QA Lab A',
        )
        assert status == 400
        assert 'STE1, STE2, STE3' in data['error']

    def test_create_block_with_test_item_ids(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        payload = {
            'procedure_id': tid,
            'assignee_names': [uid],
            'date': '2026-03-10',
            'start_time': '09:00',
            'end_time': '11:00',
            'location_name': 'STE1',
            'test_item_ids': ['TC-001'],
        }
        r = client.post('/schedule/api/blocks', json=payload)
        assert r.status_code == 201
        block = r.get_json()
        assert block['test_item_ids'] == ['TC-001']


class TestBlockUpdate:
    def test_move_block_change_date(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'date': '2026-03-11',
            'start_time': '09:00',
            'end_time': '10:00',
        })
        assert r.status_code == 200
        assert r.get_json()['date'] == '2026-03-11'

    def test_resize_syncs_remaining(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        procedure_before = client.get(f'/procedures/api/{tid}').get_json()['procedure']
        rem_before = procedure_before['remaining_minutes']
        # Resize block shorter — remaining should increase (no split block)
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '09:00',
            'end_time': '10:00',
            'resize': True,
        })
        data = r.get_json()
        assert 'split_block' not in data
        procedure_after = client.get(f'/procedures/api/{tid}').get_json()['procedure']
        assert procedure_after['estimated_minutes'] == 240
        assert procedure_after['remaining_minutes'] > rem_before


class TestBlockDelete:
    def test_delete_block(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.delete(f'/schedule/api/blocks/{block["id"]}')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_restore_does_not_add_location_to_procedure(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid, location_name='STE1')
        # Delete with restore flag
        r = client.delete(f'/schedule/api/blocks/{block["id"]}?restore=1')
        assert r.status_code == 200
        procedure_data = client.get(f'/procedures/api/{tid}').get_json()['procedure']
        assert 'location_name' not in procedure_data

    def test_restore_task_deletes_all_blocks_for_task(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        first, _ = _create_block(
            client,
            tid,
            uid,
            date_str='2026-03-10',
            start='09:00',
            end='10:00',
            test_item_ids=['TC-001'],
        )
        _create_block(
            client,
            tid,
            uid,
            date_str='2026-03-11',
            start='09:00',
            end='10:00',
            test_item_ids=['TC-002'],
        )

        r = client.delete(f'/schedule/api/blocks/{first["id"]}?restore=task')
        assert r.status_code == 200
        assert r.get_json()['deleted_count'] == 2

        blocks = client.get(f'/schedule/api/blocks/by-procedure/{tid}').get_json()['blocks']
        assert blocks == []

        queue = client.get('/schedule/api/day').get_json()['queue_procedures']
        assert any(item['id'] == tid for item in queue)


class TestBlockSplit:
    def test_next_block_without_selection_uses_only_unassigned_test_items(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        first, status = _create_block(
            client, tid, uid, start='09:00', end='11:00',
            test_item_ids=['TC-001'],
        )
        assert status == 201

        second, status = _create_block(
            client, tid, uid, start='13:00', end='15:00',
        )

        assert status == 201
        assert first['test_item_ids'] == ['TC-001']
        assert second['test_item_ids'] == ['TC-002']

    def test_block_without_selection_rejects_fully_scheduled_procedure(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        _create_block(client, tid, uid, start='09:00', end='11:00')

        response = client.post('/schedule/api/blocks', json={
            'procedure_id': tid,
            'assignee_names': [uid],
            'date': '2026-03-10',
            'start_time': '13:00',
            'end_time': '15:00',
            'location_name': 'STE1',
        })

        assert response.status_code == 400
        assert '연결할 시험 항목' in response.get_json()['error']

    def test_split_keeps_selected_test_items(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        r = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={
            'keep_test_item_ids': ['TC-001'],
        })
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        # Verify block now only has TC-001
        blocks_r = client.get(f'/schedule/api/blocks/by-procedure/{tid}')
        blocks = blocks_r.get_json()['blocks']
        updated = [b for b in blocks if b['id'] == block['id']]
        assert len(updated) == 1
        assert updated[0]['test_item_ids'] == ['TC-001']

    def test_split_empty_test_items_returns_400(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        r = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={
            'keep_test_item_ids': [],
        })
        assert r.status_code == 400


class TestBlockShift:
    def test_shift_forward(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
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
        blocks = client.get(f'/schedule/api/blocks/by-procedure/{tid}').get_json()['blocks']
        assert blocks[0]['date'] == '2026-03-11'

    def test_shift_skips_weekends(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        # Friday 2026-03-13
        _create_block(client, tid, uid, date_str='2026-03-13',
                      start='09:00', end='10:00')
        r = client.post('/schedule/api/blocks/shift', json={
            'from_date': '2026-03-13',
            'direction': 1,
        })
        assert r.status_code == 200
        blocks = client.get(f'/schedule/api/blocks/by-procedure/{tid}').get_json()['blocks']
        # Friday + 1 = Saturday → skip to Monday 2026-03-16
        assert blocks[0]['date'] == '2026-03-16'


class TestBlocksByTestProcedure:
    def test_get_blocks_by_procedure_correct_count(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        _create_block(
            client, tid, uid, start='09:00', end='10:00',
            test_item_ids=['TC-001'],
        )
        _create_block(
            client, tid, uid, start='10:15', end='11:15',
            test_item_ids=['TC-002'],
        )
        r = client.get(f'/schedule/api/blocks/by-procedure/{tid}')
        assert r.status_code == 200
        assert len(r.get_json()['blocks']) == 2

    def test_split_blocks_include_sibling_and_completed_item_statuses(self, app, client):
        """분할 블록 상세 응답은 양쪽 할당과 완료 상태를 함께 제공한다 (#168)."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        original, status = _create_block(
            client, tid, uid, start='09:00', end='13:00',
        )
        assert status == 201

        split = client.post(
            f'/schedule/api/blocks/{original["id"]}/split',
            json={'keep_test_item_ids': ['TC-001']},
        )
        assert split.status_code == 200
        sibling_id = split.get_json()['new_block']['id']

        from app.features.execution.repository import ExecutionRepository
        with app.app_context():
            ExecutionRepository.start('TC-001', tid)
            ExecutionRepository.complete(tid, 'TC-001', fail_count=0)

        response = client.get(f'/schedule/api/blocks/by-procedure/{tid}')
        assert response.status_code == 200
        blocks = {block['id']: block for block in response.get_json()['blocks']}

        assert set(blocks) == {original['id'], sibling_id}
        assert blocks[original['id']]['test_item_ids'] == ['TC-001']
        assert blocks[sibling_id]['test_item_ids'] == ['TC-002']
        assert blocks[original['id']]['test_item_statuses'] == {
            'TC-001': 'completed',
        }
        assert blocks[sibling_id]['test_item_statuses'] == {
            'TC-002': 'pending',
        }
        assert blocks[original['id']]['block_status'] == 'completed'
        assert blocks[sibling_id]['block_status'] == 'pending'


def test_manual_block_status_does_not_write_procedure_status(app, client):
    """block_status 변경이 procedure.status 를 갱신하지 않아야 한다 (#108)."""
    uid = _assignee_name(client)
    tid = _create_procedure(client, uid)
    block_r = client.post('/schedule/api/blocks', json={
        'procedure_id': tid,
        'assignee_names': [uid],
        'date': '2026-03-10',
        'start_time': '09:00',
        'end_time': '10:00',
        'location_name': 'STE1',
    })
    assert block_r.status_code == 201
    block_id = block_r.get_json()['id']

    from app.features.schedule.services import test_procedures as procedure_model
    with app.app_context():
        before_status = procedure_model.get_by_id(tid).get('status')

    r = client.put(f'/schedule/api/blocks/{block_id}/status',
                   json={'block_status': 'completed'})
    assert r.status_code == 200

    with app.app_context():
        after_status = procedure_model.get_by_id(tid).get('status')

    assert after_status == before_status
