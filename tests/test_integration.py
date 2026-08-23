"""Integration tests — full workflows spanning procedure → block → queue lifecycle."""

from tests.conftest import _create_block, _create_location, _create_procedure, _assignee_name
from app.features.schedule.services import blocks as schedule_block
from app.features.schedule.services import test_procedures as procedure_model


class TestFullWorkflow:
    """End-to-end workflows combining procedure creation, block placement, and queue updates."""

    def test_create_place_resize_restore(self, app, client):
        """Create procedure → place block → resize → verify remaining increases → delete → verify procedure back in queue."""
        uid = _assignee_name(client)
        loc_id = _create_location(client)
        tid = _create_procedure(client, uid, loc_id=loc_id, hours='4')

        # Place block 09:00-11:00
        body, status = _create_block(client, tid, uid,
                                      date_str='2026-05-01',
                                      start='09:00', end='11:00')
        assert status == 201
        block_id = body['id']

        # Resize to 09:00-10:00 (just shrinks, no split)
        r = client.put(f'/schedule/api/blocks/{block_id}', json={
            'start_time': '09:00',
            'end_time': '10:00',
            'resize': True,
        })
        assert r.status_code == 200

        # TestProcedure estimated_minutes should still be 240
        from app.features.schedule.services import test_procedures as procedure_model
        with app.app_context():
            t = procedure_model.get_by_id(tid)
            assert t['estimated_minutes'] == 240

        # Delete with restore=1
        r = client.delete(f'/schedule/api/blocks/{block_id}?restore=1')
        assert r.status_code == 200

        # TestProcedure should be back in queue
        day = client.get('/schedule/api/day?date=2026-05-01')
        queue = day.get_json()['queue_procedures']
        queue_ids = [q['id'] for q in queue]
        assert tid in queue_ids

    def test_split_and_place_separately(self, client):
        """Place TC-001 on day1 and TC-002 on day2, then verify 2 blocks via by-procedure API."""
        uid = _assignee_name(client)
        loc_id = _create_location(client)
        tid = _create_procedure(client, uid, loc_id=loc_id, hours='4')

        # Place TC-001 on 2026-05-01
        r1 = client.post('/schedule/api/blocks', json={
            'procedure_id': tid,
            'assignee_names': [uid],
            'date': '2026-05-01',
            'start_time': '09:00',
            'end_time': '10:00',
            'location_name': 'STE1',
            'test_item_ids': ['TC-001'],
        })
        assert r1.status_code == 201

        # Place TC-002 on 2026-05-02
        r2 = client.post('/schedule/api/blocks', json={
            'procedure_id': tid,
            'assignee_names': [uid],
            'date': '2026-05-02',
            'start_time': '09:00',
            'end_time': '10:00',
            'location_name': 'STE1',
            'test_item_ids': ['TC-002'],
        })
        assert r2.status_code == 201

        # Verify 2 blocks via blocks-by-procedure API
        r = client.get(f'/schedule/api/blocks/by-procedure/{tid}')
        blocks = r.get_json()['blocks']
        assert len(blocks) == 2
        dates = sorted(b['date'] for b in blocks)
        assert dates == ['2026-05-01', '2026-05-02']

    def test_test_item_move_between_blocks(self, client):
        """Place TC-001 in block1, then place TC-001+TC-002 in block2.
        Block1 should be deleted (lost all test_items), only block2 remains."""
        uid = _assignee_name(client)
        loc_id = _create_location(client)
        tid = _create_procedure(client, uid, loc_id=loc_id, hours='4')

        # Block1: TC-001 on day1
        r1 = client.post('/schedule/api/blocks', json={
            'procedure_id': tid,
            'assignee_names': [uid],
            'date': '2026-05-01',
            'start_time': '09:00',
            'end_time': '10:00',
            'location_name': 'STE1',
            'test_item_ids': ['TC-001'],
        })
        assert r1.status_code == 201
        block1_id = r1.get_json()['id']

        # Block2: TC-001 + TC-002 on day2 (TC-001 moves from block1)
        r2 = client.post('/schedule/api/blocks', json={
            'procedure_id': tid,
            'assignee_names': [uid],
            'date': '2026-05-02',
            'start_time': '09:00',
            'end_time': '11:00',
            'location_name': 'STE1',
            'test_item_ids': ['TC-001', 'TC-002'],
        })
        assert r2.status_code == 201

        # Block1 should be deleted (lost TC-001, its only test_item)
        r = client.get(f'/schedule/api/blocks/by-procedure/{tid}')
        blocks = r.get_json()['blocks']
        assert len(blocks) == 1
        assert blocks[0]['id'] != block1_id
        assert sorted(blocks[0].get('test_item_ids', [])) == ['TC-001', 'TC-002']


class TestProjectReset:
    """Project reset API tests."""

    def test_reset_clears_all_data(self, app, client):
        uid = _assignee_name(client)
        loc_id = _create_location(client)
        _create_procedure(client, uid, loc_id=loc_id, hours='2')

        r = client.post('/admin/api/project-reset')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

        with app.app_context():
            assert procedure_model.get_all() == []
            assert schedule_block.get_all() == []
