"""TestProcedure application service."""

from app.domain.test_procedures import TestItem, TestProcedure
from dataclasses import replace

from flask import current_app

from app.domain.identity import stable_id
from app.repositories import JsonDomainRepository


class TestProcedureError(Exception):
    __test__ = False
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class TestProcedureService:
    __test__ = False
    def __init__(self, data_dir):
        self.repository = JsonDomainRepository(data_dir)
        self.repository.initialize()

    def create_procedure(self, data):
        procedure_id = data.get('id') or _new_procedure_id(data)
        test_items = _test_items(data.get('test_items', []))
        if not data.get('is_simple') and not test_items:
            raise TestProcedureError('시험 항목를 하나 이상 입력해주세요.')
        procedure = _procedure(procedure_id, data, test_items)
        def create(operations):
            self._validate_unique(
                test_items, data.get('test_round'), test_procedures=operations.test_procedures,
            )
            return replace(operations, test_procedures=operations.test_procedures + (procedure,))
        self.repository.update_plan(create)
        return _procedure_dict(procedure)

    def update_procedure(self, procedure_id, data):
        current = self._find(procedure_id)
        if current is None:
            raise TestProcedureError('시험 항목을 찾을 수 없습니다.', 404)
        merged = {**_procedure_dict(current), **data, 'id': procedure_id}
        test_items = _test_items(merged.get('test_items', []))
        if not merged.get('is_simple') and not test_items:
            raise TestProcedureError('시험 항목를 하나 이상 입력해주세요.')
        updated = _procedure(procedure_id, merged, test_items)
        def update(operations):
            if not any(item.id == procedure_id for item in operations.test_procedures):
                raise TestProcedureError('시험 항목을 찾을 수 없습니다.', 404)
            self._validate_unique(
                test_items, merged.get('test_round'), procedure_id, operations.test_procedures,
            )
            return replace(operations, test_procedures=tuple(
                updated if item.id == procedure_id else item
                for item in operations.test_procedures
            ))
        self.repository.update_plan(update)
        return _procedure_dict(updated)

    def delete_procedure(self, procedure_id):
        if self._find(procedure_id) is None:
            raise TestProcedureError('시험 항목을 찾을 수 없습니다.', 404)
        self.repository.update_operations(lambda operations: replace(
            operations,
            test_procedures=tuple(item for item in operations.test_procedures if item.id != procedure_id),
            schedule_blocks=tuple(
                item for item in operations.schedule_blocks
                if item.procedure_id != procedure_id
            ),
            execution_runs=tuple(
                item for item in operations.execution_runs
                if item.procedure_id != procedure_id
            ),
        ))
        return True

    def get_procedure(self, procedure_id):
        procedure = self._find(procedure_id)
        return _procedure_dict(procedure) if procedure else None

    def _find(self, procedure_id):
        return next(
            (item for item in self.repository.load_test_procedures() if item.id == procedure_id),
            None,
        )

    def _validate_unique(
        self, test_items, test_round, exclude_procedure_id=None, test_procedures=None,
    ):
        new_ids = {item.id for item in test_items}
        duplicates = {
            test_item.id
            for procedure in (
                test_procedures
                if test_procedures is not None
                else self.repository.load_test_procedures()
            )
            if procedure.id != exclude_procedure_id and procedure.test_round == test_round
            for test_item in procedure.test_items
            if test_item.id in new_ids
        }
        if duplicates:
            raise TestProcedureError(f'중복된 시험 항목: {", ".join(sorted(duplicates))}')


def _procedure(procedure_id, data, test_items):
    estimated = int(data.get('estimated_minutes') or 0)
    if not estimated:
        estimated = sum(item.estimated_minutes for item in test_items)
    return TestProcedure(
        id=procedure_id,
        document_id=_document_id(data.get('document_id')),
        document_name=data.get('document_name', ''),
        test_round=data.get('test_round'),
        test_items=tuple(test_items),
        estimated_minutes=estimated,
        assignee_names=tuple(data.get('assignee_names', [])),
        location_name=data.get('location_name', ''),
        memo=data.get('memo', ''),
        state='cancelled' if data.get('status') == 'cancelled' else 'active',
        kind='simple' if data.get('is_simple') else 'test',
    )


def _test_items(items):
    result = []
    for item in items or []:
        if isinstance(item, dict) and item.get('id'):
            result.append(TestItem.from_dict(item))
        elif item:
            result.append(TestItem(id=str(item)))
    return result


