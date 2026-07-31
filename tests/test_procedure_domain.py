"""Procedure 공통 도메인 서비스 테스트."""

from tests.conftest import _create_block, _create_location, _create_task, _create_user


def test_execution_items_join_schedule_and_execution(app, client):
    uid = _create_user(client)
    loc_id = _create_location(client, name='ProcedureLab')
    tid = _create_task(client, uid, loc_id=loc_id, hours='2')
    _create_block(
        client,
        tid,
        uid,
        date_str='2026-03-10',
        start='09:00',
        end='10:00',
        identifier_ids=['TC-001'],
    )

    with app.app_context():
        from app.domains.procedure import service as procedure_service
        from app.features.execution.models.execution import ExecutionRepository

        ex = ExecutionRepository.start('TC-001', tid, total_count=7)
        ExecutionRepository.update_performer(ex['id'], '홍길동')

        items = procedure_service.execution_items(
            date_filter='2026-03-10',
            location_filter=loc_id,
        )

    match = [item for item in items if item['identifier_id'] == 'TC-001']
    assert len(match) == 1
    assert match[0]['task_id'] == tid
    assert match[0]['scheduled_date'] == '2026-03-10'
    assert match[0]['location_name'] == 'ProcedureLab'
    assert match[0]['execution']['status'] == 'in_progress'
    assert match[0]['execution']['performer'] == '홍길동'


def test_update_identifier_elapsed_updates_task_minutes(app, client):
    uid = _create_user(client)
    tid = _create_task(client, uid, hours='2')

    with app.app_context():
        from app.domains.procedure import service as procedure_service
        from app.features.schedule.models import task as task_repo

        result = procedure_service.update_identifier_elapsed('TC-001', 125)
        updated = task_repo.get_by_id(tid)

    assert result == {'identifier_id': 'TC-001', 'estimated_minutes': 3}
    assert updated['identifiers'][0]['estimated_minutes'] == 3
    assert updated['estimated_minutes'] == 63
