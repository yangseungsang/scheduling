"""Read models built from compact domain snapshots."""

from datetime import datetime


def build_execution_list_items(snapshot, date_filter='', location_filter=''):
    """Return execution list rows from a compact snapshot."""
    indexes = _indexes(snapshot)
    scheduled = _scheduled_maps(snapshot, indexes)
    rows = []

    for attempt in snapshot.get('catalog', {}).get('exam_attempts', []):
        attempt_id = attempt['id']
        test_item = indexes['test_items'].get(attempt.get('test_item_id'), {})
        document = indexes['documents'].get(test_item.get('document_id'), {})
        run = indexes['runs_by_attempt'].get(attempt_id)
        scheduled_info = scheduled.get(attempt_id, {})

        scheduled_date = scheduled_info.get('scheduled_date', '')
        location_id = (
            scheduled_info.get('location_id')
            or attempt.get('default_location_id', '')
        )
        if date_filter and scheduled_date != date_filter:
            continue
        if location_filter and location_id != location_filter:
            continue

        location = indexes['locations'].get(location_id, {})
        status = run.get('status') if run else 'pending'
        elapsed_seconds = _elapsed_seconds(run.get('segments', [])) if run else 0
        doc_name = document.get('doc_name', '')
        exam_no = attempt.get('exam_no')

        rows.append({
            'exam_attempt_id': attempt_id,
            'document_id': document.get('id', ''),
            'doc_name': doc_name,
            'display_name': _display_name(doc_name, exam_no),
            'external_doc_id': document.get('external_doc_id'),
            'external_test_id': test_item.get('external_test_id', ''),
            'test_name': test_item.get('name', ''),
            'exam_no': exam_no,
            'owner_names': list(test_item.get('owner_names', [])),
            'estimated_minutes': test_item.get('estimated_minutes', 0),
            'total_count': (run or {}).get('total_count', test_item.get('total_count', 0)),
            'scheduled_date': scheduled_date,
            'location_id': location_id,
            'location_name': location.get('name', ''),
            'execution_status': status,
            'performer_name': (run or {}).get('performer_name', ''),
            'fail_count': (run or {}).get('fail_count', 0),
            'block_count': (run or {}).get('block_count', 0),
            'pass_count': (run or {}).get('pass_count', 0),
            'elapsed_seconds': elapsed_seconds,
            'comment': (run or {}).get('comment', ''),
        })

    return sorted(rows, key=lambda row: (
        row.get('scheduled_date') or '9999-99-99',
        row.get('location_name', ''),
        row.get('doc_name', ''),
        row.get('external_test_id', ''),
        row.get('exam_no') if row.get('exam_no') is not None else -1,
    ))


def build_unscheduled_attempts(snapshot):
    """Return queue rows for attempts not fully scheduled."""
    indexes = _indexes(snapshot)
    scheduled_attempt_ids = {
        item.get('exam_attempt_id')
        for item in snapshot.get('schedule', {}).get('block_items', [])
    }
    rows = []

    for attempt in snapshot.get('catalog', {}).get('exam_attempts', []):
        attempt_id = attempt['id']
        if attempt.get('state') == 'cancelled':
            continue
        if attempt_id in scheduled_attempt_ids:
            continue

        run = indexes['runs_by_attempt'].get(attempt_id)
        if run and run.get('status') == 'completed':
            continue

        test_item = indexes['test_items'].get(attempt.get('test_item_id'), {})
        if test_item.get('estimated_minutes', 0) <= 0:
            continue
        document = indexes['documents'].get(test_item.get('document_id'), {})
        doc_name = document.get('doc_name', '')
        exam_no = attempt.get('exam_no')
        rows.append({
            'exam_attempt_id': attempt_id,
            'doc_name': doc_name,
            'display_name': _display_name(doc_name, exam_no),
            'external_test_id': test_item.get('external_test_id', ''),
            'test_name': test_item.get('name', ''),
            'exam_no': exam_no,
            'remaining_minutes': test_item.get('estimated_minutes', 0),
            'default_location_id': attempt.get('default_location_id', ''),
            'owner_names': list(test_item.get('owner_names', [])),
            'execution_status': run.get('status') if run else 'pending',
        })

    return sorted(rows, key=lambda row: (
        row.get('doc_name', ''),
        row.get('exam_no') if row.get('exam_no') is not None else -1,
        row.get('external_test_id', ''),
    ))