def _procedure_dict(procedure):
    return {
        'id': procedure.id,
        'document_id': procedure.document_id,
        'document_name': procedure.document_name,
        'test_round': procedure.test_round,
        'assignee_names': list(procedure.assignee_names),
        'location_name': procedure.location_name,
        'test_items': [
            {
                'id': item.id,
                'name': item.name,
                'estimated_minutes': item.estimated_minutes,
                'total_count': item.total_count,
                'owners': list(item.owner_names),
            }
            for item in procedure.test_items
        ],
        'estimated_minutes': procedure.estimated_minutes,
        'remaining_minutes': procedure.estimated_minutes,
        'memo': procedure.memo,
        'status': 'cancelled' if procedure.state == 'cancelled' else 'pending',
        'is_simple': procedure.kind == 'simple',
    }


def _new_procedure_id(data):
    return stable_id('tp_', data.get('document_id'), data.get('test_round'))


def _document_id(value):
    return None if value in (None, '') else str(value)


def _service():
    return TestProcedureService(current_app.config['DOMAIN_DATA_DIR'])


def get_all():
    repository = JsonDomainRepository(current_app.config['DOMAIN_DATA_DIR'])
    operations = repository.load_plan()
    scheduled_minutes = {}
    for block in operations.schedule_blocks:
        if block.procedure_id:
            minutes = max(
                0,
                _time_minutes(block.end_time) - _time_minutes(block.start_time),
            )
            scheduled_minutes[block.procedure_id] = (
                scheduled_minutes.get(block.procedure_id, 0) + minutes
            )
    rows = []
    for item in operations.test_procedures:
        row = _procedure_dict(item)
        row['remaining_minutes'] = max(
            item.estimated_minutes - scheduled_minutes.get(item.id, 0), 0,
        )
        rows.append(row)
    return sorted(
        rows,
        key=lambda item: (
            item['document_name'], item.get('test_round') or 0, item['id'],
        ),
    )


def get_by_id(procedure_id):
    return next((item for item in get_all() if item['id'] == procedure_id), None)


def create(
    document_id, assignee_names, location_name, document_name, test_items,
    estimated_minutes, memo='', test_round=None, **kwargs,
):
    return _service().create_procedure({
        'document_id': document_id,
        'test_round': test_round,
        'assignee_names': assignee_names or [],
        'location_name': location_name,
        'document_name': document_name,
        'test_items': test_items or [],
        'estimated_minutes': estimated_minutes,
        'memo': memo,
        **kwargs,
    })


def patch(procedure_id, **updates):
    current = get_by_id(procedure_id)
    if current is None:
        return None
    return _service().update_procedure(procedure_id, {**current, **updates})


def update(
    procedure_id, document_id, assignee_names, location_name, document_name, test_items,
    estimated_minutes, memo='',
):
    return patch(
        procedure_id,
        document_id=document_id,
        assignee_names=assignee_names or [],
        location_name=location_name,
        document_name=document_name,
        test_items=test_items or [],
        estimated_minutes=estimated_minutes,
        memo=memo,
    )


def delete(procedure_id):
    try:
        return _service().delete_procedure(procedure_id)
    except TestProcedureError:
        return False


def get_by_document_id(document_id):
    return _get_by_document_and_round(document_id)


def get_by_document_and_round(document_id, test_round):
    return _get_by_document_and_round(document_id, test_round, match_round=True)


def _get_by_document_and_round(document_id, test_round=None, match_round=False):
    try:
        target = int(document_id)
    except (TypeError, ValueError):
        return None
    return next((
        item for item in get_all()
        if str(item.get('document_id')) == str(target)
        and (not match_round or item.get('test_round') == test_round)
    ), None)


def validate_unique_test_items(
    test_items, exclude_procedure_id=None, test_round=None,
):
    new_ids = {
        item['id'] for item in test_items if isinstance(item, dict)
    }
    existing = {
        test_item['id'] if isinstance(test_item, dict) else test_item
        for item in get_all()
        if item['id'] != exclude_procedure_id and item.get('test_round') == test_round
        for test_item in item.get('test_items', [])
    }
    return sorted(new_ids & existing)


def display_name(procedure):
    name = procedure.get('document_name', '')
    test_round = procedure.get('test_round')
    return f'{name} ({test_round}차)' if test_round not in (None, 1) else name


def _time_minutes(value):
    try:
        hours, minutes = value.split(':', 1)
        return int(hours) * 60 + int(minutes)
    except (AttributeError, TypeError, ValueError):
        return 0
