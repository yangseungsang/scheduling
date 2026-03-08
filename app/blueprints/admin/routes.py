from flask import Blueprint, render_template, request, redirect, url_for, flash

from app.repositories import user_repo, category_repo, settings_repo

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        data = {
            'work_start': request.form['work_start'],
            'work_end': request.form['work_end'],
            'lunch_start': request.form['lunch_start'],
            'lunch_end': request.form['lunch_end'],
            'grid_interval_minutes': int(request.form.get('grid_interval_minutes', 15)),
            'max_schedule_days': int(request.form.get('max_schedule_days', 14)),
            'block_color_by': request.form.get('block_color_by', 'assignee'),
        }
        # Parse breaks
        break_starts = request.form.getlist('break_start')
        break_ends = request.form.getlist('break_end')
        data['breaks'] = [
            {'start': s, 'end': e}
            for s, e in zip(break_starts, break_ends)
            if s and e
        ]
        settings_repo.update(data)
        flash('설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings'))
    return render_template('admin/settings.html', settings=settings_repo.get())


@admin_bp.route('/users')
def users():
    return render_template('admin/users.html', users=user_repo.get_all())


@admin_bp.route('/users/new', methods=['GET', 'POST'])
def user_new():
    if request.method == 'POST':
        user_repo.create(
            name=request.form['name'],
            role=request.form['role'],
            color=request.form['color'],
        )
        flash('팀원이 추가되었습니다.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=None)


@admin_bp.route('/users/<user_id>/edit', methods=['GET', 'POST'])
def user_edit(user_id):
    user = user_repo.get_by_id(user_id)
    if not user:
        flash('팀원을 찾을 수 없습니다.', 'danger')
        return redirect(url_for('admin.users'))
    if request.method == 'POST':
        user_repo.update(
            user_id,
            name=request.form['name'],
            role=request.form['role'],
            color=request.form['color'],
        )
        flash('팀원 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=user)


@admin_bp.route('/users/<user_id>/delete', methods=['POST'])
def user_delete(user_id):
    user_repo.delete(user_id)
    flash('팀원이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/categories')
def categories():
    return render_template('admin/categories.html', categories=category_repo.get_all())


@admin_bp.route('/categories/new', methods=['GET', 'POST'])
def category_new():
    if request.method == 'POST':
        category_repo.create(
            name=request.form['name'],
            color=request.form['color'],
        )
        flash('카테고리가 추가되었습니다.', 'success')
        return redirect(url_for('admin.categories'))
    return render_template('admin/category_form.html', category=None)


@admin_bp.route('/categories/<cat_id>/edit', methods=['GET', 'POST'])
def category_edit(cat_id):
    cat = category_repo.get_by_id(cat_id)
    if not cat:
        flash('카테고리를 찾을 수 없습니다.', 'danger')
        return redirect(url_for('admin.categories'))
    if request.method == 'POST':
        category_repo.update(
            cat_id,
            name=request.form['name'],
            color=request.form['color'],
        )
        flash('카테고리가 수정되었습니다.', 'success')
        return redirect(url_for('admin.categories'))
    return render_template('admin/category_form.html', category=cat)


@admin_bp.route('/categories/<cat_id>/delete', methods=['POST'])
def category_delete(cat_id):
    category_repo.delete(cat_id)
    flash('카테고리가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.categories'))
