"""Read adapters for schedule UI/API responses backed by compact snapshots."""

from app.features.schedule.helpers.enrichment import STATUS_COLORS, _section_color
from app.services.read_models import build_schedule_export_rows


def build_compact_day_payload(snapshot, current_date, settings, time_slots, break_slots):
    """Build the `/schedule/api/day` response from a compact snapshot."""
    blocks = build_compact_ui_blocks(snapshot, current_date, current_date, settings)
    return {
        'blocks': blocks,
        'time_slots': time_slots,
        'break_slots': break_slots,
        'settings': settings,
        'queue_tasks': build_compact_queue_tasks(snapshot),
    }


def compact_schedule_settings(settings):
    """Return UI-safe schedule settings with defaults for compact snapshots."""
    result = {
        'work_start': '08:00',
        'work_end': '17:00',
        'actual_work_start': '',
        'actual_work_end': '',
        'lunch_start': '12:00',
        'lunch_end': '13:00',
        'breaks': [],
        'grid_interval_minutes': 15,
        'max_schedule_days': 14,
        'block_color_by': 'assignee',
    }
    result.update(settings or {})
    return result


def build_compact_export_blocks(snapshot, start_date, end_date):
    """Return export-service compatible block dictionaries from compact rows."""
    rows = build_schedule_export_rows(snapshot, start_date, end_date)
    blocks = []
    for row in rows:
        identifiers = [
            {'id': identifier_id, 'name': '', 'estimated_minutes': 0}
            for identifier_id in row.get('external_test_ids', [])
        ]
        split_label = row.get('split_label', '')
        block = {
            'id': row.get('block_id'),
            'date': row.get('date', ''),
            'start_time': row.get('start_time', ''),
            'end_time': row.get('end_time', ''),
            'location_id': row.get('location_id', ''),
            'location_name': row.get('location_name', ''),
            'assignee_names': list(row.get('assignee_names', [])),
            'kind': row.get('kind', 'test'),
            'title': row.get('title', ''),
            'doc_name': row.get('doc_name', ''),
            'display_name': row.get('doc_name', ''),
            'task_title': row.get('doc_name', ''),
            'identifiers': identifiers,
            'identifier_ids': [item['id'] for item in identifiers],
            'block_status': row.get('execution_status', 'pending'),
            'memo': row.get('memo', ''),
            'color': STATUS_COLORS.get(row.get('execution_status'), STATUS_COLORS['pending']),
            'is_simple': row.get('kind') == 'simple',
            'is_split': bool(split_label),
        }
        if split_label and '/' in split_label:
            current, total = split_label.split('/', 1)
            block['block_identifier_count'] = current
            block['total_identifier_count'] = total
        blocks.append(block)
    return blocks


