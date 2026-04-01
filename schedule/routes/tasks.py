from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, abort

from schedule.models import task, user, location, version

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


# ---------------------------------------------------------------------------
# Template rendering routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/')
def task_list():
    tasks = task.get_all()
    version_filter = request.args.get('version')
    status = request.args.get('status')
    assignees = request.args.getlist('assignee')
    location_filter = request.args.get('location')
    procedure = request.args.get('procedure', '').strip()

    if version_filter:
        tasks = [t for t in tasks if t.get('version_id') == version_filter]
    if status:
        tasks = [t for t in tasks if t['status'] == status]
    if assignees:
        tasks = [t for t in tasks if any(a in t.get('assignee_ids', []) for a in assignees)]
    if location_filter:
        tasks = [t for t in tasks if t.get('location_id') == location_filter]
    if procedure:
        tasks = [t for t in tasks if procedure.lower() in t.get('procedure_id', '').lower()]

    users = user.get_all()
    locations = location.get_all()
    versions = version.get_all()
    user_map = {u['id']: u['name'] for u in users}
    location_map = {loc['id']: loc['name'] for loc in locations}

    return render_template('tasks/list.html',
                           tasks=tasks, users=users,
                           locations=locations, versions=versions,
                           user_map=user_map, location_map=location_map,
                           filters={
                               'version': version_filter or '',
                               'status': status or '',
                               'assignees': assignees,
                               'location': location_filter or '',
                               'procedure': procedure,
                           })


@tasks_bp.route('/new', methods=['GET', 'POST'])
def task_new():
    if request.method == 'POST':
        procedure_id = request.form.get('procedure_id', '').strip()
        if not procedure_id:
            flash('절차서 식별자를 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_new'))
        assignee_ids = request.form.getlist('assignee_ids')
        test_list_raw = request.form.get('test_list', '')
        test_list = [t.strip() for t in test_list_raw.split(',') if t.strip()]
        task.create(
            procedure_id=procedure_id,
            version_id=request.form.get('version_id', ''),
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_hours=float(request.form.get('estimated_hours', 0) or 0),
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
    return render_template('tasks/detail.html', task=t,
                           assignee_names=assignee_names,
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
        test_list_raw = request.form.get('test_list', '')
        test_list = [t.strip() for t in test_list_raw.split(',') if t.strip()]
        task.update(
            task_id=task_id,
            procedure_id=procedure_id,
            version_id=request.form.get('version_id', ''),
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_hours=float(request.form.get('estimated_hours', 0) or 0),
            remaining_hours=float(request.form.get('remaining_hours', 0) or 0),
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
    tasks = task.get_all()
    ver = request.args.get('version')
    if ver:
        tasks = [t for t in tasks if t.get('version_id') == ver]
    return jsonify({'tasks': tasks})


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
    t = task.create(
        procedure_id=data['procedure_id'].strip(),
        version_id=data.get('version_id', ''),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=data.get('test_list', []),
        estimated_hours=float(data.get('estimated_hours', 0) or 0),
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
    updated = task.update(
        task_id=task_id,
        procedure_id=data['procedure_id'].strip(),
        version_id=data.get('version_id', ''),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=data.get('test_list', []),
        estimated_hours=float(data.get('estimated_hours', 0) or 0),
        remaining_hours=float(data.get('remaining_hours', 0) or 0),
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
