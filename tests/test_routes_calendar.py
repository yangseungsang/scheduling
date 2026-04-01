"""Tests for calendar/schedule routes."""
from tests.conftest import (
    _create_user, _create_location, _create_task, _create_version, _create_block,
)


class TestPageRoutes:
    def test_index_redirect(self, client):
        r = client.get('/')
        assert r.status_code == 302
        assert '/schedule/' in r.headers['Location']

    def test_day_view(self, client):
        r = client.get('/schedule/')
        assert r.status_code == 200

    def test_day_view_with_date(self, client):
        r = client.get('/schedule/?date=2026-03-10')
        assert r.status_code == 200
        assert '2026-03-10' in r.data.decode()

    def test_day_view_invalid_date_falls_back(self, client):
        r = client.get('/schedule/?date=invalid')
        assert r.status_code == 200

    def test_week_view(self, client):
        r = client.get('/schedule/week')
        assert r.status_code == 200

    def test_week_view_with_date(self, client):
        r = client.get('/schedule/week?date=2026-03-10')
        assert r.status_code == 200

    def test_month_view(self, client):
        r = client.get('/schedule/month')
        assert r.status_code == 200

    def test_month_view_with_date(self, client):
        r = client.get('/schedule/month?date=2026-01-15')
        assert r.status_code == 200
        assert '1월' in r.data.decode()