def build_compact_ui_blocks(snapshot, start_date='', end_date='', settings=None):
    """Return calendar UI block dictionaries from a compact snapshot."""
    settings = settings or {}
    indexes = _indexes(snapshot)
    all_task_attempts = _attempts_by_legacy_task(snapshot)
    block_items = _block_items_by_block(snapshot)
    placed_ids_by_task = _placed_identifier_ids_by_task(snapshot, indexes)
    color_by = settings.get('block_color_by', 'assignee')
    blocks = []

    for block in snapshot.get('schedule', {}).get('blocks', []):
        block_date = block.get('date', '')
        if start_date and block_date < start_date:
            continue
        if end_date and block_date > end_date:
            continue

        items = block_items.get(block.get('id'), [])
        attempts = [
            indexes['attempts'].get(item.get('exam_attempt_id'), {})
            for item in items
        ]
        attempts = [item for item in attempts if item]
        test_items = [
            indexes['test_items'].get(attempt.get('test_item_id'), {})
            for attempt in attempts
        ]
        docs = [
            indexes['documents'].get(test_item.get('document_id'), {})
            for test_item in test_items
        ]
        location = indexes['locations'].get(block.get('location_id'), {})
        task_id = attempts[0].get('legacy_task_id') if attempts else None
        task_attempts = all_task_attempts.get(task_id, []) if task_id else []
        identifiers = _identifier_dicts(task_attempts, indexes)
        selected_identifier_ids = [
            attempt.get('legacy_identifier_id')
            for attempt in attempts
            if attempt.get('legacy_identifier_id')
        ]
        doc_name = _first([doc.get('doc_name', '') for doc in docs]) or block.get('title', '')
        exam_no = attempts[0].get('exam_no') if attempts else None
        status = _block_status(block, attempts, indexes['runs_by_attempt'])
        assignee_names = list(block.get('assignee_names', []))

        ui_block = {
            'id': block.get('id'),
            'legacy_block_id': block.get('legacy_block_id', ''),
            'task_id': task_id,
            'date': block_date,
            'start_time': block.get('start_time', ''),
            'end_time': block.get('end_time', ''),
            'location_id': block.get('location_id', ''),
            'location_name': location.get('name', ''),
            'location_color': location.get('color', '#6c757d'),
            'assignee_names': assignee_names,
            'assignee_name': ', '.join(assignee_names) if assignee_names else '(미배정)',
            'assignee_color': _assignee_color(assignee_names, indexes['users']),
            'doc_id': _first([doc.get('external_doc_id', '') for doc in docs]) or '',
            'doc_name': doc_name,
            'task_title': block.get('title', '') if block.get('kind') == 'simple' else doc_name,
            'display_name': _display_name(doc_name, exam_no),
            'exam_no': exam_no,
            'identifiers': identifiers,
            'identifier_ids': selected_identifier_ids,
            'is_simple': block.get('kind') == 'simple',
            'title': block.get('title', ''),
            'memo': block.get('memo', ''),
            'block_status': status,
            'is_locked': bool(block.get('is_locked')),
            'section_color': _section_color(doc_name),
            'estimated_minutes': sum(
                int(test_item.get('estimated_minutes') or 0)
                for test_item in test_items
            ),
        }
        total_count = len(task_attempts)
        ui_block['total_identifier_count'] = total_count
        ui_block['block_identifier_count'] = len(selected_identifier_ids)
        ui_block['is_split'] = bool(total_count and len(selected_identifier_ids) < total_count)
        if ui_block['is_split'] and task_id:
            all_ids = {
                attempt.get('legacy_identifier_id')
                for attempt in task_attempts
                if attempt.get('legacy_identifier_id')
            }
            unplaced = all_ids - placed_ids_by_task.get(task_id, set())
            ui_block['split_status'] = 'partial' if unplaced else 'split'
        else:
            ui_block['split_status'] = ''
        ui_block['color'] = _block_color(ui_block, color_by)
        blocks.append(ui_block)

    return sorted(blocks, key=lambda item: (item.get('date', ''), item.get('start_time', ''), item.get('id', '')))


def build_compact_queue_tasks(snapshot):
    """Return task-queue compatible dictionaries from unscheduled compact attempts."""
    indexes = _indexes(snapshot)
    scheduled_attempt_ids = {
        item.get('exam_attempt_id')
        for item in snapshot.get('schedule', {}).get('block_items', [])
    }
    attempts_by_task = _attempts_by_legacy_task(snapshot)
    queue = []

    for task_id, attempts in attempts_by_task.items():
        unscheduled = []
        for attempt in attempts:
            if attempt.get('state') == 'cancelled':
                continue
            if attempt.get('id') in scheduled_attempt_ids:
                continue
            run = indexes['runs_by_attempt'].get(attempt.get('id'))
            if run and run.get('status') == 'completed':
                continue
            test_item = indexes['test_items'].get(attempt.get('test_item_id'), {})
            if int(test_item.get('estimated_minutes') or 0) <= 0:
                continue
            unscheduled.append(attempt)
        if not unscheduled:
            continue

        first = unscheduled[0]
        first_test = indexes['test_items'].get(first.get('test_item_id'), {})
        document = indexes['documents'].get(first_test.get('document_id'), {})
        doc_name = document.get('doc_name', '')
        exam_no = first.get('exam_no')
        identifiers = _identifier_dicts(unscheduled, indexes)
        all_identifiers = _identifier_dicts(attempts, indexes)
        assignee_names = list(first.get('default_assignee_names', []))
        location = indexes['locations'].get(first.get('default_location_id', ''), {})
        remaining = sum(int(item.get('estimated_minutes') or 0) for item in identifiers)
        total = sum(int(item.get('estimated_minutes') or 0) for item in all_identifiers)
        queue.append({
            'id': task_id,
            'doc_id': document.get('external_doc_id', ''),
            'doc_name': doc_name,
            'display_name': _display_name(doc_name, exam_no),
            'exam_no': exam_no,
            'assignee_names': assignee_names,
            'assignee_name': ', '.join(assignee_names) if assignee_names else '(미배정)',
            'assignee_color': _assignee_color(assignee_names, indexes['users']),
            'location_id': first.get('default_location_id', ''),
            'location_name': location.get('name', ''),
            'location_color': location.get('color', '#6c757d'),
            'identifiers': identifiers,
            'estimated_minutes': total,
            'remaining_unscheduled_minutes': remaining,
            'section_color': _section_color(doc_name),
        })

    return sorted(queue, key=lambda item: (
        item.get('doc_name', '') or str(item.get('doc_id', '')),
        item.get('exam_no') or 0,
    ))


