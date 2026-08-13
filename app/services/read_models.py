"""Read models built from the direct procedure, block, and execution references."""

def build_execution_list_items(
    procedures, schedule, executions,
    date_filter='', location_filter='',
):
    runs = {(item.procedure_id, item.test_item_id): item for item in executions.runs}
    scheduled = _scheduled_test_items(schedule)
    rows = []
    for procedure in procedures:
        for test_item in procedure.test_items:
            key = (procedure.id, test_item.id)
            run = runs.get(key)
            placement = scheduled.get(key)
            scheduled_date = placement.date if placement else ''
            location_name = placement.location_name if placement and placement.location_name else procedure.location_name
            if date_filter and scheduled_date != date_filter:
                continue
            if location_filter and location_name != location_filter:
                continue
            rows.append({
                'procedure_id': procedure.id,
                'document_name': procedure.document_name,
                'display_name': _display_name(procedure.document_name, procedure.test_round),
                'document_id': procedure.document_id,
                'test_item_id': test_item.id,
                'test_name': test_item.name,
                'test_round': procedure.test_round,
                'assignee_names': list(procedure.assignee_names),
                'owner_names': list(test_item.owner_names),
                'estimated_minutes': test_item.estimated_minutes,
                'total_count': run.total_count if run else test_item.total_count,
                'scheduled_date': scheduled_date,
                'scheduled_start_time': placement.start_time if placement else '',
                'scheduled_end_time': placement.end_time if placement else '',
                'location_name': location_name,
                'execution_status': run.status if run else 'pending',
                'performer_name': run.performer_name if run else '',
                'fail_count': run.fail_count if run else 0,
                'block_count': run.block_count if run else 0,
                'pass_count': run.pass_count if run else 0,
                'elapsed_seconds': run.elapsed_seconds if run else 0,
                'comment': run.comment if run else '',
            })
    return sorted(rows, key=lambda row: (
        row.get('scheduled_date') or '9999-99-99', row.get('location_name', ''),
        row.get('document_name', ''), row.get('test_item_id', ''),
        row.get('test_round') if row.get('test_round') is not None else -1,
    ))


def build_unscheduled_attempts(procedures, schedule, executions):
    scheduled = set(_scheduled_test_items(schedule))
    runs = {(item.procedure_id, item.test_item_id): item for item in executions.runs}
    rows = []
    for procedure in procedures:
        if procedure.state == 'cancelled':
            continue
        for test_item in procedure.test_items:
            key = (procedure.id, test_item.id)
            run = runs.get(key)
            if key in scheduled or (run and run.status == 'completed') or test_item.estimated_minutes <= 0:
                continue
            rows.append({
                'procedure_id': procedure.id,
                'document_name': procedure.document_name,
                'display_name': _display_name(procedure.document_name, procedure.test_round),
                'test_item_id': test_item.id,
                'test_name': test_item.name,
                'test_round': procedure.test_round,
                'remaining_minutes': test_item.estimated_minutes,
                'default_location_name': procedure.location_name,
                'owner_names': list(test_item.owner_names),
                'execution_status': run.status if run else 'pending',
            })
    return sorted(rows, key=lambda row: (
        row['document_name'], row.get('test_round') if row.get('test_round') is not None else -1,
        row['test_item_id'],
    ))


def build_schedule_export_rows(
    procedures, schedule, executions,
    start_date='', end_date='',
):
    procedures_by_id = {item.id: item for item in procedures}
    runs = {(item.procedure_id, item.test_item_id): item for item in executions.runs}
    rows = []
    for block in schedule.blocks:
        if start_date and block.date < start_date:
            continue
        if end_date and block.date > end_date:
            continue
        procedure = procedures_by_id.get(block.procedure_id)
        selected = _selected_test_items(procedure, block.test_item_ids)
        rows.append({
            'block_id': block.id,
            'date': block.date,
            'start_time': block.start_time,
            'end_time': block.end_time,
            'location_name': block.location_name,
            'assignee_names': list(block.assignee_names),
            'kind': block.kind,
            'title': block.title,
            'document_name': procedure.document_name if procedure else block.title,
            'test_item_ids': [item.id for item in selected],
            'split_label': _split_label(procedure, selected),
            'execution_status': _block_status(block, runs),
            'memo': block.memo,
        })
    return sorted(rows, key=lambda row: (
        row['date'], row['location_name'], row['start_time'], row['end_time'],
    ))


def _scheduled_test_items(schedule):
    result = {}
    for block in schedule.blocks:
        if not block.procedure_id:
            continue
        for test_item_id in block.test_item_ids:
            key = (block.procedure_id, test_item_id)
            current = result.get(key)
            if current is None or block.date < current.date:
                result[key] = block
    return result


def _selected_test_items(procedure, test_item_ids):
    if procedure is None:
        return []
    selected = set(test_item_ids)
    return [item for item in procedure.test_items if item.id in selected]


def _block_status(block, runs):
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


def _split_label(procedure, selected):
    if procedure is None or not procedure.test_items or len(selected) == len(procedure.test_items):
        return ''
    return f'{len(selected)}/{len(procedure.test_items)}'


def _display_name(document_name, test_round):
    return f'{document_name} ({test_round}차)' if test_round not in (None, 1) else document_name
