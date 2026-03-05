import re
from flask import render_template, request, redirect, url_for, flash, abort
from app.blueprints.admin import admin_bp
from app.repositories import settings_repo, user_repo, category_repo

_TIME_RE = re.compile(r'^\d{2}:\d{2}$')
_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


@admin_bp.route('/')
def index():
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        for key in ['work_start', 'work_end', 'lunch_start', 'lunch_end']:
            value = request.form.get(key, '').strip()
            if value:
                if not _TIME_RE.match(value):
                    flash(f'{key} 형식이 올바르지 않습니다 (HH:MM).', 'danger')
                    return redirect(url_for('admin.settings'))
                settings_repo.update_setting(key, value)
        flash('설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings'))
    work_hours = settings_repo.get_work_hours()
    return render_template('admin/settings.html', work_hours=work_hours)


@admin_bp.route('/users')
def user_list():
    users = user_repo.get_all_users()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
def create_user():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        if not name:
            flash('사용자 이름은 필수입니다.', 'danger')
            return redirect(url_for('admin.create_user'))
        if not email:
            flash('이메일은 필수입니다.', 'danger')
            return redirect(url_for('admin.create_user'))
        role = request.form.get('role', 'member')
        if role not in ('admin', 'member'):
            role = 'member'
        user_repo.create_user(name=name, email=email, role=role)
        flash('사용자가 추가되었습니다.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('admin/user_form.html', user=None)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    user = user_repo.get_user_by_id(user_id)
    if not user:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        if not name:
            flash('사용자 이름은 필수입니다.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        if not email:
            flash('이메일은 필수입니다.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        role = request.form.get('role', 'member')
        if role not in ('admin', 'member'):
            role = 'member'
        user_repo.update_user(user_id=user_id, name=name, email=email, role=role)
        flash('사용자 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('admin/user_form.html', user=user)


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    user_repo.delete_user(user_id)
    flash('사용자가 삭제되었습니다.', 'info')
    return redirect(url_for('admin.user_list'))


@admin_bp.route('/categories')
def category_list():
    categories = category_repo.get_all_categories()
    return render_template('admin/categories.html', categories=categories)


@admin_bp.route('/categories/new', methods=['GET', 'POST'])
def create_category():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('카테고리 이름은 필수입니다.', 'danger')
            return redirect(url_for('admin.create_category'))
        color = request.form.get('color', '#4A90E2')
        if not _COLOR_RE.match(color):
            color = '#4A90E2'
        category_repo.create_category(name=name, color=color)
        flash('카테고리가 추가되었습니다.', 'success')
        return redirect(url_for('admin.category_list'))
    return render_template('admin/category_form.html', category=None)


@admin_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
def edit_category(category_id):
    category = category_repo.get_category_by_id(category_id)
    if not category:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('카테고리 이름은 필수입니다.', 'danger')
            return redirect(url_for('admin.edit_category', category_id=category_id))
        color = request.form.get('color', '#4A90E2')
        if not _COLOR_RE.match(color):
            color = '#4A90E2'
        category_repo.update_category(category_id=category_id, name=name, color=color)
        flash('카테고리가 수정되었습니다.', 'success')
        return redirect(url_for('admin.category_list'))
    return render_template('admin/category_form.html', category=category)


@admin_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
def delete_category(category_id):
    category_repo.delete_category(category_id)
    flash('카테고리가 삭제되었습니다.', 'info')
    return redirect(url_for('admin.category_list'))