def _indexes(snapshot):
    catalog = snapshot.get('catalog', {})
    resources = snapshot.get('resources', {})
    runs_by_attempt = {}
    for run in snapshot.get('executions', {}).get('runs', []):
        runs_by_attempt[run.get('exam_attempt_id')] = run
    return {
        'documents': {item['id']: item for item in catalog.get('documents', [])},
        'test_items': {item['id']: item for item in catalog.get('test_items', [])},
        'attempts': {item['id']: item for item in catalog.get('exam_attempts', [])},
        'runs_by_attempt': runs_by_attempt,
        'locations': {item['id']: item for item in resources.get('locations', [])},
        'users': {item.get('name'): item for item in resources.get('users', [])},
    }


def _attempts_by_legacy_task(snapshot):
    result = {}
    for attempt in snapshot.get('catalog', {}).get('exam_attempts', []):
        task_id = attempt.get('legacy_task_id')
        if task_id:
            result.setdefault(task_id, []).append(attempt)
    return result


def _block_items_by_block(snapshot):
    result = {}
    for item in snapshot.get('schedule', {}).get('block_items', []):
        result.setdefault(item.get('block_id'), []).append(item)
    for items in result.values():
        items.sort(key=lambda item: (item.get('sort_order', 0), item.get('id', '')))
    return result


def _placed_identifier_ids_by_task(snapshot, indexes):
    result = {}
    for item in snapshot.get('schedule', {}).get('block_items', []):
        attempt = indexes['attempts'].get(item.get('exam_attempt_id'), {})
        task_id = attempt.get('legacy_task_id')
        identifier_id = attempt.get('legacy_identifier_id')
        if task_id and identifier_id:
            result.setdefault(task_id, set()).add(identifier_id)
    return result


def _identifier_dicts(attempts, indexes):
    identifiers = []
    seen = set()
    for attempt in attempts:
        identifier_id = attempt.get('legacy_identifier_id', '')
        if not identifier_id or identifier_id in seen:
            continue
        test_item = indexes['test_items'].get(attempt.get('test_item_id'), {})
        identifiers.append({
            'id': identifier_id,
            'name': test_item.get('name', ''),
            'estimated_minutes': int(test_item.get('estimated_minutes') or 0),
            'total_count': int(test_item.get('total_count') or 0),
            'owners': list(test_item.get('owner_names', [])),
        })
        seen.add(identifier_id)
    return identifiers


def _block_status(block, attempts, runs_by_attempt):
    manual_status = block.get('manual_status') or ''
    if manual_status:
        return manual_status
    if block.get('kind') == 'simple':
        return 'pending'
    statuses = []
    for attempt in attempts:
        run = runs_by_attempt.get(attempt.get('id'))
        statuses.append(run.get('status', 'pending') if run else 'pending')
    if statuses and all(status == 'completed' for status in statuses):
        return 'completed'
    if any(status in ('in_progress', 'paused', 'completed') for status in statuses):
        return 'in_progress'
    return 'pending'


def _block_color(block, color_by):
    if color_by == 'status':
        return STATUS_COLORS.get(block.get('block_status'), STATUS_COLORS['pending'])
    if color_by == 'location':
        return block.get('location_color', '#6c757d')
    return block.get('assignee_color', '#6c757d')


def _assignee_color(assignee_names, users):
    if not assignee_names:
        return '#6c757d'
    user = users.get(assignee_names[0])
    return user.get('color', '#6c757d') if user else '#6c757d'


def _display_name(doc_name, exam_no):
    if exam_no is not None and exam_no != 1:
        return f'{doc_name} ({exam_no}차)'
    return doc_name


def _first(values):
    for value in values:
        if value:
            return value
    return ''
