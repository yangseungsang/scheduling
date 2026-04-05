"""Tests for schedule/helpers/enrichment.py — enrich_blocks & get_queue_tasks."""

from tests.conftest import _create_block, _create_location, _create_task, _create_user, _create_version


class TestEnrichBlocks:
    """Verify that /schedule/api/day enriches blocks with task/user/location metadata."""

    def test_enrich_normal_block(self, client):
        uid = _create_user(client)
        loc_id = _create_location(client, name='시험실A')
        vid = _create_version(client)
        tid = _create_task(client, uid, loc_id=loc_id, version_id=vid)
        _create_block(client, tid, uid, date_str='2026-03-10',
                       start='09:00', end='10:00')

        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        data = r.get_json()
        assert len(data['blocks']) >= 1

        block = data['blocks'][0]
        assert block['section_name'] == '3.1 시스템'
        assert block['location_name'] == '시험실A'
        assert 'color' in block

    def test_enrich_split_block(self, client):
        uid = _create_user(client)
        loc_id = _create_location(client, name='시험실B')
        vid = _create_version(client)
        tid = _create_task(client, uid, loc_id=loc_id, version_id=vid)

        # Place block with only TC-001 (task has TC-001 + TC-002)
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid,
            'assignee_ids': [uid],
            'date': '2026-03-10',
            'start_time': '09:00',
            'end_time': '10:00',
            'identifier_ids': ['TC-001'],
        })
        assert r.status_code == 201

        day = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        blocks = day.get_json()['blocks']
        assert len(blocks) >= 1

        block = blocks[0]
        assert block['is_split'] is True
        assert block['block_identifier_count'] == 1


class TestQueueTasks:
    """Verify that queue_tasks in /schedule/api/day reflects task status and scheduled hours."""

    def test_queue_excludes_completed(self, app, client):
        uid = _create_user(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, version_id=vid)

        # Mark task completed via task patch (needs app context)
        from schedule.models import task as task_model
        with app.app_context():
            task_model.patch(tid, status='completed')

        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        queue = r.get_json()['queue_tasks']
        queue_ids = [q['id'] for q in queue]
        assert tid not in queue_ids

    def test_queue_hides_fully_placed(self, client):
        """Non-split block → task disappears from queue (resize = real time change)."""
        uid = _create_user(client)
        loc_id = _create_location(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, loc_id=loc_id, version_id=vid, hours='4')

        _create_block(client, tid, uid, date_str='2026-03-10',
                       start='10:00', end='11:00')

        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        queue = r.get_json()['queue_tasks']
        assert all(q['id'] != tid for q in queue)

    def test_queue_shows_split_remaining(self, client):
        """Split block → unscheduled identifiers remain in queue."""
        uid = _create_user(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, version_id=vid, hours='4')

        client.post('/schedule/api/blocks', json={
            'task_id': tid, 'assignee_ids': [uid],
            'date': '2026-03-10', 'start_time': '10:00', 'end_time': '11:00',
            'identifier_ids': ['TC-001'],
        })

        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        queue = r.get_json()['queue_tasks']
        match = [q for q in queue if q['id'] == tid]
        assert len(match) == 1
        assert match[0]['remaining_unscheduled_hours'] == 2.0
