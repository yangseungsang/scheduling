import json

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, abort

from schedule.models import task, user, location, version, schedule_block

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


def _parse_test_list_from_form():
    """Parse test_list from the hidden JSON field in the form."""
    raw = request.form.get('test_list_json', '').strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return []


def _compute_estimated_minutes(test_list):
    return sum(item.get('estimated_minutes', 0) for item in test_list if isinstance(item, dict))


# ---------------------------------------------------------------------------
# Template rendering routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/')
def task_list():
    tasks_all = task.get_all()
    version_filter = request.args.get('version')
    status = request.args.get('status')
    assignees = request.args.getlist('assignee')
    location_filter = request.args.get('location')
    procedure = request.args.get('procedure', '').strip()
    date_filter = request.args.get('date', '').strip()

    if version_filter:
        tasks_all = [t for t in tasks_all if t.get('version_id') == version_filter]
    if status:
        tasks_all = [t for t in tasks_all if t['status'] == status]
    if assignees:
        tasks_all = [t for t in tasks_all if any(a in t.get('assignee_ids', []) for a in assignees)]
    if location_filter:
        tasks_all = [t for t in tasks_all if t.get('location_id') == location_filter]
    if procedure:
        tasks_all = [t for t in tasks_all if procedure.lower() in t.get('procedure_id', '').lower()]
    if date_filter:
        blocks_on_date = schedule_block.get_by_date(date_filter)
        task_ids_on_date = {b['task_id'] for b in blocks_on_date if b.get('task_id')}
        tasks_all = [t for t in tasks_all if t['id'] in task_ids_on_date]

    users = user.get_all()
    locations = location.get_all()
    versions = version.get_all()
    user_map = {u['id']: u['name'] for u in users}
    location_map = {loc['id']: loc['name'] for loc in locations}

    all_blocks = schedule_block.get_all()
    task_ids_scheduled = {b['task_id'] for b in all_blocks if b.get('task_id')}

    # Build schedule status + split info per task
    schedule_status_map = {}
    split_info_map = {}  # task_id → { block_count, has_split }
    blocks_by_task = {}
    for b in all_blocks:
        tid = b.get('task_id')
        if tid:
            blocks_by_task.setdefault(tid, []).append(b)

    location_map_full = {loc['id']: loc for loc in locations}
    for t in tasks_all:
        tid = t['id']
        task_blocks = blocks_by_task.get(tid, [])
        schedule_status_map[tid] = 'scheduled' if task_blocks else 'queue'
        total_ids = len(t.get('test_list', []))
        has_split = any(b.get('identifier_ids') is not None and len(b.get('identifier_ids', [])) < total_ids
                        for b in task_blocks)
        block_details = []
        for b in sorted(task_blocks, key=lambda x: (x['date'], x['start_time'])):
            loc_obj = location_map_full.get(b.get('location_id'))
            ids = b.get('identifier_ids')
            block_details.append({
                'date': b['date'],
                'start_time': b['start_time'],
                'end_time': b['end_time'],
                'location_name': loc_obj['name'] if loc_obj else '',
                'identifier_ids': ids,
                'id_count': len(ids) if ids else total_ids,
            })
        split_info_map[tid] = {
            'block_count': len(task_blocks),
            'has_split': has_split,
            'blocks': block_details,
        }

    return render_template('tasks/list.html',
                           tasks=tasks_all, users=users,
                           locations=locations, versions=versions,
                           user_map=user_map, location_map=location_map,
                           schedule_status_map=schedule_status_map,
                           split_info_map=split_info_map,
                           filters={
                               'version': version_filter or '',
                               'status': status or '',
                               'assignees': assignees,
                               'location': location_filter or '',
                               'procedure': procedure,
                               'date': date_filter,
                           })


