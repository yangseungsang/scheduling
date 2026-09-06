"""Schedule block validation and workflows."""

from dataclasses import replace
from datetime import date, timedelta

from app.features.schedule.services.time import adjust_end_for_breaks, minutes_to_time, time_to_minutes
from app.features.schedule.services._block_commands import ScheduleCommandService
from app.features.schedule.services.presentation import (
    block_test_item_statuses,
    derive_block_status,
    schedule_settings,
)
from app.repositories import JsonDomainRepository, get_repository

VALID_BLOCK_STATUSES = {'pending', 'in_progress', 'completed', 'cancelled'}
VALID_LOCATIONS = {'STE1', 'STE2', 'STE3'}


class ScheduleBlockError(Exception):
    """Business validation error carrying the HTTP status expected by routes."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class ScheduleBlockService:
    """Validate and coordinate schedule-block workflows."""

    def __init__(self, repository: JsonDomainRepository):
        """Bind validation and low-level commands to the same repository."""
        self.repository = repository
        self.commands = ScheduleCommandService(repository)

    def create(self, data):
        """Create a simple or procedure-backed block after validation."""
        _require(data, ('date', 'start_time', 'end_time'))
        settings = schedule_settings(self.repository.load_settings())
        end_time = adjust_end_for_breaks(data['start_time'], data['end_time'], settings)
        end_time = _clamp_to_work_end(data['start_time'], end_time, settings)
        if data.get('is_simple', False):
            _validate_location(data.get('location_name', ''), required=True)
            self._reject_overlap(data['date'], data['start_time'], end_time, data.get('location_name', ''))
            return _api_block(self.commands.create_block(
                date=data['date'], start_time=data['start_time'], end_time=end_time,
                location_name=data.get('location_name', ''),
                assignee_names=data.get('assignee_names', []), kind='simple',
                title=data.get('title', ''), memo=data.get('memo', ''),
                is_locked=data.get('is_locked', False),
            ))

        _require(data, ('procedure_id',))
        try:
            requested_ids = data.get('test_item_ids')
            test_item_ids = (
                None if requested_ids is None
                else self.commands.test_item_ids_for_procedure(
                    data['procedure_id'], requested_ids,
                )
            )
            if requested_ids is not None and not test_item_ids:
                raise ScheduleBlockError('연결할 시험 항목를 찾을 수 없습니다.')
            procedure = self._procedure(data['procedure_id'])
            location_name = data.get('location_name', '')
            _validate_location(location_name, required=True)
            assignee_names = data.get('assignee_names') or list(procedure.assignee_names)
            self._reject_overlap(data['date'], data['start_time'], end_time, location_name)
            if requested_ids is not None:
                self._unassign_test_items(data['procedure_id'], test_item_ids)
            block = self.commands.create_block(
                procedure_id=data['procedure_id'], test_item_ids=test_item_ids,
                date=data['date'], start_time=data['start_time'], end_time=end_time,
                location_name=location_name, assignee_names=assignee_names, kind='test',
                title=data.get('title', ''), memo=data.get('memo', ''),
                is_locked=data.get('is_locked', False),
                manual_status=data.get('block_status', ''),
                overflow_minutes=data.get('overflow_minutes', 0),
            )
        except ValueError as exc:
            raise ScheduleBlockError(str(exc)) from exc
        return _api_block(block)

    def update(self, block_id, data):
        """Update allowed block fields and reject schedule collisions."""
        current = self.commands.get_block(block_id)
        if current is None:
            raise ScheduleBlockError('블록을 찾을 수 없습니다.', 404)
        if not data:
            raise ScheduleBlockError('요청 데이터가 없습니다.')
        allowed = {
            'date', 'start_time', 'end_time', 'is_locked', 'location_name',
            'memo', 'title', 'overflow_minutes',
        }
        updates = {key: value for key, value in data.items() if key in allowed}
        start_time = updates.get('start_time', current['start_time'])
        end_time = updates.get('end_time', current['end_time'])
        date_str = updates.get('date', current['date'])
        location_name = updates.get('location_name', current.get('location_name', ''))
        _validate_location(location_name)
        if 'start_time' in updates or 'end_time' in updates:
            settings = schedule_settings(self.repository.load_settings())
            end_time = adjust_end_for_breaks(start_time, end_time, settings)
            end_time = _clamp_to_work_end(start_time, end_time, settings)
            updates['end_time'] = end_time
        self._reject_overlap(date_str, start_time, end_time, location_name, block_id)
        if 'block_status' in data:
            updates['manual_status'] = data['block_status']
        updated = self.commands.update_block(block_id, **updates)
        if 'test_item_ids' in data:
            self._replace_test_items(block_id, updated, data['test_item_ids'])
        return _api_block(self.commands.get_block(block_id))

    def delete(self, block_id, restore=False):
        """Delete one block, or all sibling blocks when restoring a procedure."""
        block = self.commands.get_block(block_id)
        if block is None:
            raise ScheduleBlockError('블록을 찾을 수 없습니다.', 404)
        restore_all = restore in ('task', 'all')
        if restore_all and block.get('procedure_id'):
            procedure_id = block['procedure_id']
            deleted_count = 0

            def delete_siblings(schedule):
                nonlocal deleted_count
                remaining = []
                for item in schedule.blocks:
                    if item.procedure_id == procedure_id:
                        deleted_count += 1
                    else:
                        remaining.append(item)
                return replace(schedule, blocks=tuple(remaining))

            self.repository.update_schedule(delete_siblings)
        else:
            deleted_count = int(self.commands.delete_block(block_id))
        return {'success': True, 'deleted_count': deleted_count}

    def toggle_lock(self, block_id):
        """Toggle the edit lock on an existing block."""
        block = self._required_block(block_id)
        return _api_block(self.commands.update_block(block_id, is_locked=not block['is_locked']))

    def set_status(self, block_id, status):
        """Set a manual block status used ahead of derived execution status."""
        self._required_block(block_id)
        return _api_block(self.commands.update_block(block_id, manual_status=status))

    def set_memo(self, block_id, memo):
        """Replace a block memo without changing its placement."""
        self._required_block(block_id)
        return _api_block(self.commands.update_block(block_id, memo=memo))

    def list_by_procedure(self, procedure_id):
        """Return procedure blocks with current per-item execution statuses."""
        operations = self.repository.load_operations()
        runs = {
            (item.procedure_id, item.test_item_id): item
            for item in operations.execution_runs
        }
        blocks = []
        for item in operations.schedule_blocks:
            if item.procedure_id != procedure_id:
                continue
            block = _api_block(item.to_dict())
            block['test_item_statuses'] = block_test_item_statuses(item, runs)
            block['block_status'] = derive_block_status(item, runs)
            blocks.append(block)
        blocks.sort(key=lambda item: (item['date'], item['start_time'], item['id']))
        return {'blocks': blocks}

    def shift(self, from_date, direction=1):
        """Move unlocked blocks on/after a date while skipping weekends."""
        if not from_date:
            raise ScheduleBlockError('from_date는 필수입니다.')
        direction = int(direction or 1)
        shifted = 0
        def update(schedule):
            nonlocal shifted
            blocks = []
            for block in schedule.blocks:
                if block.date < from_date or block.is_locked:
                    blocks.append(block)
                    continue
                shifted_date = date.fromisoformat(block.date) + timedelta(days=direction)
                while shifted_date.weekday() >= 5:
                    shifted_date += timedelta(days=1 if direction > 0 else -1)
                blocks.append(replace(block, date=shifted_date.isoformat()))
                shifted += 1
            return replace(schedule, blocks=tuple(blocks))
        self.repository.update_schedule(update)
        return {'success': True, 'shifted_count': shifted}

    def split(self, block_id, keep_ids, settings):
        """Split unselected test items into a following block."""
        block = self._required_block(block_id)
        if not block.get('procedure_id'):
            raise ScheduleBlockError('간단 블록은 분리할 수 없습니다.')
        details = self._test_item_details(block['procedure_id'], block['test_item_ids'])
        keep_set = set(keep_ids)
        kept = [item for item in details if item['test_item_id'] in keep_set]
        moved = [item for item in details if item['test_item_id'] not in keep_set]
        if not kept:
            raise ScheduleBlockError('유지할 시험 항목를 선택해주세요.')
        if not moved:
            raise ScheduleBlockError('분리할 시험 항목가 없습니다.')
        first_end = _end_after_minutes(block['start_time'], _sum_minutes(kept), settings)
        second_end = _end_after_minutes(first_end, _sum_minutes(moved), settings)
        if self._check_overlap(block['date'], first_end, second_end, block.get('location_name', ''), block_id):
            raise ScheduleBlockError('분리된 블록이 다른 블록과 시간이 겹칩니다.', 409)
        self.commands.update_block(block_id, end_time=first_end, test_item_ids=[item['test_item_id'] for item in kept])
        new_block = self.commands.create_block(
            procedure_id=block['procedure_id'], test_item_ids=[item['test_item_id'] for item in moved],
            date=block['date'], start_time=first_end, end_time=second_end,
            location_name=block.get('location_name', ''),
            assignee_names=block.get('assignee_names', []), kind=block.get('kind', 'test'),
            title=block.get('title', ''), memo=block.get('memo', ''),
            is_locked=block.get('is_locked', False),
            manual_status=block.get('manual_status', ''),
        )
        return {'success': True, 'new_block': _api_block(new_block)}

    def return_test_items(self, block_id, keep_ids, settings):
        """Keep selected items in a resized block and return the rest to the queue."""
        block = self._required_block(block_id)
        if not keep_ids:
            self.commands.delete_block(block_id)
            return {'success': True}
        details = self._test_item_details(block['procedure_id'], keep_ids)
        if not details:
            self.commands.delete_block(block_id)
            return {'success': True}
        end_time = _end_after_minutes(block['start_time'], _sum_minutes(details), settings)
        self.commands.update_block(block_id, end_time=end_time, test_item_ids=keep_ids)
        return {'success': True}

    def _replace_test_items(self, block_id, block, test_item_ids):
        """Move valid items from any old blocks into the target block."""
        if not block or not block.get('procedure_id'):
            raise ScheduleBlockError('간단 블록에는 test_item_ids를 설정할 수 없습니다.')
        try:
            valid = self.commands.test_item_ids_for_procedure(block['procedure_id'], test_item_ids)
            if not valid:
                raise ScheduleBlockError('연결할 시험 항목를 찾을 수 없습니다.')
            self._unassign_test_items(block['procedure_id'], valid, exclude_block_id=block_id)
            self.commands.replace_test_items(block_id, valid)
        except ValueError as exc:
            raise ScheduleBlockError(str(exc)) from exc

    def _test_item_details(self, procedure_id, test_item_ids):
        """Resolve selected item IDs and their estimated durations."""
        procedure = self._procedure(procedure_id)
        selected = set(test_item_ids)
        return [
            {'test_item_id': item.id, 'estimated_minutes': item.estimated_minutes}
            for item in procedure.test_items if item.id in selected
        ]

    def _unassign_test_items(self, procedure_id, test_item_ids, exclude_block_id=None):
        """Remove selected items from other blocks and discard empty test blocks."""
        selected = set(test_item_ids)
        def update(schedule):
            blocks = []
            for block in schedule.blocks:
                if block.id == exclude_block_id or block.procedure_id != procedure_id:
                    blocks.append(block)
                    continue
                remaining = tuple(
                    item for item in block.test_item_ids if item not in selected
                )
                if remaining or block.kind == 'simple':
                    blocks.append(replace(block, test_item_ids=remaining))
            return replace(schedule, blocks=tuple(blocks))
        self.repository.update_schedule(update)

    def _procedure(self, procedure_id):
        """Load one required procedure or raise a route-friendly 404 error."""
        procedure = next((item for item in self.repository.load_test_procedures() if item.id == procedure_id), None)
        if procedure is None:
            raise ScheduleBlockError('시험 절차서를 찾을 수 없습니다.', 404)
        return procedure

    def _required_block(self, block_id):
        """Load one required block or raise a route-friendly 404 error."""
        block = self.commands.get_block(block_id)
        if block is None:
            raise ScheduleBlockError('블록을 찾을 수 없습니다.', 404)
        return block

    def _reject_overlap(self, date_str, start_time, end_time, location_name, exclude_block_id=None):
        """Raise a conflict when another block occupies the same place and time."""
        if self._check_overlap(date_str, start_time, end_time, location_name, exclude_block_id):
            raise ScheduleBlockError('같은 장소의 일정과 시간이 겹칩니다.', 409)

    def _check_overlap(self, date_str, start_time, end_time, location_name, exclude_block_id=None):
        """Return the first overlapping block, or None when placement is valid."""
        if not location_name:
            return None
        start_min = time_to_minutes(start_time)
        end_min = time_to_minutes(end_time)
        for block in self.repository.load_schedule().blocks:
            if block.id == exclude_block_id or block.date != date_str or block.location_name != location_name:
                continue
            if start_min < time_to_minutes(block.end_time) and time_to_minutes(block.start_time) < end_min:
                return _api_block(block.to_dict())
        return None


def _require(data, fields):
    """Validate required truthy request fields."""
    for field in fields:
        if not data.get(field):
            raise ScheduleBlockError(f'{field}은(는) 필수 항목입니다.')


def _validate_location(location_name, required=False):
    """Reject location names outside the three physical STE columns."""
    if required and not location_name:
        raise ScheduleBlockError('배치 장소를 선택해주세요.')
    if location_name and location_name not in VALID_LOCATIONS:
        raise ScheduleBlockError('장소는 STE1, STE2, STE3 중 하나여야 합니다.')


def _api_block(block):
    """Add stable response defaults and compatibility fields to a block dict."""
    data = {
        'procedure_id': None,
        'test_item_ids': [],
        'location_name': '',
        'assignee_names': [],
        'kind': 'test',
        'title': '',
        'memo': '',
        'is_locked': False,
        'manual_status': '',
        'overflow_minutes': 0,
        **dict(block),
    }
    data['block_status'] = data.get('manual_status') or data.get('block_status') or 'pending'
    data['is_simple'] = data.get('kind') == 'simple'
    return data


def _sum_minutes(items):
    """Sum estimated durations from item dictionaries."""
    return sum(int(item.get('estimated_minutes') or 0) for item in items)


def _end_after_minutes(start_time, minutes, settings):
    """Calculate an end time while accounting for configured breaks."""
    raw_end = minutes_to_time(time_to_minutes(start_time) + max(minutes, 1))
    adjusted_end = adjust_end_for_breaks(start_time, raw_end, settings)
    return _clamp_to_work_end(start_time, adjusted_end, settings)


def _clamp_to_work_end(start_time, end_time, settings):
    """Keep a block on the same day and cap it at the configured work end."""
    work_end = settings.get('work_end', '17:00')
    if time_to_minutes(start_time) >= time_to_minutes(work_end):
        raise ScheduleBlockError(f'업무 종료 시간({work_end}) 이후에는 배치할 수 없습니다.')
    return work_end if time_to_minutes(end_time) > time_to_minutes(work_end) else end_time


def _service():
    """Create a request-scoped service backed by the current app repository."""
    return ScheduleBlockService(get_repository())


def get_all():
    """Return all blocks in API-compatible dictionary form."""
    repository = get_repository()
    return [_api_block(item.to_dict()) for item in repository.load_schedule().blocks]


def get_by_id(block_id):
    """Find one API block by ID."""
    return next((item for item in get_all() if item['id'] == block_id), None)


def get_by_date(date_str):
    """Return blocks placed on one date."""
    return [item for item in get_all() if item['date'] == date_str]


def get_by_date_range(start_date, end_date):
    """Return blocks in an inclusive ISO date range."""
    return [
        item for item in get_all()
        if start_date <= item['date'] <= end_date
    ]


def get_by_assignee(name):
    """Return blocks assigned to the given display name."""
    return [
        item for item in get_all()
        if name in item.get('assignee_names', [])
    ]


def get_by_location_and_date(location_name, date_str):
    """Return blocks matching one location and date."""
    return [
        item for item in get_all()
        if item.get('location_name') == location_name
        and item['date'] == date_str
    ]


def create(
    procedure_id, assignee_names, location_name, date, start_time, end_time,
    is_locked=False, block_status='pending', test_item_ids=None,
    title='', is_simple=False, overflow_minutes=0, **kwargs,
):
    """Compatibility facade for creating a block in the current Flask app."""
    return _service().create({
        'procedure_id': procedure_id,
        'assignee_names': assignee_names or [],
        'location_name': location_name,
        'date': date,
        'start_time': start_time,
        'end_time': end_time,
        'is_locked': is_locked,
        'block_status': block_status,
        'test_item_ids': test_item_ids,
        'title': title,
        'is_simple': is_simple,
        'overflow_minutes': overflow_minutes,
        **kwargs,
    })


def update(block_id, **updates):
    """Compatibility facade for updating a block."""
    return _service().update(block_id, updates)


def delete(block_id):
    """Delete a block and convert a missing block into False."""
    try:
        _service().delete(block_id)
        return True
    except ScheduleBlockError:
        return False
