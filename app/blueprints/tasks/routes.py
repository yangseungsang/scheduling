from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, abort

from app.repositories import task_repo, user_repo, category_repo

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


# ---------------------------------------------------------------------------
# Template rendering routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/')
def task_list():
    tasks = task_repo.get_all()
    status = request.args.get('status')
    assignee = request.args.get('assignee')
    priority = request.args.get('priority')
    category = request.args.get('category')
    if status:
        tasks = [t for t in tasks if t['status'] == status]
    if assignee:
        tasks = [t for t in tasks if t['assignee_id'] == assignee]
    if priority:
        tasks = [t for t in tasks if t['priority'] == priority]
    if category:
        tasks = [t for t in tasks if t['category_id'] == category]
    users = user_repo.get_all()
    categories = category_repo.get_all()
    user_map = {u['id']: u['name'] for u in users}
    category_map = {c['id']: c['name'] for c in categories}
    return render_template('tasks/list.html',
                           tasks=tasks, users=users, categories=categories,
                           user_map=user_map, category_map=category_map,
                           filters={
                               'status': status or '',
                               'assignee': assignee or '',
                               'priority': priority or '',
                               'category': category or '',
                           })


@tasks_bp.route('/new', methods=['GET', 'POST'])
def task_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('업무 제목을 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_new'))
        task_repo.create(
            title=title,
            description=request.form.get('description', '').strip(),
            assignee_id=request.form.get('assignee_id', ''),
            category_id=request.form.get('category_id', ''),
            priority=request.form.get('priority', 'medium'),
            estimated_hours=float(request.form.get('estimated_hours', 0) or 0),
            deadline=request.form.get('deadline', ''),
        )
        flash('업무가 생성되었습니다.', 'success')
        return redirect(url_for('tasks.task_list'))
    users = user_repo.get_all()
    categories = category_repo.get_all()
    return render_template('tasks/form.html', task=None, users=users, categories=categories)


@tasks_bp.route('/<task_id>')
def task_detail(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    assignee = user_repo.get_by_id(task['assignee_id']) if task.get('assignee_id') else None
    category = category_repo.get_by_id(task['category_id']) if task.get('category_id') else None
    return render_template('tasks/detail.html', task=task, assignee=assignee, category=category)


@tasks_bp.route('/<task_id>/edit', methods=['GET', 'POST'])
def task_edit(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('업무 제목을 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_edit', task_id=task_id))
        task_repo.update(
            task_id=task_id,
            title=title,
            description=request.form.get('description', '').strip(),
            assignee_id=request.form.get('assignee_id', ''),
            category_id=request.form.get('category_id', ''),
            priority=request.form.get('priority', 'medium'),
            estimated_hours=float(request.form.get('estimated_hours', 0) or 0),
            remaining_hours=float(request.form.get('remaining_hours', 0) or 0),
            deadline=request.form.get('deadline', ''),
            status=request.form.get('status', 'waiting'),
        )
        flash('업무가 수정되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    users = user_repo.get_all()
    categories = category_repo.get_all()
    return render_template('tasks/form.html', task=task, users=users, categories=categories)


@tasks_bp.route('/<task_id>/delete', methods=['POST'])
def task_delete(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    task_repo.delete(task_id)
    flash('업무가 삭제되었습니다.', 'success')
    return redirect(url_for('tasks.task_list'))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/api/list')
def api_task_list():
    tasks = task_repo.get_all()

    status = request.args.get('status')
    assignee = request.args.get('assignee')
    priority = request.args.get('priority')
    category = request.args.get('category')

    if status:
        tasks = [t for t in tasks if t['status'] == status]
    if assignee:
        tasks = [t for t in tasks if t['assignee_id'] == assignee]
    if priority:
        tasks = [t for t in tasks if t['priority'] == priority]
    if category:
        tasks = [t for t in tasks if t['category_id'] == category]

    users = user_repo.get_all()
    categories = category_repo.get_all()

    return jsonify({
        'tasks': tasks,
        'users': users,
        'categories': categories,
    })


@tasks_bp.route('/api/<task_id>')
def api_task_detail(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '업무를 찾을 수 없습니다.'}), 404

    assignee = user_repo.get_by_id(task['assignee_id']) if task.get('assignee_id') else None
    category = category_repo.get_by_id(task['category_id']) if task.get('category_id') else None

    return jsonify({
        'task': task,
        'assignee': assignee,
        'category': category,
    })


@tasks_bp.route('/api/create', methods=['POST'])
def api_task_create():
    data = request.get_json()
    if not data or not data.get('title', '').strip():
        return jsonify({'error': '업무 제목을 입력해주세요.'}), 400

    task = task_repo.create(
        title=data['title'].strip(),
        description=data.get('description', '').strip(),
        assignee_id=data.get('assignee_id', ''),
        category_id=data.get('category_id', ''),
        priority=data.get('priority', 'medium'),
        estimated_hours=float(data.get('estimated_hours', 0) or 0),
        deadline=data.get('deadline', ''),
    )
    return jsonify(task), 201


@tasks_bp.route('/api/<task_id>/update', methods=['PUT'])
def api_task_update(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '업무를 찾을 수 없습니다.'}), 404

    data = request.get_json()
    if not data or not data.get('title', '').strip():
        return jsonify({'error': '업무 제목을 입력해주세요.'}), 400

    updated = task_repo.update(
        task_id=task_id,
        title=data['title'].strip(),
        description=data.get('description', '').strip(),
        assignee_id=data.get('assignee_id', ''),
        category_id=data.get('category_id', ''),
        priority=data.get('priority', 'medium'),
        estimated_hours=float(data.get('estimated_hours', 0) or 0),
        remaining_hours=float(data.get('remaining_hours', 0) or 0),
        deadline=data.get('deadline', ''),
        status=data.get('status', 'waiting'),
    )
    return jsonify(updated)


@tasks_bp.route('/api/<task_id>/delete', methods=['DELETE'])
def api_task_delete(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '업무를 찾을 수 없습니다.'}), 404

    task_repo.delete(task_id)
    return jsonify({'success': True})