@tasks_bp.route('/new', methods=['GET', 'POST'])
def task_new():
    if request.method == 'POST':
        procedure_id = request.form.get('procedure_id', '').strip()
        if not procedure_id:
            flash('절차서 식별자를 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_new'))
        assignee_ids = request.form.getlist('assignee_ids')
        test_list = _parse_test_list_from_form()
        estimated_minutes = _compute_estimated_minutes(test_list) if test_list else int(request.form.get('estimated_minutes', 0) or 0)

        # Validate identifier uniqueness
        dupes = task.validate_unique_identifiers(test_list)
        if dupes:
            flash(f'중복된 식별자가 있습니다: {", ".join(dupes)}', 'danger')
            return redirect(url_for('tasks.task_new'))

        task.create(
            procedure_id=procedure_id,
            version_id=request.form.get('version_id', ''),
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_minutes=estimated_minutes,
            memo=request.form.get('memo', '').strip(),
        )
        flash('시험 항목이 생성되었습니다.', 'success')
        return redirect(url_for('tasks.task_list'))
    users = user.get_all()
    locations = location.get_all()
    versions = version.get_all()
    return render_template('tasks/form.html', task=None,
                           users=users, locations=locations, versions=versions)


@tasks_bp.route('/<task_id>')
def task_detail(task_id):
    t = task.get_by_id(task_id)
    if not t:
        abort(404)
    users = user.get_all()
    user_map = {u['id']: u['name'] for u in users}
    assignee_names = [user_map.get(uid, uid) for uid in t.get('assignee_ids', [])]
    loc = location.get_by_id(t.get('location_id')) if t.get('location_id') else None
    ver = version.get_by_id(t.get('version_id')) if t.get('version_id') else None

    # Build identifier → scheduled date mapping
    all_blocks = schedule_block.get_all()
    task_blocks = [b for b in all_blocks if b.get('task_id') == task_id]
    total_ids = [item['id'] if isinstance(item, dict) else item
                 for item in t.get('test_list', [])]
    identifier_schedule = {}  # id → {date, start_time, end_time}
    for b in sorted(task_blocks, key=lambda x: (x['date'], x['start_time'])):
        block_ids = b.get('identifier_ids')
        if block_ids:
            covered = block_ids
        else:
            covered = total_ids
        for iid in covered:
            if iid not in identifier_schedule:
                identifier_schedule[iid] = {
                    'date': b['date'],
                    'start_time': b['start_time'],
                    'end_time': b['end_time'],
                }

    return render_template('tasks/detail.html', task=t,
                           assignee_names=assignee_names,
                           identifier_schedule=identifier_schedule,
                           location=loc, version=ver)


