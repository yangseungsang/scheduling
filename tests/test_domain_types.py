"""Contract tests for shared domain types."""

from app.features.execution.domain import ExecutionRun, Executions
from app.features.schedule.domain import Schedule, ScheduleBlock, TestItem, TestProcedure


def _domain_sections():
    procedures = tuple(TestProcedure.from_dict(item) for item in [{
            'id': 'procedure_1', 'document_id': 'doc_1', 'document_name': '절차서',
            'test_round': 1,
            'test_items': [{
                'id': 'TC-1', 'name': '시험', 'estimated_minutes': 30,
            }],
        }])
    schedule = Schedule.from_dict({
        'blocks': [{
            'id': 'block_1', 'procedure_id': 'procedure_1',
            'test_item_ids': ['TC-1'], 'date': '2026-08-09',
            'start_time': '09:00', 'end_time': '09:30',
        }],
    })
    executions = Executions.from_dict({
        'runs': [{
            'procedure_id': 'procedure_1',
            'test_item_id': 'TC-1',
            'status': 'pending',
        }],
    })
    return procedures, schedule, executions


def test_domain_sections_use_named_types():
    procedures, schedule, executions = _domain_sections()

    assert isinstance(procedures, tuple)
    assert isinstance(procedures[0], TestProcedure)
    assert isinstance(procedures[0].test_items[0], TestItem)
    assert isinstance(schedule, Schedule)
    assert isinstance(schedule.blocks[0], ScheduleBlock)
    assert isinstance(executions, Executions)
    assert isinstance(executions.runs[0], ExecutionRun)

    procedure = procedures[0]
    assert procedure.id == 'procedure_1'
    assert procedure.test_items[0].id == 'TC-1'
    assert procedure.document_name == '절차서'
    assert schedule.blocks[0].procedure_id == procedure.id
    assert executions.runs[0].test_item_id == procedure.test_items[0].id
