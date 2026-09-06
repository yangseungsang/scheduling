"""Tests for calendar/schedule routes."""

import zipfile
from xml.etree import ElementTree as ET
from io import BytesIO

from tests.conftest import (
    _assignee_name,
    _create_location,
    _create_procedure,
    _create_block,
)


class TestPageRoutes:
    def test_index_redirect(self, client):
        r = client.get('/')
        assert r.status_code == 302
        assert '/schedule/week' in r.headers['Location']

    def test_day_view(self, client):
        r = client.get('/schedule/')
        assert r.status_code == 200

    def test_schedule_defaults_to_readonly_mode(self, client):
        r = client.get('/schedule/')
        assert r.status_code == 200
        assert "localStorage.getItem('scheduleMode') || 'readonly'" in r.data.decode()

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

    def test_week_view_without_locations_keeps_fixed_location_headers(self, client):
        r = client.get('/schedule/week')
        assert r.status_code == 200
        html = r.data.decode()
        assert 'STE1' in html
        assert 'STE2' in html
        assert 'STE3' in html

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
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        data, status = _create_block(client, tid, uid)
        assert status == 201
        assert data['procedure_id'] == tid
        assert uid in data['assignee_names']
        assert data['start_time'] == '09:00'

    def test_create_block_missing_fields(self, client):
        r = client.post('/schedule/api/blocks', json={'procedure_id': 'xxx'})
        assert r.status_code == 400

    def test_create_block_no_body(self, client):
        r = client.post('/schedule/api/blocks', content_type='application/json')
        assert r.status_code == 400

    def test_create_block_auto_assignee(self, client):
        """If no assignee_names, use the procedure's assignee_names."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        r = client.post(
            '/schedule/api/blocks',
            json={
                'procedure_id': tid,
                'date': '2026-03-10',
                'start_time': '09:00',
                'end_time': '10:00',
                'location_name': 'STE1',
            },
        )
        assert r.status_code == 201
        assert uid in r.get_json()['assignee_names']

    def test_create_block_overlap_rejected(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        _create_block(
            client, tid, uid, start='09:00', end='10:00', location_name='STE1'
        )
        # Overlapping block at same location
        _, status = _create_block(
            client, tid, uid, start='09:30', end='10:30', location_name='STE1'
        )
        assert status == 409

    def test_create_block_adjacent_allowed(self, client):
        """Blocks that touch at endpoints should not be rejected."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        # Use times that don't span breaks to avoid end_time adjustment
        _create_block(
            client, tid, uid, start='10:00', end='11:00',
            test_item_ids=['TC-001'],
        )
        _, status = _create_block(
            client, tid, uid, start='11:00', end='11:30',
            test_item_ids=['TC-002'],
        )
        assert status == 201

    def test_create_block_break_adjustment(self, client):
        """Block spanning lunch should have end_time extended."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        data, status = _create_block(
            client,
            tid,
            uid,
            start='11:00',
            end='14:00',
        )
        assert status == 201
        # 3h work: 11:00-12:00 (1h) + skip lunch + 13:00-15:00 (2h) = end at 15:00
        assert data['end_time'] >= '15:00'

    def test_create_block_is_clamped_to_work_end(self, client):
        """An overflowing block stays on the same day and ends at work_end."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        data, status = _create_block(
            client, tid, uid, start='16:00', end='19:00',
        )
        assert status == 201
        assert data['date'] == '2026-03-10'
        assert data['end_time'] == '17:00'

    def test_create_block_at_or_after_work_end_is_rejected(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        data, status = _create_block(
            client, tid, uid, start='17:00', end='18:00',
        )
        assert status == 400
        assert '업무 종료 시간' in data['error']

    def test_update_block_move(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            json={
                'start_time': '10:00',
                'end_time': '11:00',
            },
        )
        assert r.status_code == 200
        assert r.get_json()['start_time'] == '10:00'

    def test_update_block_is_clamped_to_work_end(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            json={'start_time': '16:00', 'end_time': '19:00'},
        )
        assert r.status_code == 200
        assert r.get_json()['end_time'] == '17:00'

    def test_update_block_change_date(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            json={
                'date': '2026-03-11',
            },
        )
        assert r.status_code == 200
        assert r.get_json()['date'] == '2026-03-11'

    def test_update_block_preserves_work_duration(self, client):
        """Moving a block should preserve the actual work duration (excluding breaks)."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        # Create 1h block at 09:00-10:00
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        # Move to 11:00 -- should still be 1h of work
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            json={
                'start_time': '11:00',
                'end_time': '12:00',
            },
        )
        data = r.get_json()
        assert data['start_time'] == '11:00'
        assert data['end_time'] == '12:00'

    def test_update_block_move_across_lunch(self, client):
        """Moving a 1h block to start at 11:30 should extend past lunch."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            json={
                'start_time': '11:30',
                'end_time': '12:30',
            },
        )
        data = r.get_json()
        assert data['start_time'] == '11:30'
        # 1h work: 11:30-12:00 (30min) + skip lunch + 13:00-13:30 (30min) = 13:30
        assert data['end_time'] == '13:30'

    def test_update_block_resize_no_duration_preservation(self, client):
        """Resize should use the exact end_time, not preserve work duration."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            json={
                'start_time': '09:00',
                'end_time': '09:30',
                'resize': True,
            },
        )
        assert r.get_json()['end_time'] == '09:30'

    def test_update_block_resize_syncs_remaining(self, client):
        """On resize-shrink, remaining hours increase (no auto-split)."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        t_before = client.get(f'/procedures/api/{tid}').get_json()['procedure']
        rem_before = t_before['remaining_minutes']
        # Resize to 1h — remaining should increase
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            json={
                'start_time': '09:00',
                'end_time': '10:00',
                'resize': True,
            },
        )
        assert 'split_block' not in r.get_json()
        t = client.get(f'/procedures/api/{tid}').get_json()['procedure']
        assert t['estimated_minutes'] == 240
        assert t['remaining_minutes'] > rem_before

    def test_update_block_overlap_rejected(self, client):
        # Create two simple blocks (different procedures) at same location
        client.post(
            '/schedule/api/blocks',
            json={
                'is_simple': True,
                'date': '2026-03-10',
                'start_time': '10:00',
                'end_time': '11:00',
                'location_name': 'STE1',
                'title': 'A',
            },
        )
        r2 = client.post(
            '/schedule/api/blocks',
            json={
                'is_simple': True,
                'date': '2026-03-10',
                'start_time': '11:00',
                'end_time': '11:30',
                'location_name': 'STE1',
                'title': 'B',
            },
        )
        b2_id = r2.get_json()['id']
        # Try to move b2 to overlap with b1
        r = client.put(
            f'/schedule/api/blocks/{b2_id}',
            json={
                'start_time': '10:00',
                'end_time': '10:30',
            },
        )
        assert r.status_code == 409

    def test_update_nonexistent_block(self, client):
        r = client.put('/schedule/api/blocks/sb_nonexist', json={'date': '2026-03-10'})
        assert r.status_code == 404

    def test_update_block_no_body(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.put(
            f'/schedule/api/blocks/{block["id"]}',
            content_type='application/json',
        )
        assert r.status_code == 400

    def test_delete_block(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        block, _ = _create_block(client, tid, uid)
        r = client.delete(f'/schedule/api/blocks/{block["id"]}')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_delete_nonexistent_block(self, client):
        r = client.delete('/schedule/api/blocks/sb_nonexist')
        assert r.status_code == 404

    def test_lock_toggle(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
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
        assert 'queue_procedures' in data

    def test_api_week_data(self, client):
        r = client.get('/schedule/api/week?date=2026-03-10')
        assert r.status_code == 200
        data = r.get_json()
        assert len(data['week_days']) == 5
        assert len(data['day_names']) == 5

    def test_api_month_data(self, client):
        r = client.get('/schedule/api/month?date=2026-03-10')
        assert r.status_code == 200
        data = r.get_json()
        assert data['year'] == 2026
        assert data['month'] == 3
        assert len(data['weeks']) >= 4

    def test_api_day_data_with_blocks(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, document_id=820)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get('/schedule/api/day?date=2026-03-10')
        data = r.get_json()
        assert len(data['blocks']) == 1
        assert data['blocks'][0]['procedure_title'] == '시스템'

    def test_enriched_block_has_display_fields(self, client):
        uid = _assignee_name(client)
        lid = _create_location(client, name='시험실Z')
        tid = _create_procedure(client, uid, loc_id=lid, document_id=654)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get('/schedule/api/day?date=2026-03-10')
        block = r.get_json()['blocks'][0]
        assert block['procedure_title'] == '시스템'
        assert block['assignee_name'] == '홍길동'
        assert 'color' in block

    def test_queue_procedures_in_view_data(self, client):
        uid = _assignee_name(client)
        _create_procedure(client, uid, hours='4')
        r = client.get('/schedule/api/day')
        data = r.get_json()
        assert len(data['queue_procedures']) == 1
        assert data['queue_procedures'][0]['remaining_unscheduled_minutes'] == 240

    def test_queue_procedures_exclude_fully_scheduled(self, client):
        """TestProcedure fully covered by blocks should not appear in queue."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='1')
        _create_block(client, tid, uid, start='09:00', end='10:00')
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_procedures']
        assert all(t['id'] != tid for t in queue)

    def test_queue_hides_procedure_with_full_block(self, client):
        """TestProcedure with non-split block should NOT appear in queue (resize = real time change)."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='2')
        _create_block(client, tid, uid, start='10:00', end='11:00')
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_procedures']
        assert all(t['id'] != tid for t in queue)

    def test_queue_excludes_completed_procedures(self, app, client):
        """모든 식별자가 execution 완료된 태스크는 queue 에서 제외된다 (#108)."""
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, hours='2')

        from app.features.execution.repository import ExecutionRepository

        with app.app_context():
            ex1 = ExecutionRepository.start('TC-001', tid)
            ExecutionRepository.complete(tid, 'TC-001', fail_count=0)
            ex2 = ExecutionRepository.start('TC-002', tid)
            ExecutionRepository.complete(tid, 'TC-002', fail_count=0)

        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_procedures']
        assert all(t['id'] != tid for t in queue)


class TestOverlapLayout:
    def test_overlapping_blocks_get_columns(self, client):
        uid = _assignee_name(client)
        tid1 = _create_procedure(client, uid, document_id=986)
        uid2 = _assignee_name(client, name='김철수', color='#FF0000')
        tid2 = _create_procedure(client, uid2, document_id=771)
        # Two blocks at same time, different assignees
        _create_block(
            client, tid1, uid, date_str='2026-03-10', start='09:00', end='10:00'
        )
        _create_block(
            client, tid2, uid2, date_str='2026-03-10', start='09:00', end='10:00'
        )
        r = client.get('/schedule/api/day?date=2026-03-10')
        # API doesn't compute overlap layout, but template view does
        r = client.get('/schedule/?date=2026-03-10')
        assert r.status_code == 200

    def test_nonoverlapping_blocks_single_column(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid)
        _create_block(client, tid, uid, start='09:00', end='10:00')
        _create_block(client, tid, uid, start='10:00', end='11:00')
        r = client.get('/schedule/?date=2026-03-10')
        assert r.status_code == 200


class TestExportAPI:
    def test_export_csv(self, client):
        uid = _assignee_name(client)
        tid = _create_procedure(client, uid, document_id=681)
        _create_block(client, tid, uid, date_str='2026-03-10')
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-10&format=csv'
        )
        assert r.status_code == 200
        assert 'text/csv' in r.content_type
        body = r.data.decode('utf-8-sig')
        assert '시스템' in body  # document_name
        assert '2026-03-10' in body

    def test_export_xlsx(self, client):
        uid = _assignee_name(client)
        loc_id = 'STE1'
        tid = _create_procedure(client, uid)
        _create_block(
            client,
            tid,
            uid,
            date_str='2026-03-10',
            location_name=loc_id,
            test_item_ids=['TC-001'],
        )
        _create_block(
            client,
            tid,
            uid,
            date_str='2026-03-11',
            start='10:00',
            end='11:00',
            location_name=loc_id,
            test_item_ids=['TC-002'],
        )
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-16&format=xlsx'
        )
        assert r.status_code == 200
        assert 'spreadsheetml' in r.content_type
        assert len(r.data) > 1000  # non-trivial xlsx file
        with zipfile.ZipFile(BytesIO(r.data)) as z:
            names = set(z.namelist())
            assert 'xl/worksheets/sheet1.xml' in names
            assert 'xl/worksheets/sheet2.xml' in names
            assert 'xl/worksheets/sheet3.xml' in names
            assert 'xl/styles.xml' in names
            workbook = z.read('xl/workbook.xml').decode('utf-8')
            assert '실무자용' in workbook
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(r.data), read_only=True)
        values = list(workbook['데이터'].values)
        assert values[0] == ('날짜', '문서명')
        assert any(
            '시스템' in str(value)
            for row in values for value in row if value
        )
        practitioner_values = list(workbook['실무자용'].values)
        assert practitioner_values[0] == (
            '날짜', '장소', '시작', '종료', '절차서', '시험 항목',
        )
        flattened = [str(value) for row in practitioner_values for value in row if value]
        assert 'STE1' in flattened
        assert sum('시스템' in value for value in flattened) == 2
        assert any('TC-001' in value for value in flattened)
        assert any('TC-002' in value for value in flattened)

        with zipfile.ZipFile(BytesIO(r.data)) as z:
            schedule_sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
            styles = z.read('xl/styles.xml').decode('utf-8')
            root = ET.fromstring(schedule_sheet)
            merge_refs = {
                node.attrib['ref']
                for node in root.findall(
                    './/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}mergeCell'
                )
            }
            assert 'A1:G1' in merge_refs
            assert 'width="34"' in schedule_sheet
            assert 'EAF3F8' in styles

    def test_export_empty_range(self, client):
        r = client.get(
            '/schedule/api/export?start_date=2026-01-01&end_date=2026-01-07&format=csv'
        )
        assert r.status_code == 200

    def test_export_missing_dates(self, client):
        r = client.get('/schedule/api/export')
        assert r.status_code == 400

    def test_export_invalid_date(self, client):
        r = client.get('/schedule/api/export?start_date=bad&end_date=2026-03-10')
        assert r.status_code == 400

    def test_export_csv_has_headers(self, client):
        r = client.get(
            '/schedule/api/export?start_date=2026-03-10&end_date=2026-03-10&format=csv'
        )
        body = r.data.decode('utf-8-sig')
        assert '날짜' in body
        assert '문서명' in body
