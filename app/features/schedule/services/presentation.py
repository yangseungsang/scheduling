"""Schedule view and export presentation models."""

import calendar
import hashlib
from datetime import date, datetime

from app.features.schedule.services.time import (
    generate_time_slots,
    is_break_slot,
    time_to_minutes,
)
from app.services.read_models import build_schedule_export_rows


def build_day_payload(procedures, schedule, executions, current_date, settings, time_slots, break_slots):
    """Build the complete JSON payload consumed by the day view."""
    return {
        'blocks': build_ui_blocks(
            procedures, schedule, executions,
            current_date, current_date, settings,
        ),
        'time_slots': time_slots,
        'break_slots': break_slots,
        'settings': settings,
        'queue_procedures': build_queue_procedures(procedures, schedule, executions),
    }


def schedule_settings(settings):
    """Merge optional AppSettings with stable calendar defaults."""
    result = {
        'work_start': '08:00', 'work_end': '17:00',
        'actual_work_start': '', 'actual_work_end': '',
        'lunch_start': '12:00', 'lunch_end': '13:00', 'breaks': [],
        'grid_interval_minutes': 15, 'max_schedule_days': 14,
        'block_color_by': 'assignee',
    }
    result.update(settings.to_dict() if hasattr(settings, 'to_dict') else (settings or {}))
    return result


def build_location_options(procedures, schedule):
    """Build UI options from location names already stored on procedures and blocks."""
    names = sorted(
        {procedure.location_name for procedure in procedures if procedure.location_name}
        | {block.location_name for block in schedule.blocks if block.location_name}
    )
    return [
        {'id': name, 'name': name, 'color': _location_color(name)}
        for name in names
    ]


def build_export_blocks(procedures, schedule, executions, start_date, end_date):
    """Build enriched blocks for CSV/XLSX serialization."""
    rows = build_schedule_export_rows(
        procedures, schedule, executions, start_date, end_date,
    )
    blocks = []
    for row in rows:
        test_items = [{'id': item, 'name': '', 'estimated_minutes': 0} for item in row['test_item_ids']]
        split_label = row.get('split_label', '')
        block = {
            'id': row['block_id'], 'date': row['date'],
            'start_time': row['start_time'], 'end_time': row['end_time'],
            'location_name': row['location_name'],
            'assignee_names': list(row['assignee_names']), 'kind': row['kind'],
            'title': row['title'], 'document_name': row['document_name'],
            'display_name': row['document_name'], 'procedure_title': row['document_name'],
            'test_items': test_items,
            'test_item_ids': [item['id'] for item in test_items],
            'block_status': row['execution_status'], 'memo': row['memo'],
            'color': STATUS_COLORS.get(row['execution_status'], STATUS_COLORS['pending']),
            'is_simple': row['kind'] == 'simple', 'is_split': bool(split_label),
        }
        if split_label:
            block['block_test_item_count'], block['total_test_item_count'] = split_label.split('/', 1)
        blocks.append(block)
    return blocks


