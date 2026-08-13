import pytest

from scripts.seed_test_data import SEED_VERSION_ID, build_seed_data, seed

from app.repositories import JsonDomainRepository


def test_seed_data_references_existing_procedures_and_test_items():
    procedures, schedule, executions, _settings = build_seed_data('2026-08-10')
    procedures_by_id = {procedure.id: procedure for procedure in procedures}

    for block in schedule.blocks:
        if block.procedure_id is None:
            assert block.kind == 'simple'
            continue
        procedure = procedures_by_id[block.procedure_id]
        test_items = {item.id for item in procedure.test_items}
        assert set(block.test_item_ids) <= test_items

    for run in executions.runs:
        procedure = procedures_by_id[run.procedure_id]
        assert run.test_item_id in {item.id for item in procedure.test_items}


def test_seed_writes_domain_files_and_requires_force_to_replace(tmp_path):
    seed(tmp_path, '2026-08-10')
    repository = JsonDomainRepository(tmp_path)

    assert len(repository.load_test_procedures()) == 4
    assert len(repository.load_schedule().blocks) == 7
    assert len(repository.load_executions().runs) == 3
    assert repository.load_operations().version_id == SEED_VERSION_ID

    with pytest.raises(RuntimeError, match='--force'):
        seed(tmp_path, '2026-08-11')
