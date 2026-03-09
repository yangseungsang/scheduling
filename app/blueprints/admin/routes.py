from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash

from app.repositories import user_repo, category_repo, settings_repo

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _snap_time(time_str, interval=15):
    """Snap a time string to the nearest grid interval."""
    if not time_str or ':' not in time_str:
        return time_str
    parts = time_str.split(':')
    h, m = int(parts[0]), int(parts[1])
    m = round(m / interval) * interval
    if m >= 60:
        h += 1
        m = 0
    return f'{h:02d}:{m:02d}'


# ---------------------------------------------------------------------------
# Template rendering routes
# ---------------------------------------------------------------------------

@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        grid = int(request.form.get('grid_interval_minutes', 15))
        data = {
            'work_start': _snap_time(request.form['work_start'], grid),
            'work_end': _snap_time(request.form['work_end'], grid),
            'lunch_start': _snap_time(request.form['lunch_start'], grid),
            'lunch_end': _snap_time(request.form['lunch_end'], grid),
            'grid_interval_minutes': grid,
            'max_schedule_days': int(request.form.get('max_schedule_days', 14)),
            'block_color_by': request.form.get('block_color_by', 'assignee'),
        }
        break_starts = request.form.getlist('break_start')
        break_ends = request.form.getlist('break_end')
        data['breaks'] = [
            {'start': _snap_time(s, grid), 'end': _snap_time(e, grid)}
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


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@admin_bp.route('/api/settings')
def api_get_settings():
    return jsonify(settings_repo.get())


@admin_bp.route('/api/settings', methods=['PUT'])
def api_update_settings():
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    updated = settings_repo.update(data)
    return jsonify(updated)


@admin_bp.route('/api/users')
def api_get_users():
    return jsonify(user_repo.get_all())


@admin_bp.route('/api/users', methods=['POST'])
def api_create_user():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': '이름을 입력해주세요.'}), 400
    user = user_repo.create(
        name=data['name'],
        role=data.get('role', ''),
        color=data.get('color', '#4A90D9'),
    )
    return jsonify(user), 201


@admin_bp.route('/api/users/<user_id>', methods=['PUT'])
def api_update_user(user_id):
    user = user_repo.get_by_id(user_id)
    if not user:
        return jsonify({'error': '팀원을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    updated = user_repo.update(
        user_id,
        name=data.get('name', user['name']),
        role=data.get('role', user['role']),
        color=data.get('color', user['color']),
    )
    return jsonify(updated)


@admin_bp.route('/api/users/<user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    user_repo.delete(user_id)
    return jsonify({'success': True})


@admin_bp.route('/api/categories')
def api_get_categories():
    return jsonify(category_repo.get_all())


@admin_bp.route('/api/categories', methods=['POST'])
def api_create_category():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': '이름을 입력해주세요.'}), 400
    cat = category_repo.create(
        name=data['name'],
        color=data.get('color', '#28a745'),
    )
    return jsonify(cat), 201


@admin_bp.route('/api/categories/<cat_id>', methods=['PUT'])
def api_update_category(cat_id):
    cat = category_repo.get_by_id(cat_id)
    if not cat:
        return jsonify({'error': '카테고리를 찾을 수 없습니다.'}), 404
    data = request.get_json()
    updated = category_repo.update(
        cat_id,
        name=data.get('name', cat['name']),
        color=data.get('color', cat['color']),
    )
    return jsonify(updated)


@admin_bp.route('/api/categories/<cat_id>', methods=['DELETE'])
def api_delete_category(cat_id):
    category_repo.delete(cat_id)
    return jsonify({'success': True})
