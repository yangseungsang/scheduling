from flask import render_template, request, redirect, url_for, jsonify, flash, abort
from app.blueprints.tasks import tasks_bp
from app.repositories import task_repo, category_repo, user_repo


@tasks_bp.route('/')
def task_list():
    status = request.args.get('status')
    category_id = request.args.get('category_id', type=int)
    assignee_id = request.args.get('assignee_id', type=int)
    page = request.args.get('page', 1, type=int)
    tasks, total, total_pages = task_repo.get_all_tasks(
        status=status, category_id=category_id,
        assignee_id=assignee_id, page=page)
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/list.html', tasks=tasks, categories=categories,
                           users=users, selected_status=status,
                           selected_category=category_id, selected_assignee=assignee_id,
                           page=page, total=total, total_pages=total_pages)


@tasks_bp.route('/new', methods=['GET', 'POST'])
def create_task():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('업무 제목은 필수입니다.', 'danger')
            return redirect(url_for('tasks.create_task'))
        estimated_minutes = request.form.get('estimated_minutes', 60, type=int)
        if estimated_minutes <= 0:
            flash('예상 소요시간은 1분 이상이어야 합니다.', 'danger')
            return redirect(url_for('tasks.create_task'))
        priority = request.form.get('priority', 'medium')
        if priority not in ('urgent', 'high', 'medium', 'low'):
            priority = 'medium'
        assignee_ids = request.form.getlist('assignee_ids', type=int)
        task_id = task_repo.create_task(
            title=title,
            description=request.form.get('description', ''),
            category_id=request.form.get('category_id', type=int),
            priority=priority,
            estimated_minutes=estimated_minutes,
            due_date=request.form.get('due_date') or None,
            created_by=request.form.get('created_by', type=int),
            assignee_ids=assignee_ids,
        )
        flash('업무가 생성되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/form.html', categories=categories, users=users,
                           task=None, assignees=[])


@tasks_bp.route('/<int:task_id>')
def task_detail(task_id):
    task, assignees = task_repo.get_task_by_id(task_id)
    if not task:
        abort(404)
    notes = task_repo.get_task_notes(task_id)
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/detail.html', task=task, assignees=assignees,
                           notes=notes, categories=categories, users=users)


@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
def edit_task(task_id):
    task, assignees = task_repo.get_task_by_id(task_id)
    if not task:
        abort(404)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('업무 제목은 필수입니다.', 'danger')
            return redirect(url_for('tasks.edit_task', task_id=task_id))
        estimated_minutes = request.form.get('estimated_minutes', 60, type=int)
        if estimated_minutes <= 0:
            flash('예상 소요시간은 1분 이상이어야 합니다.', 'danger')
            return redirect(url_for('tasks.edit_task', task_id=task_id))
        priority = request.form.get('priority', 'medium')
        if priority not in ('urgent', 'high', 'medium', 'low'):
            priority = 'medium'
        assignee_ids = request.form.getlist('assignee_ids', type=int)
        task_repo.update_task(
            task_id=task_id,
            title=title,
            description=request.form.get('description', ''),
            category_id=request.form.get('category_id', type=int),
            priority=priority,
            estimated_minutes=estimated_minutes,
            due_date=request.form.get('due_date') or None,
            assignee_ids=assignee_ids,
        )
        flash('업무가 수정되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/form.html', task=task, assignees=assignees,
                           categories=categories, users=users)


@tasks_bp.route('/<int:task_id>/status', methods=['POST'])
def update_status(task_id):
    data = request.get_json(silent=True)
    status = (data or {}).get('status') or request.form.get('status')
    allowed = {'pending', 'in_progress', 'completed', 'cancelled'}
    if status not in allowed:
        if request.is_json:
            return jsonify({'success': False, 'error': 'invalid status'}), 400
        flash('유효하지 않은 상태값입니다.', 'danger')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    task_repo.update_task_status(task_id, status)
    if request.is_json:
        return jsonify({'success': True})
    flash('상태가 업데이트되었습니다.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


@tasks_bp.route('/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    task_repo.delete_task(task_id)
    flash('업무가 삭제되었습니다.', 'info')
    return redirect(url_for('tasks.task_list'))


@tasks_bp.route('/<int:task_id>/notes', methods=['POST'])
def add_note(task_id):
    content = request.form.get('content', '').strip()
    user_id = request.form.get('user_id', type=int)
    if content:
        task_repo.add_task_note(task_id, user_id, content)
        flash('메모가 추가되었습니다.', 'success')
    else:
        flash('메모 내용을 입력해주세요.', 'warning')
    return redirect(url_for('tasks.task_detail', task_id=task_id))