@tasks_bp.route('/<task_id>/edit', methods=['GET', 'POST'])
def task_edit(task_id):
    t = task.get_by_id(task_id)
    if not t:
        abort(404)
    if request.method == 'POST':
        procedure_id = request.form.get('procedure_id', '').strip()
        if not procedure_id:
            flash('절차서 식별자를 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_edit', task_id=task_id))
        assignee_ids = request.form.getlist('assignee_ids')
        test_list = _parse_test_list_from_form()
        estimated_minutes = _compute_estimated_minutes(test_list) if test_list else int(request.form.get('estimated_minutes', 0) or 0)
        remaining_minutes = int(request.form.get('remaining_minutes', 0) or 0)

        # Validate identifier uniqueness
        dupes = task.validate_unique_identifiers(test_list, exclude_task_id=task_id)
        if dupes:
            flash(f'중복된 식별자가 있습니다: {", ".join(dupes)}', 'danger')
            return redirect(url_for('tasks.task_edit', task_id=task_id))

        task.update(
            task_id=task_id,
            procedure_id=procedure_id,
            version_id=request.form.get('version_id', ''),
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_minutes=estimated_minutes,
            remaining_minutes=remaining_minutes,
            status=request.form.get('status', 'waiting'),
            memo=request.form.get('memo', '').strip(),
        )
        flash('시험 항목이 수정되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    users = user.get_all()
    locations = location.get_all()
    versions = version.get_all()
    return render_template('tasks/form.html', task=t,
                           users=users, locations=locations, versions=versions)


@tasks_bp.route('/<task_id>/delete', methods=['POST'])
def task_delete(task_id):
    t = task.get_by_id(task_id)
    if not t:
        abort(404)
    task.delete(task_id)
    flash('시험 항목이 삭제되었습니다.', 'success')
    return redirect(url_for('tasks.task_list'))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/api/list')
def api_task_list():
    tasks_all = task.get_all()
    ver = request.args.get('version')
    if ver:
        tasks_all = [t for t in tasks_all if t.get('version_id') == ver]
    return jsonify({'tasks': tasks_all})


@tasks_bp.route('/api/<task_id>')
def api_task_detail(task_id):
    t = task.get_by_id(task_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    users = user.get_all()
    user_map = {u['id']: u['name'] for u in users}
    locations = location.get_all()
    loc_map = {loc['id']: loc['name'] for loc in locations}
    versions = version.get_all()
    ver_map = {v['id']: v['name'] for v in versions}
    result = dict(t)
    result['assignee_names'] = [user_map.get(uid, uid) for uid in t.get('assignee_ids', [])]
    result['location_name'] = loc_map.get(t.get('location_id', ''), '')
    result['version_name'] = ver_map.get(t.get('version_id', ''), '')
    return jsonify({'task': result})


@tasks_bp.route('/api/create', methods=['POST'])
def api_task_create():
    data = request.get_json()
    if not data or not data.get('procedure_id', '').strip():
        return jsonify({'error': '절차서 식별자를 입력해주세요.'}), 400
    test_list = data.get('test_list', [])
    estimated_minutes = _compute_estimated_minutes(test_list) if test_list else int(data.get('estimated_minutes', 0) or 0)

    dupes = task.validate_unique_identifiers(test_list)
    if dupes:
        return jsonify({'error': f'중복된 식별자: {", ".join(dupes)}'}), 400

    t = task.create(
        procedure_id=data['procedure_id'].strip(),
        version_id=data.get('version_id', ''),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=test_list,
        estimated_minutes=estimated_minutes,
        memo=data.get('memo', ''),
    )
    return jsonify(t), 201


@tasks_bp.route('/api/<task_id>/update', methods=['PUT'])
def api_task_update(task_id):
    t = task.get_by_id(task_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if not data or not data.get('procedure_id', '').strip():
        return jsonify({'error': '절차서 식별자를 입력해주세요.'}), 400
    test_list = data.get('test_list', [])
    estimated_minutes = _compute_estimated_minutes(test_list) if test_list else int(data.get('estimated_minutes', 0) or 0)

    dupes = task.validate_unique_identifiers(test_list, exclude_task_id=task_id)
    if dupes:
        return jsonify({'error': f'중복된 식별자: {", ".join(dupes)}'}), 400

    updated = task.update(
        task_id=task_id,
        procedure_id=data['procedure_id'].strip(),
        version_id=data.get('version_id', ''),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=test_list,
        estimated_minutes=estimated_minutes,
        remaining_minutes=int(data.get('remaining_minutes', 0) or 0),
        status=data.get('status', 'waiting'),
        memo=data.get('memo', ''),
    )
    return jsonify(updated)


@tasks_bp.route('/api/<task_id>/delete', methods=['DELETE'])
def api_task_delete(task_id):
    t = task.get_by_id(task_id)
    if not t:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    task.delete(task_id)
    return jsonify({'success': True})


@tasks_bp.route('/api/procedure/<procedure_id>')
def api_procedure_lookup(procedure_id):
    from schedule.services.procedure import lookup
    result = lookup(procedure_id)
    if not result:
        return jsonify({'error': '절차서를 찾을 수 없습니다.'}), 404
    return jsonify(result)


@tasks_bp.route('/api/check-identifier')
def api_check_identifier():
    """Check if an identifier ID is already used by another task."""
    identifier_id = request.args.get('id', '').strip()
    exclude_task = request.args.get('exclude_task', '')
    if not identifier_id:
        return jsonify({'available': True})
    dupes = task.validate_unique_identifiers(
        [{'id': identifier_id}],
        exclude_task_id=exclude_task or None,
    )
    return jsonify({'available': len(dupes) == 0, 'duplicates': dupes})