def build_schedule_export_rows(snapshot, start_date='', end_date=''):
    """Return schedule export rows from a compact snapshot."""
    indexes = _indexes(snapshot)
    block_items_by_block = {}
    for item in snapshot.get('schedule', {}).get('block_items', []):
        block_items_by_block.setdefault(item.get('block_id'), []).append(item)

    rows = []
    for block in snapshot.get('schedule', {}).get('blocks', []):
        block_date = block.get('date', '')
        if start_date and block_date < start_date:
            continue
        if end_date and block_date > end_date:
            continue

        items = sorted(
            block_items_by_block.get(block.get('id'), []),
            key=lambda item: item.get('sort_order', 0),
        )
        attempts = [
            indexes['attempts'].get(item.get('exam_attempt_id'), {})
            for item in items
        ]
        test_items = [
            indexes['test_items'].get(attempt.get('test_item_id'), {})
            for attempt in attempts
        ]
        documents = [
            indexes['documents'].get(test_item.get('document_id'), {})
            for test_item in test_items
        ]
        location = indexes['locations'].get(block.get('location_id'), {})
        status = _block_status(block, attempts, indexes['runs_by_attempt'])
        doc_names = _unique([doc.get('doc_name', '') for doc in documents if doc])
        test_ids = _unique([
            test_item.get('external_test_id', '')
            for test_item in test_items
            if test_item
        ])

        rows.append({
            'block_id': block.get('id'),
            'legacy_block_id': block.get('legacy_block_id', ''),
            'date': block_date,
            'start_time': block.get('start_time', ''),
            'end_time': block.get('end_time', ''),
            'location_id': block.get('location_id', ''),
            'location_name': location.get('name', ''),
            'assignee_names': list(block.get('assignee_names', [])),
            'kind': block.get('kind', 'test'),
            'title': block.get('title', ''),
            'doc_name': ', '.join(doc_names) if doc_names else block.get('title', ''),
            'external_test_ids': test_ids,
            'split_label': _split_label(attempts, documents, indexes),
            'execution_status': status,
            'memo': block.get('memo', ''),
        })

    return sorted(rows, key=lambda row: (
        row.get('date', ''),
        row.get('location_name', ''),
        row.get('start_time', ''),
        row.get('end_time', ''),
    ))


def _indexes(snapshot):
    catalog = snapshot.get('catalog', {})
    resources = snapshot.get('resources', {})
    executions = snapshot.get('executions', {})
    attempts = {
        item['id']: item
        for item in catalog.get('exam_attempts', [])
    }
    runs_by_attempt = {}
    for run in executions.get('runs', []):
        runs_by_attempt[run.get('exam_attempt_id')] = run
    return {
        'documents': {item['id']: item for item in catalog.get('documents', [])},
        'test_items': {item['id']: item for item in catalog.get('test_items', [])},
        'attempts': attempts,
        'runs_by_attempt': runs_by_attempt,
        'locations': {item['id']: item for item in resources.get('locations', [])},
    }


def _scheduled_maps(snapshot, indexes):
    blocks = {
        block['id']: block
        for block in snapshot.get('schedule', {}).get('blocks', [])
    }
    result = {}
    for item in snapshot.get('schedule', {}).get('block_items', []):
        attempt_id = item.get('exam_attempt_id')
        block = blocks.get(item.get('block_id'), {})
        if not attempt_id or not block:
            continue
        current = result.get(attempt_id)
        block_date = block.get('date', '')
        if current is None or block_date < current.get('scheduled_date', ''):
            result[attempt_id] = {
                'scheduled_date': block_date,
                'location_id': block.get('location_id', ''),
            }
    return result


def _elapsed_seconds(segments):
    total = 0
    now = datetime.now()
    for segment in segments or []:
        start = segment.get('start')
        if not start:
            continue
        end = segment.get('end')
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end) if end else now
        except (TypeError, ValueError):
            continue
        total += int((end_dt - start_dt).total_seconds())
    return max(0, total)


def _display_name(doc_name, exam_no):
    if exam_no is not None and exam_no != 1:
        return f'{doc_name} ({exam_no}차)'
    return doc_name


def _block_status(block, attempts, runs_by_attempt):
    if block.get('manual_status') == 'cancelled':
        return 'cancelled'
    if block.get('kind') == 'simple':
        return 'pending'
    statuses = []
    for attempt in attempts:
        if not attempt:
            continue
        run = runs_by_attempt.get(attempt.get('id'))
        statuses.append(run.get('status', 'pending') if run else 'pending')
    if statuses and all(status == 'completed' for status in statuses):
        return 'completed'
    if any(status in ('in_progress', 'paused', 'completed') for status in statuses):
        return 'in_progress'
    return 'pending'


def _split_label(attempts, documents, indexes):
    if not attempts:
        return ''
    doc_ids = {
        doc.get('id')
        for doc in documents
        if doc and doc.get('id')
    }
    if len(doc_ids) != 1:
        return ''
    doc_id = next(iter(doc_ids))
    all_attempts = [
        attempt for attempt in indexes['attempts'].values()
        if indexes['test_items'].get(attempt.get('test_item_id'), {}).get('document_id') == doc_id
    ]
    if len(attempts) == len(all_attempts):
        return ''
    return f'{len(attempts)}/{len(all_attempts)}'


def _unique(values):
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
