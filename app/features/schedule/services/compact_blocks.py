"""Compatibility service for schedule block APIs backed by compact ORM."""

from datetime import date, timedelta

from app.db.models import BlockItem, ExamAttempt, ScheduleBlock, TestItem
from app.features.schedule.helpers.time_utils import (
    adjust_end_for_breaks,
    minutes_to_time,
    time_to_minutes,
)
from app.services.compact_schedule_commands import CompactScheduleCommandService


class CompactBlockApiError(Exception):
    """Error that can be returned by the schedule block API route."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class CompactScheduleBlockApiService:
    """Translate legacy block API payloads to compact ORM commands."""

    def __init__(self, database_url):
        self.commands = CompactScheduleCommandService(database_url)

    def create(self, data):
        self._require(data, ('date', 'start_time', 'end_time'))
        if data.get('is_simple', False):
            block = self.commands.create_block(
                date=data['date'],
                start_time=data['start_time'],
                end_time=data['end_time'],
                location_id=data.get('location_id', ''),
                assignee_names=data.get('assignee_names', []),
                kind='simple',
                title=data.get('title', ''),
                memo=data.get('memo', ''),
                is_locked=data.get('is_locked', False),
            )
            return _api_block(block)

        self._require(data, ('task_id',))
        try:
            attempt_ids = self.commands.attempt_ids_for_legacy_task(
                data['task_id'],
                data.get('identifier_ids'),
            )
            self._require_attempts(attempt_ids)
            block = self.commands.create_block(
                date=data['date'],
                start_time=data['start_time'],
                end_time=data['end_time'],
                location_id=data.get('location_id', ''),
                assignee_names=data.get('assignee_names', []),
                kind='test',
                title=data.get('title', ''),
                memo=data.get('memo', ''),
                is_locked=data.get('is_locked', False),
                manual_status=data.get('block_status', ''),
                overflow_minutes=data.get('overflow_minutes', 0),
                exam_attempt_ids=attempt_ids,
            )
        except ValueError as exc:
            raise CompactBlockApiError(str(exc)) from exc
        return _api_block(block)

    def update(self, block_id, data):
        if self.commands.get_block(block_id) is None:
            raise CompactBlockApiError('블록을 찾을 수 없습니다.', 404)
        if not data:
            raise CompactBlockApiError('요청 데이터가 없습니다.')

        allowed = {
            'date',
            'start_time',
            'end_time',
            'is_locked',
            'location_id',
            'memo',
            'title',
            'overflow_minutes',
        }
        updates = {key: value for key, value in data.items() if key in allowed}
        if 'block_status' in data:
            updates['manual_status'] = data['block_status']

        updated = self.commands.update_block(block_id, **updates)
        if 'identifier_ids' in data:
            self._replace_identifiers(block_id, updated, data['identifier_ids'])
        return _api_block(self.commands.get_block(block_id))

    def delete(self, block_id):
        if self.commands.get_block(block_id) is None:
            raise CompactBlockApiError('블록을 찾을 수 없습니다.', 404)
        self.commands.delete_block(block_id)
        return {'success': True}

    def toggle_lock(self, block_id):
        block = self.commands.get_block(block_id)
        if block is None:
            raise CompactBlockApiError('블록을 찾을 수 없습니다.', 404)
        updated = self.commands.update_block(
            block_id,
            is_locked=not block.get('is_locked', False),
        )
        return _api_block(updated)

    def set_status(self, block_id, status):
        if self.commands.get_block(block_id) is None:
            raise CompactBlockApiError('블록을 찾을 수 없습니다.', 404)
        updated = self.commands.update_block(block_id, manual_status=status)
        return _api_block(updated)

    def set_memo(self, block_id, memo):
        if self.commands.get_block(block_id) is None:
            raise CompactBlockApiError('블록을 찾을 수 없습니다.', 404)
        updated = self.commands.update_block(block_id, memo=memo)
        return _api_block(updated)

    def list_by_task(self, task_id):
        with self.commands.session_factory() as session:
            block_ids = [
                row[0]
                for row in session.query(BlockItem.block_id)
                .join(ExamAttempt, BlockItem.exam_attempt_id == ExamAttempt.id)
                .filter(ExamAttempt.legacy_task_id == task_id)
                .distinct()
            ]
        blocks = [self.commands.get_block(block_id) for block_id in block_ids]
        blocks = [_api_block(block) for block in blocks if block is not None]
        blocks.sort(key=lambda item: (item.get('date', ''), item.get('start_time', ''), item.get('id', '')))
        return {'blocks': blocks}

    def shift(self, from_date, direction=1):
        if not from_date:
            raise CompactBlockApiError('from_date는 필수입니다.')
        direction = int(direction or 1)
        shifted = 0
        with self.commands.session_factory() as session:
            blocks = list(
                session.query(ScheduleBlock)
                .filter(ScheduleBlock.date >= from_date)
                .order_by(ScheduleBlock.date, ScheduleBlock.start_time, ScheduleBlock.id)
            )
            for block in blocks:
                if block.is_locked:
                    continue
                shifted_date = date.fromisoformat(block.date) + timedelta(days=direction)
                if direction > 0:
                    while shifted_date.weekday() >= 5:
                        shifted_date += timedelta(days=1)
                else:
                    while shifted_date.weekday() >= 5:
                        shifted_date -= timedelta(days=1)
                block.date = shifted_date.isoformat()
                shifted += 1
            session.commit()
        return {'success': True, 'shifted_count': shifted}

    def split(self, block_id, keep_ids, settings):
        block = self.commands.get_block(block_id)
        if block is None:
            raise CompactBlockApiError('블록을 찾을 수 없습니다.', 404)
        if not keep_ids:
            raise CompactBlockApiError('유지할 식별자를 선택해주세요.')
        task_id = block.get('task_id')
        if not task_id:
            raise CompactBlockApiError('간단 블록은 분리할 수 없습니다.')

        details = self._block_attempt_details(block_id)
        if not details:
            raise CompactBlockApiError('연결된 시험 항목을 찾을 수 없습니다.', 404)

        keep_set = set(keep_ids)
        keep_details = [item for item in details if item['identifier_id'] in keep_set]
        split_details = [item for item in details if item['identifier_id'] not in keep_set]
        if not keep_details:
            raise CompactBlockApiError('유지할 식별자를 선택해주세요.')
        if not split_details:
            raise CompactBlockApiError('분리할 식별자가 없습니다.')

        adjusted_end = _end_after_minutes(
            block['start_time'],
            _sum_minutes(keep_details),
            settings,
        )
        split_start = adjusted_end
        split_adjusted_end = _end_after_minutes(
            split_start,
            _sum_minutes(split_details),
            settings,
        )
        overlap = self._check_overlap(
            block['date'],
            split_start,
            split_adjusted_end,
            block.get('location_id', ''),
            exclude_block_id=block_id,
        )
        if overlap:
            raise CompactBlockApiError('분리된 블록이 다른 블록과 시간이 겹칩니다.', 409)

        self.commands.update_block(block_id, end_time=adjusted_end)
        self.commands.replace_block_items(block_id, [item['attempt_id'] for item in keep_details])
        new_block = self.commands.create_block(
            date=block['date'],
            start_time=split_start,
            end_time=split_adjusted_end,
            location_id=block.get('location_id', ''),
            assignee_names=block.get('assignee_names', []),
            kind=block.get('kind', 'test'),
            title=block.get('title', ''),
            memo=block.get('memo', ''),
            is_locked=block.get('is_locked', False),
            manual_status=block.get('manual_status', ''),
            exam_attempt_ids=[item['attempt_id'] for item in split_details],
        )
        return {'success': True, 'new_block': _api_block(new_block)}

    def return_identifiers(self, block_id, keep_ids, settings):
        block = self.commands.get_block(block_id)
        if block is None:
            raise CompactBlockApiError('블록을 찾을 수 없습니다.', 404)
        if not keep_ids:
            self.commands.delete_block(block_id)
            return {'success': True}

        details = self._block_attempt_details(block_id)
        keep_set = set(keep_ids)
        keep_details = [item for item in details if item['identifier_id'] in keep_set]
        if not keep_details:
            self.commands.delete_block(block_id)
            return {'success': True}

        adjusted_end = _end_after_minutes(
            block['start_time'],
            _sum_minutes(keep_details),
            settings,
        )
        self.commands.update_block(block_id, end_time=adjusted_end)
        self.commands.replace_block_items(block_id, [item['attempt_id'] for item in keep_details])
        return {'success': True}

    def _replace_identifiers(self, block_id, block, identifier_ids):
        task_id = block.get('task_id') if block else None
        if not task_id:
            raise CompactBlockApiError('간단 블록에는 identifier_ids를 설정할 수 없습니다.')
        try:
            attempt_ids = self.commands.attempt_ids_for_legacy_task(task_id, identifier_ids)
            self._require_attempts(attempt_ids)
            self.commands.replace_block_items(block_id, attempt_ids)
        except ValueError as exc:
            raise CompactBlockApiError(str(exc)) from exc

    @staticmethod
    def _require(data, fields):
        for field in fields:
            if not data.get(field):
                raise CompactBlockApiError(f'{field}은(는) 필수 항목입니다.')

    @staticmethod
    def _require_attempts(attempt_ids):
        if not attempt_ids:
            raise CompactBlockApiError('연결할 시험 항목을 찾을 수 없습니다.')

    def _block_attempt_details(self, block_id):
        with self.commands.session_factory() as session:
            rows = (
                session.query(BlockItem, ExamAttempt, TestItem)
                .join(ExamAttempt, BlockItem.exam_attempt_id == ExamAttempt.id)
                .join(TestItem, ExamAttempt.test_item_id == TestItem.id)
                .filter(BlockItem.block_id == block_id)
                .order_by(BlockItem.sort_order, BlockItem.id)
            )
            return [
                {
                    'attempt_id': attempt.id,
                    'identifier_id': attempt.legacy_identifier_id,
                    'estimated_minutes': test_item.estimated_minutes,
                }
                for _block_item, attempt, test_item in rows
            ]

    def _check_overlap(self, date_str, start_time, end_time, location_id, exclude_block_id=None):
        if not location_id:
            return None
        start_min = time_to_minutes(start_time)
        end_min = time_to_minutes(end_time)
        with self.commands.session_factory() as session:
            blocks = (
                session.query(ScheduleBlock)
                .filter_by(date=date_str, location_id=location_id)
                .order_by(ScheduleBlock.start_time, ScheduleBlock.id)
            )
            for block in blocks:
                if exclude_block_id and block.id == exclude_block_id:
                    continue
                if start_min < time_to_minutes(block.end_time) and time_to_minutes(block.start_time) < end_min:
                    return _api_block(self.commands.get_block(block.id))
        return None


def _api_block(block):
    data = dict(block)
    data['block_status'] = data.get('manual_status') or data.get('block_status') or 'pending'
    data['is_simple'] = data.get('kind') == 'simple'
    return data


def _sum_minutes(items):
    return sum(int(item.get('estimated_minutes') or 0) for item in items)


def _end_after_minutes(start_time, minutes, settings):
    raw_end = minutes_to_time(time_to_minutes(start_time) + max(minutes, 1))
    return adjust_end_for_breaks(start_time, raw_end, settings)
