"""Schedule block validation and workflows."""

from dataclasses import replace
from datetime import date, timedelta

from app.features.schedule.services.time import minutes_to_time, time_to_minutes
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
        """Place work across as many weekdays as its duration needs."""
        _require(data, ('date', 'start_time', 'end_time'))
        if not data.get('is_simple', False):
            _require(data, ('procedure_id',))
        return self._save_placement(data)

    def update(self, block_id, data):
        """Update a placement, preserving all of its continuation minutes."""
        current = self._required_block(block_id)
        if not data:
            raise ScheduleBlockError('요청 데이터가 없습니다.')
        if any(key in data for key in ('date', 'start_time', 'end_time', 'test_item_ids', 'location_name')):
            return self._save_placement({**current, **data}, block_id, data)
        updates = {key: data[key] for key in ('is_locked', 'memo', 'title') if key in data}
        if 'block_status' in data:
            updates['manual_status'] = data['block_status']
        return self._response(self.commands.update_block(block_id, **updates))

    def _response(self, block):
        """Use the same execution-derived status as calendar read responses."""
        from app.features.schedule.domain import ScheduleBlock
        runs = {(run.procedure_id, run.test_item_id): run for run in self.repository.load_executions().runs}
        typed = ScheduleBlock.from_dict(block)
        response = _api_block(block)
        response['block_status'] = derive_block_status(typed, runs)
        response['test_item_statuses'] = block_test_item_statuses(typed, runs)
        return response

    def _save_placement(self, data, block_id=None, changes=None):
        """Validate every day and replace the entire placement atomically."""
        import uuid
        from app.features.schedule.domain import ScheduleBlock
        from app.features.schedule.services.time import working_segments, work_minutes_in_range
        settings = schedule_settings(self.repository.load_settings())
        if data.get('procedure_id') and data.get('test_item_ids') == []:
            raise ScheduleBlockError('연결할 시험 항목를 찾을 수 없습니다.')
        location = data.get('location_name', '')
        _validate_location(location, required=block_id is None)
        created = []
        def save(plan):
            existing = next((block for block in plan.schedule_blocks if block.id == block_id), None)
            root_id = (existing.continuation_of or existing.id) if existing else f'blk_{uuid.uuid4().hex[:12]}'
            group = [block for block in plan.schedule_blocks
                     if block.id == root_id or block.continuation_of == root_id]
            remaining = [block for block in plan.schedule_blocks if block not in group]
            if block_id is None:
                for item in remaining:
                    if location and item.date == data['date'] and item.location_name == location and data['start_time'] < item.end_time and item.start_time < data['end_time']:
                        raise ScheduleBlockError('같은 장소의 일정과 시간이 겹칩니다.', 409)
            procedure_id = data.get('procedure_id')
            procedure = next((item for item in plan.test_procedures if item.id == procedure_id), None)
            simple = data.get('is_simple', False) or not procedure_id
            if not simple and procedure is None:
                raise ScheduleBlockError('시험 절차서를 찾을 수 없습니다.', 404)
            if not simple:
                available = {item.id for item in procedure.test_items}
                selected = data.get('test_item_ids')
                if selected is None:
                    assigned = {iid for block in remaining if block.procedure_id == procedure_id for iid in block.test_item_ids}
                    selected = [item.id for item in procedure.test_items if item.id not in assigned]
                if not selected or set(selected) - available:
                    raise ScheduleBlockError('연결할 시험 항목를 찾을 수 없습니다.')
                selected = tuple(dict.fromkeys(selected))
                if (block_id is None and data.get('test_item_ids') is not None) or (changes and 'test_item_ids' in changes):
                    remaining = [replace(block, test_item_ids=tuple(iid for iid in block.test_item_ids if iid not in selected))
                                 if block.procedure_id == procedure_id else block for block in remaining]
                    remaining = [block for block in remaining if block.test_item_ids or block.kind == 'simple']
            else:
                selected = ()
            duration = time_to_minutes(data['end_time']) - time_to_minutes(data['start_time'])
            if existing and changes and 'end_time' not in changes:
                duration = sum(work_minutes_in_range(block.start_time, block.end_time, settings) for block in group)
            try:
                segments = working_segments(data['date'], data['start_time'], duration, settings)
            except (ValueError, TypeError) as exc:
                raise ScheduleBlockError(str(exc)) from exc
            for index, segment in enumerate(segments):
                if location and any(block.date == segment['date'] and block.location_name == location
                                    and segment['start_time'] < block.end_time and block.start_time < segment['end_time']
                                    for block in remaining):
                    raise ScheduleBlockError('같은 장소의 일정과 시간이 겹칩니다.', 409)
                created.append(ScheduleBlock(
                    id=root_id if index == 0 else f'blk_{uuid.uuid4().hex[:12]}',
                    continuation_of='' if index == 0 else root_id,
                    procedure_id=procedure_id, test_item_ids=selected, kind='simple' if simple else 'test',
                    location_name=location, assignee_names=tuple(data.get('assignee_names') or (procedure.assignee_names if procedure else ())),
                    title=data.get('title', ''), memo=data.get('memo', ''), is_locked=bool(data.get('is_locked', False)),
                    manual_status=(changes.get('block_status', data.get('manual_status', '')) if changes else data.get('block_status', '')),
                    **segment,
                ))
            return replace(plan, schedule_blocks=tuple(remaining + created))
        self.repository.update_plan(save)
        response = self._response(created[0].to_dict())
        response['continuations'] = [self._response(block.to_dict()) for block in created[1:]]
        response['placement_end'] = {'date': created[-1].date, 'end_time': created[-1].end_time}
        return response

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
            root_id = block.get('continuation_of') or block_id
            deleted_count = 0
            def delete_group(schedule):
                nonlocal deleted_count
                kept = tuple(item for item in schedule.blocks if item.id != root_id and item.continuation_of != root_id)
                deleted_count = len(schedule.blocks) - len(kept)
                return replace(schedule, blocks=kept)
            self.repository.update_schedule(delete_group)
        return {'success': True, 'deleted_count': deleted_count}

    def toggle_lock(self, block_id):
        """Toggle the edit lock on an existing block."""
        block = self._required_block(block_id)
        return _api_block(self.commands.update_block(block_id, is_locked=not block['is_locked']))

    def set_status(self, block_id, status):
        """Set placement state while reporting the actual test execution state."""
        self._required_block(block_id)
        return self._response(self.commands.update_block(block_id, manual_status=status))

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
        from app.features.schedule.services.time import working_segments
        first_segments = working_segments(block['date'], block['start_time'], max(1, _sum_minutes(kept)), settings)
        last = first_segments[-1]
        second_segments = working_segments(last['date'], last['end_time'], max(1, _sum_minutes(moved)), settings)
        # Validate the whole split before changing either side.
        root_id = block.get('continuation_of') or block_id
        for segment in first_segments + second_segments:
            for existing in self.repository.load_schedule().blocks:
                if existing.id == root_id or existing.continuation_of == root_id:
                    continue
                if existing.location_name == block.get('location_name') and existing.date == segment['date'] and segment['start_time'] < existing.end_time and existing.start_time < segment['end_time']:
                    raise ScheduleBlockError('분리된 블록이 다른 블록과 시간이 겹칩니다.', 409)
        self.update(block_id, {
            'end_time': minutes_to_time(time_to_minutes(block['start_time']) + max(1, _sum_minutes(kept))),
            'test_item_ids': [item['test_item_id'] for item in kept],
        })
        new_block = self.create({
            **block, 'date': last['date'], 'start_time': last['end_time'],
            'end_time': minutes_to_time(time_to_minutes(last['end_time']) + max(1, _sum_minutes(moved))),
            'test_item_ids': [item['test_item_id'] for item in moved],
        })
        return {'success': True, 'new_block': new_block}

    def return_test_items(self, block_id, keep_ids, settings):
        """Keep selected items in a resized block and return the rest to the queue."""
        block = self._required_block(block_id)
        if not keep_ids:
            self.delete(block_id)
            return {'success': True}
        details = self._test_item_details(block['procedure_id'], keep_ids)
        if not details:
            self.delete(block_id)
            return {'success': True}
        end_time = minutes_to_time(time_to_minutes(block['start_time']) + max(1, _sum_minutes(details)))
        self.update(block_id, {'end_time': end_time, 'test_item_ids': keep_ids})
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
