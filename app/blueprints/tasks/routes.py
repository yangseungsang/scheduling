from flask import render_template, request, redirect, url_for, jsonify, flash
from app.blueprints.tasks import tasks_bp
from app.repositories import task_repo, category_repo, user_repo


@tasks_bp.route('/')
def task_list():
    status = request.args.get('status')
    category_id = request.args.get('category_id', type=int)
    assignee_id = request.args.get('assignee_id', type=int)
    tasks = task_repo.get_all_tasks(status=status, category_id=category_id,
                                    assignee_id=assignee_id)
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/list.html', tasks=tasks, categories=categories,
                           users=users, selected_status=status,
                           selected_category=category_id, selected_assignee=assignee_id)


@tasks_bp.route('/new', methods=['GET', 'POST'])
def create_task():
    if request.method == 'POST':
        assignee_ids = request.form.getlist('assignee_ids', type=int)
        task_id = task_repo.create_task(
            title=request.form['title'],
            description=request.form.get('description', ''),
            category_id=request.form.get('category_id', type=int),
            priority=request.form.get('priority', 'medium'),
            estimated_minutes=request.form.get('estimated_minutes', 60, type=int),
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
        flash('업무를 찾을 수 없습니다.', 'danger')
        return redirect(url_for('tasks.task_list'))
    notes = task_repo.get_task_notes(task_id)
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/detail.html', task=task, assignees=assignees,
                           notes=notes, categories=categories, users=users)


@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
def edit_task(task_id):
    task, assignees = task_repo.get_task_by_id(task_id)
    if not task:
        return redirect(url_for('tasks.task_list'))
    if request.method == 'POST':
        assignee_ids = request.form.getlist('assignee_ids', type=int)
        task_repo.update_task(
            task_id=task_id,
            title=request.form['title'],
            description=request.form.get('description', ''),
            category_id=request.form.get('category_id', type=int),
            priority=request.form.get('priority', 'medium'),
            estimated_minutes=request.form.get('estimated_minutes', 60, type=int),
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
    return redirect(url_for('tasks.task_detail', task_id=task_id))
