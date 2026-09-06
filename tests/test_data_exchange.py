from tests.conftest import _assignee_name, _create_block, _create_procedure


def test_feature_snapshot_exposes_schedule_and_execution_data(app, client):
    assignee_name = _assignee_name(client)
    procedure_id = _create_procedure(client, assignee_name)
    block, status = _create_block(client, procedure_id, assignee_name)
    assert status == 201

    from app.features.execution.repository import ExecutionRepository

    with app.app_context():
        ExecutionRepository.start('TC-001', procedure_id, total_count=3)

    response = client.get('/features/api/snapshot')
    assert response.status_code == 200
    data = response.get_json()

    assert data['schedule']['test_procedures'][0]['id'] == procedure_id
    assert data['schedule']['schedule_blocks'][0]['id'] == block['id']
    assert data['execution']['execution_runs'][0]['test_item_id'] == 'TC-001'
