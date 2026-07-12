"""Commands that write schedule data directly to compact ORM tables."""

import uuid

from app.db import Base, create_session_factory, session_scope
from app.db.models import BlockItem, ExamAttempt, ScheduleBlock
from app.domain.ids import stable_id

BLOCK_FIELDS = {
    'date',
    'start_time',
    'end_time',
    'location_id',
    'assignee_names',
    'kind',
    'title',
    'memo',
    'is_locked',
    'manual_status',
    'overflow_minutes',
}


class CompactScheduleCommandService:
    """Write schedule blocks directly against the compact ORM schema."""

    def __init__(self, database_url, session_factory=None, engine=None):
        if session_factory is None:
            session_factory, engine = create_session_factory(database_url)
        self.session_factory = session_factory
        self.engine = engine
        Base.metadata.create_all(self.engine)

    def get_block(self, block_id):
        """Return one block with legacy task/identifier references for API callers."""
        with self.session_factory() as session:
            block = session.get(ScheduleBlock, block_id)
            if block is None:
                return None
            return _block_with_legacy_refs(session, block)

    def attempt_ids_for_legacy_task(self, task_id, identifier_ids=None):
        """Resolve legacy task/identifier references to compact exam attempt ids."""
        with self.session_factory() as session:
            attempts = list(
                session.query(ExamAttempt)
                .filter_by(legacy_task_id=task_id)
                .order_by(ExamAttempt.exam_no, ExamAttempt.legacy_identifier_id, ExamAttempt.id)
            )
            if identifier_ids is None:
                return [item.id for item in attempts]
            by_identifier = {
                item.legacy_identifier_id: item.id
                for item in attempts
                if item.legacy_identifier_id
            }
            missing = [
                identifier_id
                for identifier_id in identifier_ids
                if identifier_id not in by_identifier
            ]
            if missing:
                raise ValueError(f'exam_attempt not found for identifiers: {", ".join(missing)}')
            return [by_identifier[identifier_id] for identifier_id in identifier_ids]

    def create_block(
        self,
        *,
        date,
        start_time,
        end_time,
        location_id='',
        assignee_names=None,
        kind='test',
        title='',
        memo='',
        is_locked=False,
        manual_status='',
        overflow_minutes=0,
        exam_attempt_ids=None,
        block_id='',
        legacy_block_id='',
    ):
        """Create one compact schedule block and optional block items."""
        block_id = block_id or _new_block_id(legacy_block_id)
        exam_attempt_ids = list(exam_attempt_ids or [])
        with session_scope(self.session_factory) as session:
            if session.get(ScheduleBlock, block_id):
                raise ValueError(f'block already exists: {block_id}')
            _validate_attempts(session, exam_attempt_ids)
            block = ScheduleBlock(
                id=block_id,
                legacy_block_id=legacy_block_id,
                date=date,
                start_time=start_time,
                end_time=end_time,
                location_id=location_id,
                assignee_names=list(assignee_names or []),
                kind=kind,
                title=title,
                memo=memo,
                is_locked=bool(is_locked),
                manual_status=manual_status,
                overflow_minutes=int(overflow_minutes or 0),
            )
            session.add(block)
            _replace_items(session, block_id, exam_attempt_ids)
            return _block_with_legacy_refs(session, block)

    def update_block(self, block_id, **fields):
        """Patch allowed fields on one compact schedule block."""
        updates = {key: value for key, value in fields.items() if key in BLOCK_FIELDS}
        with session_scope(self.session_factory) as session:
            block = session.get(ScheduleBlock, block_id)
            if block is None:
                return None
            for key, value in updates.items():
                if key == 'assignee_names':
                    value = list(value or [])
                if key == 'is_locked':
                    value = bool(value)
                if key == 'overflow_minutes':
                    value = int(value or 0)
                setattr(block, key, value)
            return _block_with_legacy_refs(session, block)

    def replace_block_items(self, block_id, exam_attempt_ids):
        """Replace the attempt assignments for one compact schedule block."""
        exam_attempt_ids = list(exam_attempt_ids or [])
        with session_scope(self.session_factory) as session:
            if session.get(ScheduleBlock, block_id) is None:
                return None
            _validate_attempts(session, exam_attempt_ids)
            _replace_items(session, block_id, exam_attempt_ids)
            return [
                {
                    'id': stable_id('bi_', block_id, attempt_id),
                    'block_id': block_id,
                    'exam_attempt_id': attempt_id,
                    'sort_order': index,
                }
                for index, attempt_id in enumerate(exam_attempt_ids)
            ]

    def delete_block(self, block_id):
        """Delete one compact schedule block and its block items."""
        with session_scope(self.session_factory) as session:
            block = session.get(ScheduleBlock, block_id)
            if block is None:
                return False
            session.query(BlockItem).filter_by(block_id=block_id).delete()
            session.delete(block)
            return True


def _replace_items(session, block_id, exam_attempt_ids):
    session.query(BlockItem).filter_by(block_id=block_id).delete()
    for index, attempt_id in enumerate(exam_attempt_ids):
        session.add(BlockItem(
            id=stable_id('bi_', block_id, attempt_id),
            block_id=block_id,
            exam_attempt_id=attempt_id,
            sort_order=index,
        ))


def _validate_attempts(session, exam_attempt_ids):
    if not exam_attempt_ids:
        return
    existing = {
        item.id
        for item in session.query(ExamAttempt)
        .filter(ExamAttempt.id.in_(exam_attempt_ids))
    }
    missing = sorted(set(exam_attempt_ids) - existing)
    if missing:
        raise ValueError(f'exam_attempt not found: {", ".join(missing)}')


def _block_with_legacy_refs(session, block):
    data = _block_dict(block)
    items = list(
        session.query(BlockItem, ExamAttempt)
        .join(ExamAttempt, BlockItem.exam_attempt_id == ExamAttempt.id)
        .filter(BlockItem.block_id == block.id)
        .order_by(BlockItem.sort_order, BlockItem.id)
    )
    task_ids = [
        attempt.legacy_task_id
        for _, attempt in items
        if attempt.legacy_task_id
    ]
    identifier_ids = [
        attempt.legacy_identifier_id
        for _, attempt in items
        if attempt.legacy_identifier_id
    ]
    data['task_id'] = task_ids[0] if task_ids else None
    data['identifier_ids'] = identifier_ids
    data['block_status'] = data.get('manual_status') or 'pending'
    data['is_simple'] = data.get('kind') == 'simple'
    return data


def _new_block_id(legacy_block_id):
    if legacy_block_id:
        return stable_id('blk_', legacy_block_id)
    return f'blk_{uuid.uuid4().hex[:12]}'


def _block_dict(block):
    return {
        'id': block.id,
        'legacy_block_id': block.legacy_block_id,
        'date': block.date,
        'start_time': block.start_time,
        'end_time': block.end_time,
        'location_id': block.location_id,
        'assignee_names': list(block.assignee_names or []),
        'kind': block.kind,
        'title': block.title,
        'memo': block.memo,
        'is_locked': bool(block.is_locked),
        'manual_status': block.manual_status,
        'overflow_minutes': int(block.overflow_minutes or 0),
    }