def build_ui_blocks(procedures, schedule, executions, start_date='', end_date='', settings=None):
    """Join blocks with procedure/execution data for calendar rendering."""
    procedures_by_id = {item.id: item for item in procedures}
    runs = {(item.procedure_id, item.test_item_id): item for item in executions.runs}
    placed = _placed_test_items(schedule)
    color_by = (settings or {}).get('block_color_by', 'assignee')
    result = []
    for block in schedule.blocks:
        if start_date and block.date < start_date:
            continue
        if end_date and block.date > end_date:
            continue
        procedure = procedures_by_id.get(block.procedure_id)
        test_items = list(procedure.test_items) if procedure else []
        selected_ids = list(block.test_item_ids)
        selected = [item for item in test_items if item.id in set(selected_ids)]
        document_name = procedure.document_name if procedure else block.title
        status = _block_status(block, runs)
        assignee_names = list(block.assignee_names)
        row = {
            'id': block.id, 'procedure_id': block.procedure_id, 'date': block.date,
            'start_time': block.start_time, 'end_time': block.end_time,
            'location_name': block.location_name,
            'location_color': _location_color(block.location_name),
            'assignee_names': assignee_names,
            'assignee_name': ', '.join(assignee_names) if assignee_names else '(미배정)',
            'assignee_color': _assignee_color(assignee_names),
            'document_id': procedure.document_id if procedure and procedure.document_id else '',
            'document_name': document_name,
            'procedure_title': block.title if block.kind == 'simple' else document_name,
            'display_name': _display_name(document_name, procedure.test_round if procedure else None),
            'test_round': procedure.test_round if procedure else None,
            'test_items': [_test_item_dict(item) for item in test_items],
            'test_item_ids': selected_ids,
            'is_simple': block.kind == 'simple', 'title': block.title,
            'memo': block.memo, 'block_status': status, 'is_locked': block.is_locked,
            'section_color': _section_color(document_name),
            'estimated_minutes': sum(item.estimated_minutes for item in selected),
        }
        row['total_test_item_count'] = len(test_items)
        row['block_test_item_count'] = len(selected_ids)
        row['is_split'] = bool(test_items and len(selected_ids) < len(test_items))
        if row['is_split'] and procedure:
            unplaced = {item.id for item in test_items} - placed.get(procedure.id, set())
            row['split_status'] = 'partial' if unplaced else 'split'
        else:
            row['split_status'] = ''
        row['color'] = _block_color(row, color_by)
        result.append(row)
    return sorted(result, key=lambda item: (item['date'], item['start_time'], item['id']))


def build_queue_procedures(procedures, schedule, executions):
    """Return unscheduled procedure work and remaining item durations."""
    runs = {(item.procedure_id, item.test_item_id): item for item in executions.runs}
    placed = _placed_test_items(schedule)
    queue = []
    for procedure in procedures:
        if procedure.state == 'cancelled' or procedure.kind == 'simple':
            available = list(procedure.test_items) if procedure.kind != 'simple' else []
        else:
            available = [
                item for item in procedure.test_items
                if item.id not in placed.get(procedure.id, set())
                and not (runs.get((procedure.id, item.id)) and runs[(procedure.id, item.id)].status == 'completed')
            ]
        if procedure.kind == 'simple':
            if any(block.procedure_id == procedure.id for block in schedule.blocks):
                continue
        elif not available:
            continue
        assignees = list(procedure.assignee_names)
        shown_test_items = available if procedure.kind != 'simple' else []
        queue.append({
            'id': procedure.id, 'document_id': procedure.document_id or '', 'document_name': procedure.document_name,
            'display_name': _display_name(procedure.document_name, procedure.test_round),
            'test_round': procedure.test_round, 'assignee_names': assignees,
            'assignee_name': ', '.join(assignees) if assignees else '(미배정)',
            'assignee_color': _assignee_color(assignees),
            'location_name': procedure.location_name,
            'location_color': _location_color(procedure.location_name),
            'test_items': [_test_item_dict(item) for item in shown_test_items],
            'estimated_minutes': procedure.estimated_minutes,
            'remaining_unscheduled_minutes': (
                procedure.estimated_minutes if procedure.kind == 'simple'
                else sum(item.estimated_minutes for item in shown_test_items)
            ),
            'section_color': _section_color(procedure.document_name),
            'is_simple': procedure.kind == 'simple',
        })
    return sorted(queue, key=lambda item: (item['document_name'] or str(item['document_id']), item.get('test_round') or 0))


def _placed_test_items(schedule):
    """Index placed item IDs by procedure."""
    result = {}
    for block in schedule.blocks:
        if block.procedure_id:
            result.setdefault(block.procedure_id, set()).update(block.test_item_ids)
    return result


def _test_item_dict(test_item):
    """Convert one immutable test item to a template-friendly dictionary."""
    return {
        'id': test_item.id, 'name': test_item.name,
        'estimated_minutes': test_item.estimated_minutes,
        'total_count': test_item.total_count, 'owners': list(test_item.owner_names),
    }


