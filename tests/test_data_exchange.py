from tests.conftest import _create_block, _create_location, _create_task, _create_user


def test_feature_snapshot_exposes_schedule_and_execution_data(app, client):
    uid = _create_user(client)
    loc_id = _create_location(client)
    task_id = _create_task(client, uid, loc_id=loc_id)
    block, status = _create_block(client, task_id, uid, location_id=loc_id)
    assert status == 201

    from app.features.execution.models.execution import ExecutionRepository

    with app.app_context():
        ExecutionRepository.start('TC-001', task_id, total_count=3)

    response = client.get('/features/api/snapshot')
    assert response.status_code == 200
    data = response.get_json()

    assert data['schedule']['tasks'][0]['id'] == task_id
    assert data['schedule']['schedule_blocks'][0]['id'] == block['id']
    assert data['execution']['executions'][0]['identifier_id'] == 'TC-001'