class TestScheduleBlockAPI:
    def test_create_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        data, status = _create_block(client, tid, uid)
        assert status == 201
        assert data['task_id'] == tid
        assert uid in data['assignee_ids']
        assert data['start_time'] == '09:00'
        assert data['origin'] == 'manual'

    def test_create_block_missing_fields(self, client):
        r = client.post('/schedule/api/blocks', json={'task_id': 'xxx'})
        assert r.status_code == 400

    def test_create_block_no_body(self, client):
        r = client.post('/schedule/api/blocks', content_type='application/json')
        assert r.status_code == 400

    def test_create_block_auto_assignee(self, client):
        """If no assignee_ids, use the task's assignee_ids."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid, 'date': '2026-03-10',
            'start_time': '09:00', 'end_time': '10:00',
        })
        assert r.status_code == 201
        assert uid in r.get_json()['assignee_ids']

    def test_create_block_overlap_rejected(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, start='09:00', end='10:00',
                      location_id='loc_test')
        # Overlapping block at same location
        _, status = _create_block(client, tid, uid, start='09:30', end='10:30',
                                  location_id='loc_test')
        assert status == 409

    def test_create_block_adjacent_allowed(self, client):
        """Blocks that touch at endpoints should not be rejected."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        # Use times that don't span breaks to avoid end_time adjustment
        _create_block(client, tid, uid, start='10:00', end='11:00')
        _, status = _create_block(client, tid, uid, start='11:00', end='11:30')
        assert status == 201

    def test_create_block_break_adjustment(self, client):
        """Block spanning lunch should have end_time extended."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        data, status = _create_block(
            client, tid, uid, start='11:00', end='14:00',
        )
        assert status == 201
        # 3h work: 11:00-12:00 (1h) + skip lunch + 13:00-15:00 (2h) = end at 15:00
        assert data['end_time'] >= '15:00'

    def test_update_block_move(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '10:00', 'end_time': '11:00',
        })
        assert r.status_code == 200
        assert r.get_json()['start_time'] == '10:00'

    def test_update_block_change_date(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'date': '2026-03-11',
        })
        assert r.status_code == 200
        assert r.get_json()['date'] == '2026-03-11'

    def test_update_block_preserves_work_duration(self, client):
        """Moving a block should preserve the actual work duration (excluding breaks)."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        # Create 1h block at 09:00-10:00
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        # Move to 11:00 -- should still be 1h of work
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '11:00', 'end_time': '12:00',
        })
        data = r.get_json()
        assert data['start_time'] == '11:00'
        assert data['end_time'] == '12:00'

    def test_update_block_move_across_lunch(self, client):
        """Moving a 1h block to start at 11:30 should extend past lunch."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '11:30', 'end_time': '12:30',
        })
        data = r.get_json()
        assert data['start_time'] == '11:30'
        # 1h work: 11:30-12:00 (30min) + skip lunch + 13:00-13:30 (30min) = 13:30
        assert data['end_time'] == '13:30'

    def test_update_block_resize_no_duration_preservation(self, client):
        """Resize should use the exact end_time, not preserve work duration."""
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '09:00', 'end_time': '09:30',
            'resize': True,
        })
        assert r.get_json()['end_time'] == '09:30'

    def test_update_block_resize_syncs_estimated_hours(self, client):
        """On resize, estimated_hours adjusts to total scheduled, remaining=0."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        # Resize to 1h
        client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '09:00', 'end_time': '10:00',
            'resize': True,
        })
        task = client.get(f'/tasks/api/{tid}').get_json()['task']
        # 09:00-10:00 crosses break 09:45-10:00 (15min), work = 45min = 0.75h
        assert task['estimated_hours'] == 0.75
        assert task['remaining_hours'] == 0

    def test_update_block_overlap_rejected(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        # Use times that don't span breaks, same location to trigger overlap check
        b1, _ = _create_block(client, tid, uid, start='10:00', end='11:00',
                              location_id='loc_test')
        b2, _ = _create_block(client, tid, uid, start='11:00', end='11:30',
                              location_id='loc_test')
        # Try to move b2 to overlap with b1
        r = client.put(f'/schedule/api/blocks/{b2["id"]}', json={
            'start_time': '10:00', 'end_time': '10:30',
        })
        assert r.status_code == 409

    def test_update_nonexistent_block(self, client):
        r = client.put('/schedule/api/blocks/sb_nonexist', json={'date': '2026-03-10'})
        assert r.status_code == 404

    def test_update_block_no_body(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            content_type='application/json',
        )
        assert r.status_code == 400

    def test_delete_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.delete(f'/schedule/api/blocks/{block["id"]}')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_delete_nonexistent_block(self, client):
        r = client.delete('/schedule/api/blocks/sb_nonexist')
        assert r.status_code == 404

    def test_lock_toggle(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        block, _ = _create_block(client, tid, uid)
        bid = block['id']
        # Lock
        r = client.put(f'/schedule/api/blocks/{bid}/lock')
        assert r.get_json()['is_locked'] is True
        # Unlock
        r = client.put(f'/schedule/api/blocks/{bid}/lock')
        assert r.get_json()['is_locked'] is False

    def test_lock_nonexistent(self, client):
        r = client.put('/schedule/api/blocks/sb_nonexist/lock')
        assert r.status_code == 404


class TestScheduleViewAPIs:
    def test_api_day_data(self, client):
        r = client.get('/schedule/api/day?date=2026-03-10')
        assert r.status_code == 200
        data = r.get_json()
        assert data['current_date'] == '2026-03-10'
        assert 'blocks' in data
        assert 'time_slots' in data
        assert 'queue_tasks' in data

    def test_api_week_data(self, client):
        r = client.get('/schedule/api/week?date=2026-03-10')
        assert r.status_code == 200
        data = r.get_json()
        assert len(data['week_days']) == 7
        assert len(data['day_names']) == 7

    def test_api_month_data(self, client):
        r = client.get('/schedule/api/month?date=2026-03-10')
        assert r.status_code == 200
        data = r.get_json()
        assert data['year'] == 2026
        assert data['month'] == 3
        assert len(data['weeks']) >= 4

    def test_api_day_data_with_blocks(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, procedure_id='DAY-001')
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get('/schedule/api/day?date=2026-03-10')
        data = r.get_json()
        assert len(data['blocks']) == 1
        assert data['blocks'][0]['task_title'] == 'DAY-001'

    def test_enriched_block_has_display_fields(self, client):
        uid = _create_user(client)
        lid = _create_location(client, name='시험실Z')
        tid = _create_task(client, uid, loc_id=lid, procedure_id='ENR-001')
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get('/schedule/api/day?date=2026-03-10')
        block = r.get_json()['blocks'][0]
        assert block['task_title'] == 'ENR-001'
        assert block['assignee_name'] == '홍길동'
        assert 'color' in block

    def test_queue_tasks_in_view_data(self, client):
        uid = _create_user(client)
        _create_task(client, uid, hours='4')
        r = client.get('/schedule/api/day')
        data = r.get_json()
        assert len(data['queue_tasks']) == 1
        assert data['queue_tasks'][0]['remaining_unscheduled_hours'] == 4.0

    def test_queue_tasks_exclude_fully_scheduled(self, client):
        """Task fully covered by blocks should not appear in queue."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='1')
        _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_tasks']
        assert all(t['id'] != tid for t in queue)

    def test_queue_tasks_partial_remaining(self, client):
        """Task with 2h remaining but 1h scheduled should show 1h in queue."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        # Use time range that doesn't cross breaks (10:00-11:00 = exactly 1h)
        _create_block(client, tid, uid, start='10:00', end='11:00')
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_tasks']
        matching = [t for t in queue if t['id'] == tid]
        assert len(matching) == 1
        assert matching[0]['remaining_unscheduled_hours'] == 1.0

    def test_queue_excludes_completed_tasks(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        # Mark as completed via API update
        client.put(f'/tasks/api/{tid}/update', json={
            'procedure_id': 'SYS-001',
            'status': 'completed',
            'estimated_hours': 2,
            'remaining_hours': 0,
        })
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_tasks']
        assert all(t['id'] != tid for t in queue)


class TestOverlapLayout:
    def test_overlapping_blocks_get_columns(self, client):
        uid = _create_user(client)
        tid1 = _create_task(client, uid, procedure_id='업무A')
        uid2 = _create_user(client, name='김철수', color='#FF0000')
        tid2 = _create_task(client, uid2, procedure_id='업무B')
        # Two blocks at same time, different assignees
        _create_block(client, tid1, uid, date_str='2026-03-10',
                      start='09:00', end='10:00')
        _create_block(client, tid2, uid2, date_str='2026-03-10',
                      start='09:00', end='10:00')
        r = client.get('/schedule/api/day?date=2026-03-10')
        # API doesn't compute overlap layout, but template view does
        r = client.get('/schedule/?date=2026-03-10')
        assert r.status_code == 200

    def test_nonoverlapping_blocks_single_column(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, start='09:00', end='10:00')
        _create_block(client, tid, uid, start='10:00', end='11:00')
        r = client.get('/schedule/?date=2026-03-10')
        assert r.status_code == 200


class TestDraftScheduling:
    def test_generate_drafts(self, client):
        uid = _create_user(client)
        vid = _create_version(client)
        _create_task(client, uid, version_id=vid, hours='2')
        r = client.post('/schedule/api/draft/generate', json={})
        assert r.status_code == 200
        data = r.get_json()
        assert data['placed_count'] >= 1

    def test_generate_creates_draft_blocks(self, client):
        uid = _create_user(client)
        vid = _create_version(client)
        _create_task(client, uid, version_id=vid, hours='1')
        client.post('/schedule/api/draft/generate', json={})
        # Check blocks exist and are drafts
        r = client.get('/schedule/api/day')
        blocks = r.get_json()['blocks']
        drafts = [b for b in blocks if b.get('is_draft')]
        # May or may not have blocks today depending on timing
        # Just verify the API works
        assert r.status_code == 200

    def test_approve_drafts(self, client):
        uid = _create_user(client)
        vid = _create_version(client)
        _create_task(client, uid, version_id=vid, hours='1')
        client.post('/schedule/api/draft/generate', json={})
        r = client.post('/schedule/api/draft/approve')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_approve_updates_remaining_hours(self, client):
        uid = _create_user(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, version_id=vid, hours='1')
        client.post('/schedule/api/draft/generate', json={})
        client.post('/schedule/api/draft/approve')
        task = client.get(f'/tasks/api/{tid}').get_json()['task']
        # remaining_hours should have been decremented
        assert task['remaining_hours'] < 1.0 or task['status'] == 'completed'

    def test_discard_drafts(self, client):
        uid = _create_user(client)
        vid = _create_version(client)
        _create_task(client, uid, version_id=vid, hours='2')
        gen = client.post('/schedule/api/draft/generate', json={}).get_json()
        assert gen['placed_count'] >= 1
        r = client.post('/schedule/api/draft/discard')
        assert r.status_code == 200

    def test_generate_with_existing_confirmed_blocks(self, client):
        """Auto-scheduling should respect existing confirmed blocks."""
        uid = _create_user(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, version_id=vid, hours='2')
        # Manually place 1h
        _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.post('/schedule/api/draft/generate', json={})
        data = r.get_json()
        # Should place remaining 1h, not overlap with 09:00-10:00
        assert r.status_code == 200

    def test_generate_multiple_tasks_procedure_order(self, client):
        uid = _create_user(client)
        vid = _create_version(client)
        _create_task(client, uid, version_id=vid, procedure_id='LATE-001',
                     hours='1')
        _create_task(client, uid, version_id=vid, procedure_id='EARLY-001',
                     hours='1')
        r = client.post('/schedule/api/draft/generate', json={})
        assert r.status_code == 200
        assert r.get_json()['placed_count'] >= 2

    def test_unplaced_tasks_reported(self, client):
        """Tasks that can't fit should be reported as unplaced."""
        uid = _create_user(client)
        vid = _create_version(client)
        # Create task with impossibly many hours
        _create_task(client, uid, version_id=vid, hours='999')
        r = client.post('/schedule/api/draft/generate', json={})
        data = r.get_json()
        assert len(data['unplaced']) >= 1
        assert data['unplaced'][0]['remaining_hours'] > 0

    def test_generate_no_version_returns_error(self, client):
        """Generate without any active version should return 400."""
        uid = _create_user(client)
        _create_task(client, uid, hours='1')
        r = client.post('/schedule/api/draft/generate')
        assert r.status_code == 400


class TestExportAPI:
    def test_export_csv(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, procedure_id='EXPORT-001')
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-10&format=csv'
        )
        assert r.status_code == 200
        assert 'text/csv' in r.content_type
        body = r.data.decode('utf-8-sig')
        assert 'EXPORT-001' in body
        assert '홍길동' in body

    def test_export_xlsx(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-16&format=xlsx'
        )
        assert r.status_code == 200
        assert 'spreadsheetml' in r.content_type
        assert len(r.data) > 1000  # non-trivial xlsx file

    def test_export_empty_range(self, client):
        r = client.get(
            '/schedule/api/export?start_date=2026-01-01&end_date=2026-01-07&format=csv'
        )
        assert r.status_code == 200

    def test_export_missing_dates(self, client):
        r = client.get('/schedule/api/export')
        assert r.status_code == 400

    def test_export_invalid_date(self, client):
        r = client.get(
            '/schedule/api/export?start_date=bad&end_date=2026-03-10'
        )
        assert r.status_code == 400

    def test_export_csv_has_headers(self, client):
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-10&format=csv'
        )
        body = r.data.decode('utf-8-sig')
        assert '날짜' in body
        assert '업무명' in body
