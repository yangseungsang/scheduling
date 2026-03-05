from flask import render_template, request, redirect, url_for, flash
from app.blueprints.admin import admin_bp
from app.repositories import settings_repo, user_repo, category_repo


@admin_bp.route('/')
def index():
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        for key in ['work_start', 'work_end', 'lunch_start', 'lunch_end']:
            value = request.form.get(key)
            if value:
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
        user_repo.create_user(
            name=request.form['name'],
            email=request.form['email'],
            role=request.form.get('role', 'member'),
        )
        flash('사용자가 추가되었습니다.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('admin/user_form.html', user=None)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    user = user_repo.get_user_by_id(user_id)
    if request.method == 'POST':
        user_repo.update_user(
            user_id=user_id,
            name=request.form['name'],
            email=request.form['email'],
            role=request.form.get('role', 'member'),
        )
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
        category_repo.create_category(
            name=request.form['name'],
            color=request.form.get('color', '#4A90E2'),
        )
        flash('카테고리가 추가되었습니다.', 'success')
        return redirect(url_for('admin.category_list'))
    return render_template('admin/category_form.html', category=None)


@admin_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
def edit_category(category_id):
    category = category_repo.get_category_by_id(category_id)
    if request.method == 'POST':
        category_repo.update_category(
            category_id=category_id,
            name=request.form['name'],
            color=request.form.get('color', '#4A90E2'),
        )
        flash('카테고리가 수정되었습니다.', 'success')
        return redirect(url_for('admin.category_list'))
    return render_template('admin/category_form.html', category=category)


@admin_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
def delete_category(category_id):
    category_repo.delete_category(category_id)
    flash('카테고리가 삭제되었습니다.', 'info')
    return redirect(url_for('admin.category_list'))
