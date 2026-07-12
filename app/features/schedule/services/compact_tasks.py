"""Task API commands backed by compact ORM catalog tables."""

from app.db import Base, create_session_factory, session_scope
from app.db.models import (
    BlockItem,
    ExamAttempt,
    ExecutionRun,
    ScheduleBlock,
    SourceDocument,
    TestItem,
)
from app.domain.ids import stable_id


class CompactTaskError(Exception):
    """Error that can be returned by task routes."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class CompactTaskCommandService:
    """Create, update, and delete catalog task projections directly in ORM."""

    def __init__(self, database_url, session_factory=None, engine=None):
        if session_factory is None:
            session_factory, engine = create_session_factory(database_url)
        self.session_factory = session_factory
        self.engine = engine
        Base.metadata.create_all(self.engine)

    def create_task(self, data):
        task_id = data.get('id') or _new_task_id(data)
        exam_no = data.get('exam_no')
        identifiers = _normal_identifiers(data.get('identifiers', []))
        self._validate_duplicate_identifiers(identifiers, exam_no)
        with session_scope(self.session_factory) as session:
            document = _upsert_document(session, task_id, data)
            attempts = _replace_attempts(session, document, task_id, data, identifiers)
            return _task_dict(document, attempts, data)

    def update_task(self, task_id, data):
        current = self.get_task(task_id)
        if current is None:
            raise CompactTaskError('시험 항목을 찾을 수 없습니다.', 404)
        merged = {**current, **data, 'id': task_id}
        identifiers = _normal_identifiers(merged.get('identifiers', []))
        exam_no = merged.get('exam_no')
        self._validate_duplicate_identifiers(identifiers, exam_no, exclude_task_id=task_id)
        with session_scope(self.session_factory) as session:
            _delete_attempts_for_task(session, task_id)
            document = _upsert_document(session, task_id, merged)
            attempts = _replace_attempts(session, document, task_id, merged, identifiers)
            return _task_dict(document, attempts, merged)

    def delete_task(self, task_id):
        if self.get_task(task_id) is None:
            raise CompactTaskError('시험 항목을 찾을 수 없습니다.', 404)
        with session_scope(self.session_factory) as session:
            _delete_attempts_for_task(session, task_id)
            for document in session.query(SourceDocument):
                legacy_ids = list(document.legacy_task_ids or [])
                if task_id in legacy_ids:
                    legacy_ids = [item for item in legacy_ids if item != task_id]
                    if legacy_ids:
                        document.legacy_task_ids = legacy_ids
                    else:
                        _delete_document_if_orphan(session, document.id)
        return True

    def get_task(self, task_id):
        with self.session_factory() as session:
            attempts = list(
                session.query(ExamAttempt)
                .filter_by(legacy_task_id=task_id)
                .order_by(ExamAttempt.legacy_identifier_id, ExamAttempt.id)
            )
            if not attempts:
                return None
            for attempt in attempts:
                attempt._test_item_cache = session.get(TestItem, attempt.test_item_id)
            test_item = session.get(TestItem, attempts[0].test_item_id)
            document = session.get(SourceDocument, test_item.document_id) if test_item else None
            if document is None:
                return None
            return _task_dict(document, attempts, _attempt_defaults(attempts[0]))

    def _validate_duplicate_identifiers(self, identifiers, exam_no, exclude_task_id=None):
        new_ids = [item['id'] for item in identifiers if item.get('id')]
        if not new_ids:
            return
        with self.session_factory() as session:
            rows = (
                session.query(ExamAttempt)
                .filter(ExamAttempt.exam_no == exam_no)
                .filter(ExamAttempt.legacy_identifier_id.in_(new_ids))
            )
            duplicates = []
            for attempt in rows:
                if exclude_task_id and attempt.legacy_task_id == exclude_task_id:
                    continue
                duplicates.append(attempt.legacy_identifier_id)
            if duplicates:
                raise CompactTaskError(f'중복된 식별자: {", ".join(sorted(set(duplicates)))}')


def _upsert_document(session, task_id, data):
    document_id = _document_id(data)
    document = session.get(SourceDocument, document_id)
    legacy_ids = [task_id]
    if document and document.legacy_task_ids:
        legacy_ids = list(document.legacy_task_ids)
        if task_id not in legacy_ids:
            legacy_ids.append(task_id)
    fields = {
        'id': document_id,
        'legacy_task_ids': legacy_ids,
        'external_doc_id': _external_doc_id(data.get('doc_id')),
        'version_id': data.get('version_id', ''),
        'doc_name': data.get('doc_name', ''),
        'is_active': data.get('status') != 'cancelled',
    }
    if document is None:
        document = SourceDocument(**fields)
        session.add(document)
    else:
        for key, value in fields.items():
            setattr(document, key, value)
    return document


def _replace_attempts(session, document, task_id, data, identifiers):
    attempts = []
    for identifier in identifiers:
        test_item_id = stable_id('ti_', document.id, identifier['id'])
        test_item = session.get(TestItem, test_item_id)
        test_fields = {
            'id': test_item_id,
            'document_id': document.id,
            'external_test_id': identifier['id'],
            'name': identifier.get('name', ''),
            'estimated_minutes': int(identifier.get('estimated_minutes') or 0),
            'total_count': _identifier_total_count(identifier),
            'owner_names': list(identifier.get('owners') or identifier.get('owner_names') or []),
            'is_active': True,
        }
        if test_item is None:
            test_item = TestItem(**test_fields)
            session.add(test_item)
        else:
            for key, value in test_fields.items():
                setattr(test_item, key, value)

        attempt = ExamAttempt(
            id=_attempt_id(document.id, identifier['id'], data.get('exam_no')),
            test_item_id=test_item_id,
            exam_no=data.get('exam_no'),
            legacy_task_id=task_id,
            legacy_identifier_id=identifier['id'],
            default_location_id=data.get('location_id', ''),
            default_assignee_names=list(data.get('assignee_names', [])),
            memo=data.get('memo', ''),
            state='cancelled' if data.get('status') == 'cancelled' else 'active',
        )
        session.add(attempt)
        attempt._test_item_cache = test_item
        attempts.append(attempt)
    return attempts


def _delete_attempts_for_task(session, task_id):
    attempts = list(session.query(ExamAttempt).filter_by(legacy_task_id=task_id))
    attempt_ids = [item.id for item in attempts]
    test_item_ids = [item.test_item_id for item in attempts]
    if attempt_ids:
        session.query(BlockItem).filter(BlockItem.exam_attempt_id.in_(attempt_ids)).delete(synchronize_session=False)
        session.query(ExecutionRun).filter(ExecutionRun.exam_attempt_id.in_(attempt_ids)).delete(synchronize_session=False)
        session.query(ExamAttempt).filter(ExamAttempt.id.in_(attempt_ids)).delete(synchronize_session=False)
    for test_item_id in test_item_ids:
        if session.query(ExamAttempt).filter_by(test_item_id=test_item_id).count() == 0:
            test_item = session.get(TestItem, test_item_id)
            if test_item is not None:
                document_id = test_item.document_id
                session.delete(test_item)
                _delete_document_if_orphan(session, document_id)
    _delete_empty_blocks(session)


def _delete_empty_blocks(session):
    block_ids_with_items = {
        item[0]
        for item in session.query(BlockItem.block_id).distinct()
    }
    for block in session.query(ScheduleBlock).filter_by(kind='test'):
        if block.id not in block_ids_with_items:
            session.delete(block)


def _delete_document_if_orphan(session, document_id):
    if session.query(TestItem).filter_by(document_id=document_id).count() > 0:
        return
    document = session.get(SourceDocument, document_id)
    if document is not None:
        session.delete(document)


def _task_dict(document, attempts, defaults):
    attempts = list(attempts)
    identifiers = []
    estimated_minutes = 0
    for attempt in attempts:
        # In-session access for fresh rows, detached get for loaded rows.
        test_item = getattr(attempt, '_test_item_cache', None)
        identifiers.append({
            'id': attempt.legacy_identifier_id,
            'name': getattr(test_item, 'name', '') if test_item else '',
            'estimated_minutes': getattr(test_item, 'estimated_minutes', 0) if test_item else 0,
            'total_count': getattr(test_item, 'total_count', 0) if test_item else 0,
            'owners': list(getattr(test_item, 'owner_names', []) or []) if test_item else [],
        })
    if not identifiers:
        identifiers = defaults.get('identifiers', [])
    estimated_minutes = sum(int(item.get('estimated_minutes') or 0) for item in identifiers)
    return {
        'id': defaults.get('id') or (attempts[0].legacy_task_id if attempts else ''),
        'doc_id': document.external_doc_id,
        'version_id': document.version_id,
        'exam_no': defaults.get('exam_no') if 'exam_no' in defaults else (attempts[0].exam_no if attempts else None),
        'assignee_names': list(defaults.get('assignee_names') or (attempts[0].default_assignee_names if attempts else [])),
        'location_id': defaults.get('location_id') or (attempts[0].default_location_id if attempts else ''),
        'doc_name': document.doc_name,
        'identifiers': identifiers,
        'estimated_minutes': estimated_minutes,
        'remaining_minutes': defaults.get('remaining_minutes', estimated_minutes),
        'memo': defaults.get('memo') or (attempts[0].memo if attempts else ''),
        'status': defaults.get('status', 'pending'),
    }


def _attempt_defaults(attempt):
    return {
        'id': attempt.legacy_task_id,
        'exam_no': attempt.exam_no,
        'assignee_names': list(attempt.default_assignee_names or []),
        'location_id': attempt.default_location_id,
        'memo': attempt.memo,
        'status': 'cancelled' if attempt.state == 'cancelled' else 'pending',
    }


def _normal_identifiers(identifiers):
    result = []
    for item in identifiers or []:
        if isinstance(item, dict):
            identifier_id = item.get('id', '')
            if identifier_id:
                result.append({**item, 'id': identifier_id})
        elif item:
            result.append({'id': str(item), 'name': '', 'estimated_minutes': 0})
    return result


def _identifier_total_count(identifier):
    for key in ('total_count', 'pf_num', 'test_count', 'case_count', 'count'):
        value = identifier.get(key)
        if value in (None, ''):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _document_id(data):
    return stable_id('doc_', data.get('version_id', ''), _external_doc_id(data.get('doc_id')))


def _attempt_id(document_id, identifier_id, exam_no):
    return stable_id('ea_', stable_id('ti_', document_id, identifier_id), exam_no)


def _new_task_id(data):
    return stable_id('t_', data.get('version_id', ''), data.get('doc_id'), data.get('exam_no'))


def _external_doc_id(value):
    if value in (None, ''):
        return None
    return str(value)
