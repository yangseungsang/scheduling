"""Integration tests — full workflows spanning task → block → queue lifecycle."""

from tests.conftest import _create_block, _create_location, _create_task, _create_user, _create_version


class TestFullWorkflow:
    """End-to-end workflows combining task creation, block placement, and queue updates."""

    def test_create_place_resize_restore(self, app, client):
        """Create task → place block → resize → verify remaining increases → delete → verify task back in queue."""
        uid = _create_user(client)
        loc_id = _create_location(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, loc_id=loc_id, version_id=vid, hours='4')

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

        # Task estimated_minutes should still be 240
        from schedule.models import task as task_model
        with app.app_context():
            t = task_model.get_by_id(tid)
            assert t['estimated_minutes'] == 240

        # Delete with restore=1
        r = client.delete(f'/schedule/api/blocks/{block_id}?restore=1')
        assert r.status_code == 200

        # Task should be back in queue
        day = client.get(f'/schedule/api/day?date=2026-05-01&version={vid}')
        queue = day.get_json()['queue_tasks']
        queue_ids = [q['id'] for q in queue]
        assert tid in queue_ids

    def test_split_and_place_separately(self, client):
        """Place TC-001 on day1 and TC-002 on day2, then verify 2 blocks via by-task API."""
        uid = _create_user(client)
        loc_id = _create_location(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, loc_id=loc_id, version_id=vid, hours='4')

        # Place TC-001 on 2026-05-01
        r1 = client.post('/schedule/api/blocks', json={
            'task_id': tid,
            'assignee_ids': [uid],
            'date': '2026-05-01',
            'start_time': '09:00',
            'end_time': '10:00',
            'identifier_ids': ['TC-001'],
        })
        assert r1.status_code == 201

        # Place TC-002 on 2026-05-02
        r2 = client.post('/schedule/api/blocks', json={
            'task_id': tid,
            'assignee_ids': [uid],
            'date': '2026-05-02',
            'start_time': '09:00',
            'end_time': '10:00',
            'identifier_ids': ['TC-002'],
        })
        assert r2.status_code == 201

        # Verify 2 blocks via blocks-by-task API
        r = client.get(f'/schedule/api/blocks/by-task/{tid}')
        blocks = r.get_json()['blocks']
        assert len(blocks) == 2
        dates = sorted(b['date'] for b in blocks)
        assert dates == ['2026-05-01', '2026-05-02']

    def test_identifier_move_between_blocks(self, client):
        """Place TC-001 in block1, then place TC-001+TC-002 in block2.
        Block1 should be deleted (lost all identifiers), only block2 remains."""
        uid = _create_user(client)
        loc_id = _create_location(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, loc_id=loc_id, version_id=vid, hours='4')

        # Block1: TC-001 on day1
        r1 = client.post('/schedule/api/blocks', json={
            'task_id': tid,
            'assignee_ids': [uid],
            'date': '2026-05-01',
            'start_time': '09:00',
            'end_time': '10:00',
            'identifier_ids': ['TC-001'],
        })
        assert r1.status_code == 201
        block1_id = r1.get_json()['id']

        # Block2: TC-001 + TC-002 on day2 (TC-001 moves from block1)
        r2 = client.post('/schedule/api/blocks', json={
            'task_id': tid,
            'assignee_ids': [uid],
            'date': '2026-05-02',
            'start_time': '09:00',
            'end_time': '11:00',
            'identifier_ids': ['TC-001', 'TC-002'],
        })
        assert r2.status_code == 201

        # Block1 should be deleted (lost TC-001, its only identifier)
        r = client.get(f'/schedule/api/blocks/by-task/{tid}')
        blocks = r.get_json()['blocks']
        assert len(blocks) == 1
        assert blocks[0]['id'] != block1_id
        assert sorted(blocks[0].get('identifier_ids', [])) == ['TC-001', 'TC-002']
