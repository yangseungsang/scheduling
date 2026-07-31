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
        assert block['doc_name'] == '시스템'
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
            'assignee_names': [uid],
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

    def test_enrich_status_derived_from_execution(self, app, client):
        """블록 상태(block_status)가 execution 데이터에 의해 동적으로 결정되는지 검증 (#108)."""
        uid = _create_user(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, version_id=vid)

        # 블록 생성 (TC-001만 포함)
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid,
            'assignee_names': [uid],
            'date': '2026-03-10',
            'start_time': '09:00',
            'end_time': '10:00',
            'identifier_ids': ['TC-001'],
            'block_status': 'pending'
        })
        bid = r.get_json()['id']

        # TC-001 을 진행 중으로 설정
        from app.features.execution.models.execution import ExecutionRepository
        with app.app_context():
            ExecutionRepository.start('TC-001', tid)

        # 캘린더 조회 시 블록 상태가 in_progress 여야 함
        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        block = next(b for b in r.get_json()['blocks'] if b['id'] == bid)
        assert block['block_status'] == 'in_progress'
        # 색상도 in_progress (#0d6efd) 여야 함
        assert block['color'] == '#0d6efd'

        # TC-001 을 완료로 설정
        with app.app_context():
            ex = ExecutionRepository.get_by_identifier_and_task('TC-001', tid)
            ExecutionRepository.complete(ex['id'], fail_count=0)

        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        block = next(b for b in r.get_json()['blocks'] if b['id'] == bid)
        assert block['block_status'] == 'completed'
        assert block['color'] == '#198754'


class TestQueueTasks:
    """Verify that queue_tasks in /schedule/api/day reflects task status and scheduled hours."""

    def test_queue_excludes_completed(self, app, client):
        """모든 식별자가 execution 완료된 태스크는 queue 에서 제외된다 (#108)."""
        uid = _create_user(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, version_id=vid)

        from app.features.execution.models.execution import ExecutionRepository
        with app.app_context():
            ex1 = ExecutionRepository.start('TC-001', tid)
            ExecutionRepository.complete(ex1['id'], fail_count=0)
            ex2 = ExecutionRepository.start('TC-002', tid)
            ExecutionRepository.complete(ex2['id'], fail_count=0)

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
            'task_id': tid, 'assignee_names': [uid],
            'date': '2026-03-10', 'start_time': '10:00', 'end_time': '11:00',
            'identifier_ids': ['TC-001'],
        })

        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        queue = r.get_json()['queue_tasks']
        match = [q for q in queue if q['id'] == tid]
        assert len(match) == 1
        assert match[0]['remaining_unscheduled_minutes'] == 120

    def test_queue_shows_identifier_added_after_full_block_is_frozen(self, app, client):
        """동기화로 새 식별자가 추가되면 기존 전체 블록에 자동 포함되지 않고 큐에 남아야 한다."""
        uid = _create_user(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, version_id=vid, hours='2')
        _create_block(client, tid, uid, start='10:00', end='11:00')

        from app.features.schedule.models import task as task_model
        from app.features.schedule.models import schedule_block

        with app.app_context():
            task_model.patch(
                tid,
                identifiers=[
                    {'id': 'TC-001', 'estimated_minutes': 60, 'owners': []},
                    {'id': 'TC-002', 'estimated_minutes': 60, 'owners': []},
                    {'id': 'TC-003', 'estimated_minutes': 30, 'owners': []},
                ],
                estimated_minutes=150,
                remaining_minutes=30,
            )
            block = schedule_block.get_all()[0]
            schedule_block.update(block['id'], identifier_ids=['TC-001', 'TC-002'])

        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        match = [q for q in r.get_json()['queue_tasks'] if q['id'] == tid]
        assert len(match) == 1
        assert match[0]['remaining_unscheduled_minutes'] == 30

    def test_queue_uses_execution_status_not_task_status(self, app, client):
        """Queue 필터는 task.status 필드가 아닌 execution 상태 기반이어야 한다 (#108)."""
        uid = _create_user(client)
        vid = _create_version(client)
        tid = _create_task(client, uid, version_id=vid)

        # task.status 를 명시적으로 'waiting' 으로 설정하여 구 방식이 큐에 남기는지 검증
        from app.features.schedule.models import task as task_model
        with app.app_context():
            task_model.patch(tid, status='waiting')

        # 모든 식별자 execution 을 completed 로 만든다
        from app.features.execution.models.execution import ExecutionRepository
        with app.app_context():
            ex1 = ExecutionRepository.start('TC-001', tid)
            ExecutionRepository.complete(ex1['id'], fail_count=0)
            ex2 = ExecutionRepository.start('TC-002', tid)
            ExecutionRepository.complete(ex2['id'], fail_count=0)

        r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
        queue = r.get_json()['queue_tasks']
        queue_ids = [q['id'] for q in queue]
        # task.status 가 'waiting' 이어도 execution 기준 완료 → queue 에 없어야 함
        assert tid not in queue_ids
