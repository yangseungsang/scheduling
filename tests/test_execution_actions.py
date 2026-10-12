"""Public action updates persist through the execution storage adapter."""

from pathlib import Path

import pytest
from flask import Flask

from app.features.execution.domain import ExecutionRun, Executions
from app.features.execution.repository import ExecutionRepository
from app.repositories import JsonDomainRepository, get_repository, init_repository


@pytest.mark.parametrize('field,value', [
    ('action_status', 'running'),
    ('action_input', {'command': 'start', 'enabled': False}),
    ('action_status', ''),
    ('action_input', {}),
    ('action_input', 0),
    ('action_input', False),
    ('action_input', None),
])
def test_public_action_update_persists_only_the_selected_run(app, field, value):
    with app.app_context():
        repository = get_repository()
        runs = (
            ExecutionRun('p1', 'TC-1', action_status='old', action_input={'old': True}),
            ExecutionRun('p2', 'TC-1'),
            ExecutionRun('p1', 'TC-2'),
        )
        repository.replace_executions(Executions(runs=runs))
        result = getattr(repository, f'update_{field}')(runs[0].id, value)
        assert result.get(field) == value
        # Another execution mutation must not discard the action fields.
        ExecutionRepository.update_comment('p1', 'TC-1', 'updated')
        reloaded = JsonDomainRepository(repository.data_dir).load_executions().runs
        assert getattr(reloaded[0], field) == value
        other_field = 'action_input' if field == 'action_status' else 'action_status'
        assert getattr(reloaded[0], other_field) == getattr(runs[0], other_field)
        assert reloaded[0].comment == 'updated'
        assert reloaded[1:] == runs[1:]


@pytest.mark.parametrize('field', ['action_status', 'action_input'])
def test_public_action_update_returns_none_for_missing_run(app, field):
    with app.app_context():
        repository = get_repository()
        repository.replace_executions(Executions(runs=(ExecutionRun('p1', 'TC-1'),)))
        before = repository.load_executions()
        assert getattr(repository, f'update_{field}')('missing', 'value') is None
        assert repository.load_executions() == before


def test_action_wrappers_use_their_bound_repository(tmp_path):
    first_app = Flask('first')
    second_app = Flask('second')
    first_app.config['DOMAIN_DATA_DIR'] = str(tmp_path / 'first')
    second_app.config['DOMAIN_DATA_DIR'] = str(tmp_path / 'second')
    first = init_repository(first_app)
    second = init_repository(second_app)
    executions = Executions(runs=(ExecutionRun('p1', 'TC-1'),))
    first.replace_executions(executions)
    second.replace_executions(executions)

    with second_app.app_context():
        first.update_action_status(executions.runs[0].id, 'running')
        first.update_action_input(executions.runs[0].id, {'command': 'start'})
        assert get_repository().load_executions() == executions

    assert first.load_executions().runs[0].action_status == 'running'
    assert first.load_executions().runs[0].action_input == {'command': 'start'}


def test_existing_execution_action_methods_persist_values(app):
    with app.app_context():
        execution_id = ExecutionRepository.start('TC-1', 'p1')['id']
        assert ExecutionRepository.update_action_status(execution_id, 'running')['action_status'] == 'running'
        assert ExecutionRepository.update_action_input(execution_id, {'value': 1})['action_input'] == {'value': 1}
        run = get_repository().load_executions().runs[0]
        assert run.action_status == 'running'
        assert run.action_input == {'value': 1}


@pytest.mark.parametrize('field,value', [
    ('action_status', 'running'),
    ('action_input', {'command': 'start'}),
])
def test_legacy_stored_id_and_import_work(app, field, value):
    import json
    from app.features.execution.models.execution import ExecutionRepository as LegacyRepository

    with app.app_context():
        repository = get_repository()
        data_path = Path(repository.data_dir) / repository.EXECUTIONS_FILE
        data_path.write_text(json.dumps({'execution_runs': [{
            'id': 'ex_legacy_123', 'procedure_id': 'p1', 'test_item_id': 'TC-1',
        }]}), encoding='utf-8')
        result = getattr(LegacyRepository, f'update_{field}')(
            execution_id='ex_legacy_123', **{field: value},
        )
        assert result['id'] == 'ex_legacy_123'
        assert result[field] == value
        assert LegacyRepository.get_by_id('ex_legacy_123')['id'] == 'ex_legacy_123'
        LegacyRepository.start('TC-1', 'p1')
        LegacyRepository.reset('p1', 'TC-1')
        run = JsonDomainRepository(repository.data_dir).load_executions().runs[0]
        assert run.id == 'ex_legacy_123'
        assert getattr(run, field) == value
        assert json.loads(data_path.read_text(encoding='utf-8'))['execution_runs'][0]['id'] == 'ex_legacy_123'


def test_records_without_id_have_stable_distinct_ids(app):
    import json

    with app.app_context():
        repository = get_repository()
        data_path = Path(repository.data_dir) / repository.EXECUTIONS_FILE
        data_path.write_text(json.dumps({'execution_runs': [
            {'procedure_id': 'p1', 'test_item_id': 'TC-1'},
            {'procedure_id': 'p2', 'test_item_id': 'TC-1'},
        ]}), encoding='utf-8')
        before = data_path.read_bytes()
        first, second = repository.load_executions().runs
        assert first.id != second.id
        assert first.id == JsonDomainRepository(repository.data_dir).load_executions().runs[0].id
        assert data_path.read_bytes() == before
        repository.update_action_input(first.id, {'value': 1})
        reloaded = repository.load_executions().runs
        assert reloaded[0].id == first.id
        assert reloaded[0].action_input == {'value': 1}
        assert reloaded[1].id == second.id
        assert reloaded[1].action_input is None
        assert ExecutionRepository.start('TC-1', 'p1')['id'] == first.id


def test_execution_api_exposes_id_for_action_updates(app, client):
    from app.features.schedule.domain import TestProcedure

    with app.app_context():
        get_repository().replace_test_procedures((TestProcedure.from_dict({
            'id': 'p1', 'document_name': 'Test',
            'test_items': [{'id': 'TC-1', 'name': 'Test item'}],
        }),))
    response = client.post('/execution/api/start', json={
        'procedure_id': 'p1', 'test_item_id': 'TC-1',
    })
    assert response.status_code == 201
    execution_id = response.get_json()['id']
    assert execution_id.startswith('ex_')
    detail = client.get('/execution/api/item/TC-1?procedure_id=p1')
    assert detail.status_code == 200
    assert detail.get_json()['execution']['id'] == execution_id
    rows = client.get('/execution/api/list').get_json()
    assert next(row for row in rows if row['procedure_id'] == 'p1')['execution']['id'] == execution_id
    with app.app_context():
        assert get_repository().update_action_input(execution_id, {'value': 1})['id'] == execution_id


def test_action_signatures_match_the_legacy_contract():
    from inspect import signature

    for name, value_name in (
        ('update_action_input', 'action_input'),
        ('update_action_status', 'action_status'),
    ):
        assert list(signature(getattr(ExecutionRepository, name)).parameters) == ['execution_id', value_name]
        assert list(signature(getattr(JsonDomainRepository, name)).parameters) == ['self', 'execution_id', value_name]
