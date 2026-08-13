"""Internal typed mutations used by the schedule block service."""

import uuid
from dataclasses import replace

from app.domain.scheduling import Schedule, ScheduleBlock
from app.repositories import JsonDomainRepository

BLOCK_FIELDS = {
    'procedure_id', 'test_item_ids', 'date', 'start_time', 'end_time',
    'location_name', 'assignee_names', 'kind', 'title', 'memo', 'is_locked',
    'manual_status', 'overflow_minutes',
}


class ScheduleCommandService:
    def __init__(self, data_dir):
        self.repository = JsonDomainRepository(data_dir)
        self.repository.initialize()

    def get_block(self, block_id):
        block = next(
            (item for item in self.repository.load_schedule().blocks if item.id == block_id),
            None,
        )
        return _block_dict(block) if block else None

    def test_item_ids_for_procedure(self, procedure_id, selected_ids=None):
        procedure = next(
            (item for item in self.repository.load_test_procedures() if item.id == procedure_id),
            None,
        )
        if procedure is None:
            raise ValueError(f'procedure not found: {procedure_id}')
        available = {item.id for item in procedure.test_items}
        if selected_ids is None:
            return [item.id for item in procedure.test_items]
        missing = [item_id for item_id in selected_ids if item_id not in available]
        if missing:
            raise ValueError(f'test_item not found: {", ".join(missing)}')
        return list(selected_ids)

    def create_block(
        self, *, date, start_time, end_time, procedure_id=None, test_item_ids=None,
        location_name='', assignee_names=None, kind='test', title='', memo='',
        is_locked=False, manual_status='', overflow_minutes=0, block_id='',
    ):
        block_id = block_id or f'blk_{uuid.uuid4().hex[:12]}'
        result = []
        def create(operations):
            if any(item.id == block_id for item in operations.schedule_blocks):
                raise ValueError(f'block already exists: {block_id}')
            if location_name and any(
                item.date == date
                and item.location_name == location_name
                and start_time < item.end_time
                and item.start_time < end_time
                for item in operations.schedule_blocks
            ):
                raise ValueError('같은 장소의 일정과 시간이 겹칩니다.')
            selected = test_item_ids
            if procedure_id:
                procedure = next(
                    (item for item in operations.test_procedures if item.id == procedure_id), None,
                )
                if procedure is None:
                    raise ValueError(f'procedure not found: {procedure_id}')
                available = {item.id for item in procedure.test_items}
                if test_item_ids is None:
                    assigned = {
                        test_item_id
                        for item in operations.schedule_blocks
                        if item.procedure_id == procedure_id
                        for test_item_id in item.test_item_ids
                    }
                    selected = [
                        item.id for item in procedure.test_items
                        if item.id not in assigned
                    ]
                else:
                    selected = list(test_item_ids)
                missing = [item for item in selected if item not in available]
                if missing:
                    raise ValueError(f'test_item not found: {", ".join(missing)}')
                if not selected:
                    raise ValueError('연결할 시험 항목를 찾을 수 없습니다.')
            block = ScheduleBlock(
                id=block_id, procedure_id=procedure_id,
                test_item_ids=tuple(selected or []), date=date,
                start_time=start_time, end_time=end_time,
                location_name=location_name,
                assignee_names=tuple(assignee_names or []), kind=kind,
                title=title, memo=memo, is_locked=bool(is_locked),
                manual_status=manual_status,
                overflow_minutes=int(overflow_minutes or 0),
            )
            result.append(block)
            return replace(
                operations,
                schedule_blocks=operations.schedule_blocks + (block,),
            )
        self.repository.update_plan(create)
        block = result[0]
        return _block_dict(block)

    def update_block(self, block_id, **fields):
        updates = {key: value for key, value in fields.items() if key in BLOCK_FIELDS}
        if 'assignee_names' in updates:
            updates['assignee_names'] = tuple(updates['assignee_names'] or [])
        if 'test_item_ids' in updates:
            updates['test_item_ids'] = tuple(updates['test_item_ids'] or [])
        if 'is_locked' in updates:
            updates['is_locked'] = bool(updates['is_locked'])
        if 'overflow_minutes' in updates:
            updates['overflow_minutes'] = int(updates['overflow_minutes'] or 0)
        result = []
        def update(operations):
            block = next(
                (item for item in operations.schedule_blocks if item.id == block_id),
                None,
            )
            if block is None:
                return operations
            updated_block = replace(block, **updates)
            result.append(updated_block)
            return replace(operations, schedule_blocks=tuple(
                updated_block if item.id == block_id else item
                for item in operations.schedule_blocks
            ))
        self.repository.update_plan(update)
        return _block_dict(result[0]) if result else None

    def replace_test_items(self, block_id, test_item_ids):
        block = self.get_block(block_id)
        if block is None:
            return None
        test_items = self.test_item_ids_for_procedure(block['procedure_id'], test_item_ids)
        return self.update_block(block_id, test_item_ids=test_items)

    def delete_block(self, block_id):
        deleted = []
        def delete(operations):
            if not any(item.id == block_id for item in operations.schedule_blocks):
                return operations
            deleted.append(True)
            return replace(operations, schedule_blocks=tuple(
                item for item in operations.schedule_blocks
                if item.id != block_id
            ))
        self.repository.update_plan(delete)
        return bool(deleted)


def _block_dict(block):
    data = {
        'id': block.id,
        'procedure_id': block.procedure_id,
        'test_item_ids': list(block.test_item_ids),
        'date': block.date,
        'start_time': block.start_time,
        'end_time': block.end_time,
        'location_name': block.location_name,
        'assignee_names': list(block.assignee_names),
        'kind': block.kind,
        'title': block.title,
        'memo': block.memo,
        'is_locked': block.is_locked,
        'manual_status': block.manual_status,
        'overflow_minutes': block.overflow_minutes,
    }
    data['block_status'] = data.get('manual_status') or 'pending'
    data['is_simple'] = block.kind == 'simple'
    return data