def _block_status(block, runs):
    """Derive a block status from manual state and item execution states."""
    if block.manual_status == 'cancelled':
        return 'cancelled'
    if block.kind == 'simple':
        return 'pending'
    statuses = [
        runs.get((block.procedure_id, test_item_id)).status
        if runs.get((block.procedure_id, test_item_id)) else 'pending'
        for test_item_id in block.test_item_ids
    ]
    if statuses and all(item == 'completed' for item in statuses):
        return 'completed'
    if any(item in ('in_progress', 'paused', 'completed') for item in statuses):
        return 'in_progress'
    return 'pending'


def _block_color(block, color_by):
    """Choose a deterministic block color using the configured dimension."""
    if color_by == 'status':
        return STATUS_COLORS.get(block['block_status'], STATUS_COLORS['pending'])
    if color_by == 'location':
        return block['location_color']
    return block['assignee_color']


def _assignee_color(names):
    """Generate a stable color from sorted assignee names."""
    return _section_color(names[0]) if names else '#6c757d'


def _location_color(name):
    """Generate a stable color from a location name."""
    return _section_color(name) if name else '#6c757d'


def _display_name(name, test_round):
    """Append a test-round suffix when needed."""
    return f'{name} ({test_round}차)' if test_round not in (None, 1) else name


STATUS_COLORS = {
    'pending': '#94a3b8',
    'in_progress': '#0d6efd',
    'completed': '#198754',
    'cancelled': '#dc3545',
}


def _section_color(value):
    """Map arbitrary text to a readable deterministic HSL color."""
    if not value:
        return '#94a3b8'
    hue = int(hashlib.md5(value.encode()).hexdigest()[:8], 16) % 360
    return f'hsl({hue}, 55%, 45%)'


def get_break_slots(settings):
    """Return time-slot labels that fall inside configured breaks."""
    return {
        slot for slot in generate_time_slots(settings)
        if is_break_slot(slot, settings)
    }


def build_month_nav(year, month):
    """Build previous/current/next month navigation metadata."""
    previous = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return previous, following


def group_blocks_by_date(blocks):
    """Index UI blocks by ISO date while preserving input order."""
    result = {}
    for block in blocks:
        result.setdefault(block['date'], []).append(block)
    return result


def build_month_weeks(year, month, blocks_by_date):
    """Build weekday cells and attached blocks for the month template."""
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        weeks.append([
            None if day_number == 0 else {
                'date': date(year, month, day_number),
                'day': day_number,
                'blocks': blocks_by_date.get(
                    date(year, month, day_number).isoformat(), [],
                ),
            }
            for day_number in week[:5]
        ])
    return weeks


def parse_date(value):
    """Parse an ISO date and fall back to today for missing values."""
    if value:
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            pass
    return date.today()


def compute_overlap_layout(blocks):
    """Assign display columns to blocks that overlap in time."""
    if not blocks:
        return blocks
    sorted_blocks = sorted(
        blocks,
        key=lambda block: (
            time_to_minutes(block['start_time']),
            -time_to_minutes(block['end_time']),
        ),
    )
    columns = []
    block_columns = {}
    for index, block in enumerate(sorted_blocks):
        start = time_to_minutes(block['start_time'])
        for column_index, (column_end, indices) in enumerate(columns):
            if column_end <= start:
                columns[column_index] = (
                    time_to_minutes(block['end_time']), indices + [index],
                )
                block_columns[index] = column_index
                break
        else:
            block_columns[index] = len(columns)
            columns.append((time_to_minutes(block['end_time']), [index]))

    for index, block in enumerate(sorted_blocks):
        start = time_to_minutes(block['start_time'])
        end = time_to_minutes(block['end_time'])
        total = block_columns[index] + 1
        for other_index, other in enumerate(sorted_blocks):
            if index == other_index:
                continue
            if (
                start < time_to_minutes(other['end_time'])
                and time_to_minutes(other['start_time']) < end
            ):
                total = max(total, block_columns[other_index] + 1)
        block['col_index'] = block_columns[index]
        block['col_total'] = total
    return sorted_blocks
