from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, abort

from app.repositories import task_repo, user_repo, location_repo, version_repo

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


# ---------------------------------------------------------------------------
# Template rendering routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/')
def task_list():
    tasks = task_repo.get_all()
    version = request.args.get('version')
    status = request.args.get('status')
    assignees = request.args.getlist('assignee')
    location = request.args.get('location')
    procedure = request.args.get('procedure', '').strip()

    if version:
        tasks = [t for t in tasks if t.get('version_id') == version]
    if status:
        tasks = [t for t in tasks if t['status'] == status]
    if assignees:
        tasks = [t for t in tasks if any(a in t.get('assignee_ids', []) for a in assignees)]
    if location:
        tasks = [t for t in tasks if t.get('location_id') == location]
    if procedure:
        tasks = [t for t in tasks if procedure.lower() in t.get('procedure_id', '').lower()]

    users = user_repo.get_all()
    locations = location_repo.get_all()
    versions = version_repo.get_all()
    user_map = {u['id']: u['name'] for u in users}
    location_map = {loc['id']: loc['name'] for loc in locations}

    return render_template('tasks/list.html',
                           tasks=tasks, users=users,
                           locations=locations, versions=versions,
                           user_map=user_map, location_map=location_map,
                           filters={
                               'version': version or '',
                               'status': status or '',
                               'assignees': assignees,
                               'location': location or '',
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
        task_repo.create(
            procedure_id=procedure_id,
            version_id=request.form.get('version_id', ''),
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_hours=float(request.form.get('estimated_hours', 0) or 0),
            deadline=request.form.get('deadline', ''),
            memo=request.form.get('memo', '').strip(),
        )
        flash('시험 항목이 생성되었습니다.', 'success')
        return redirect(url_for('tasks.task_list'))
    users = user_repo.get_all()
    locations = location_repo.get_all()
    versions = version_repo.get_all()
    return render_template('tasks/form.html', task=None,
                           users=users, locations=locations, versions=versions)


@tasks_bp.route('/<task_id>')
def task_detail(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    users = user_repo.get_all()
    user_map = {u['id']: u['name'] for u in users}
    assignee_names = [user_map.get(uid, uid) for uid in task.get('assignee_ids', [])]
    location = location_repo.get_by_id(task.get('location_id')) if task.get('location_id') else None
    version = version_repo.get_by_id(task.get('version_id')) if task.get('version_id') else None
    return render_template('tasks/detail.html', task=task,
                           assignee_names=assignee_names,
                           location=location, version=version)


@tasks_bp.route('/<task_id>/edit', methods=['GET', 'POST'])
def task_edit(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    if request.method == 'POST':
        procedure_id = request.form.get('procedure_id', '').strip()
        if not procedure_id:
            flash('절차서 식별자를 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_edit', task_id=task_id))
        assignee_ids = request.form.getlist('assignee_ids')
        test_list_raw = request.form.get('test_list', '')
        test_list = [t.strip() for t in test_list_raw.split(',') if t.strip()]
        task_repo.update(
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
            deadline=request.form.get('deadline', ''),
            status=request.form.get('status', 'waiting'),
            memo=request.form.get('memo', '').strip(),
        )
        flash('시험 항목이 수정되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    users = user_repo.get_all()
    locations = location_repo.get_all()
    versions = version_repo.get_all()
    return render_template('tasks/form.html', task=task,
                           users=users, locations=locations, versions=versions)


@tasks_bp.route('/<task_id>/delete', methods=['POST'])
def task_delete(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    task_repo.delete(task_id)
    flash('시험 항목이 삭제되었습니다.', 'success')
    return redirect(url_for('tasks.task_list'))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/api/list')
def api_task_list():
    tasks = task_repo.get_all()
    version = request.args.get('version')
    if version:
        tasks = [t for t in tasks if t.get('version_id') == version]
    return jsonify({'tasks': tasks})


@tasks_bp.route('/api/<task_id>')
def api_task_detail(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    return jsonify({'task': task})


@tasks_bp.route('/api/create', methods=['POST'])
def api_task_create():
    data = request.get_json()
    if not data or not data.get('procedure_id', '').strip():
        return jsonify({'error': '절차서 식별자를 입력해주세요.'}), 400
    task = task_repo.create(
        procedure_id=data['procedure_id'].strip(),
        version_id=data.get('version_id', ''),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=data.get('test_list', []),
        estimated_hours=float(data.get('estimated_hours', 0) or 0),
        deadline=data.get('deadline', ''),
        memo=data.get('memo', ''),
    )
    return jsonify(task), 201


@tasks_bp.route('/api/<task_id>/update', methods=['PUT'])
def api_task_update(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if not data or not data.get('procedure_id', '').strip():
        return jsonify({'error': '절차서 식별자를 입력해주세요.'}), 400
    updated = task_repo.update(
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
        deadline=data.get('deadline', ''),
        status=data.get('status', 'waiting'),
        memo=data.get('memo', ''),
    )
    return jsonify(updated)


@tasks_bp.route('/api/<task_id>/delete', methods=['DELETE'])
def api_task_delete(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    task_repo.delete(task_id)
    return jsonify({'success': True})


@tasks_bp.route('/api/procedure/<procedure_id>')
def api_procedure_lookup(procedure_id):
    from app.services.procedure_service import lookup
    result = lookup(procedure_id)
    if not result:
        return jsonify({'error': '절차서를 찾을 수 없습니다.'}), 404
    return jsonify(result)
