"""Preview schedule changes using the production rules without writing files."""
from dataclasses import replace

from app.features.schedule.domain import TestPlan
from app.features.schedule.services.blocks import ScheduleBlockError, ScheduleBlockService
from app.features.schedule.services.presentation import schedule_settings


class _PreviewRepository:
    """Keep mutations confined to one immutable in-memory plan snapshot."""

    def __init__(self, repository):
        operations = repository.load_operations()
        self.plan = TestPlan(version_id=operations.version_id,
                             test_procedures=operations.test_procedures,
                             schedule_blocks=operations.schedule_blocks)
        self.executions = operations.executions
        self.settings = repository.load_settings()

    def load_plan(self):
        return self.plan

    def load_schedule(self):
        return self.plan.schedule

    def load_test_procedures(self):
        return self.plan.test_procedures

    def load_executions(self):
        return self.executions

    def load_settings(self):
        return self.settings

    def update_plan(self, operation):
        self.plan = operation(self.plan)
        return self.plan

    def update_schedule(self, operation):
        schedule = operation(self.plan.schedule)
        self.plan = replace(self.plan, schedule_blocks=schedule.blocks)
        return schedule


def preview_placement(repository, action, data, block_id=None):
    """Return subsequent-day placements that require a user's decision."""
    snapshot = _PreviewRepository(repository)
    before = {block.id: block for block in snapshot.plan.schedule_blocks}
    current = before.get(block_id)
    requested_date = data.get('date') or (current.date if current else '')
    service = ScheduleBlockService(snapshot)
    if action == 'create':
        service.create(data)
    elif action == 'update':
        service.update(block_id, data)
    elif action in ('split', 'return-test_items'):
        command = service.split if action == 'split' else service.return_test_items
        command(block_id, data.get('keep_test_item_ids', []), schedule_settings(snapshot.settings))
    else:
        raise ScheduleBlockError('지원하지 않는 배치 미리보기 요청입니다.')
    subsequent = [block for block in snapshot.plan.schedule_blocks
                  if block != before.get(block.id)
                  and (block.continuation_of or block.date > requested_date)]
    return {
        'requires_confirmation': bool(subsequent),
        'segments': [{'date': block.date, 'start_time': block.start_time,
                      'end_time': block.end_time} for block in subsequent],
    }
