from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash

from schedule.models import user, location, version, settings

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _snap_time(time_str, interval=15):
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
# Settings
# ---------------------------------------------------------------------------

@admin_bp.route('/settings', methods=['GET', 'POST'], endpoint='settings')
def settings_page():
    if request.method == 'POST':
        grid = int(request.form.get('grid_interval_minutes', 15))
        data = {
            'work_start': _snap_time(request.form['work_start'], grid),
            'work_end': _snap_time(request.form['work_end'], grid),
            'actual_work_start': _snap_time(request.form.get('actual_work_start', '08:30'), grid),
            'actual_work_end': _snap_time(request.form.get('actual_work_end', '16:30'), grid),
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
        settings.update(data)
        flash('설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings'))
    return render_template('admin/settings.html', settings=settings.get())


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@admin_bp.route('/users')
def users():
    return render_template('admin/users.html', users=user.get_all())


@admin_bp.route('/users/new', methods=['GET', 'POST'])
def user_new():
    if request.method == 'POST':
        user.create(
            name=request.form['name'],
            role=request.form['role'],
            color=request.form['color'],
        )
        flash('팀원이 추가되었습니다.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=None)


@admin_bp.route('/users/<user_id>/edit', methods=['GET', 'POST'])
def user_edit(user_id):
    u = user.get_by_id(user_id)
    if not u:
        flash('팀원을 찾을 수 없습니다.', 'danger')
        return redirect(url_for('admin.users'))
    if request.method == 'POST':
        user.update(
            user_id,
            name=request.form['name'],
            role=request.form['role'],
            color=request.form['color'],
        )
        flash('팀원 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=u)


@admin_bp.route('/users/<user_id>/delete', methods=['POST'])
def user_delete(user_id):
    user.delete(user_id)
    flash('팀원이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.users'))


# ---------------------------------------------------------------------------
# Locations (replaces categories)
# ---------------------------------------------------------------------------

@admin_bp.route('/locations')
def locations():
    return render_template('admin/locations.html', locations=location.get_all())


@admin_bp.route('/locations/new', methods=['GET', 'POST'])
def location_new():
    if request.method == 'POST':
        location.create(
            name=request.form['name'],
            color=request.form['color'],
            description=request.form.get('description', ''),
        )
        flash('시험장소가 추가되었습니다.', 'success')
        return redirect(url_for('admin.locations'))
    return render_template('admin/location_form.html', location=None)


@admin_bp.route('/locations/<loc_id>/edit', methods=['GET', 'POST'])
def location_edit(loc_id):
    loc = location.get_by_id(loc_id)
    if not loc:
        flash('시험장소를 찾을 수 없습니다.', 'danger')
        return redirect(url_for('admin.locations'))
    if request.method == 'POST':
        location.update(
            loc_id,
            name=request.form['name'],
            color=request.form['color'],
            description=request.form.get('description', ''),
        )
        flash('시험장소가 수정되었습니다.', 'success')
        return redirect(url_for('admin.locations'))
    return render_template('admin/location_form.html', location=loc)


@admin_bp.route('/locations/<loc_id>/delete', methods=['POST'])
def location_delete(loc_id):
    location.delete(loc_id)
    flash('시험장소가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.locations'))


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

@admin_bp.route('/versions')
def versions():
    return render_template('admin/versions.html', versions=version.get_all())


@admin_bp.route('/versions/new', methods=['GET', 'POST'])
def version_new():
    if request.method == 'POST':
        version.create(
            name=request.form['name'],
            description=request.form.get('description', ''),
        )
        flash('버전이 추가되었습니다.', 'success')
        return redirect(url_for('admin.versions'))
    return render_template('admin/version_form.html', version=None)


@admin_bp.route('/versions/<version_id>/edit', methods=['GET', 'POST'])
def version_edit(version_id):
    v = version.get_by_id(version_id)
    if not v:
        flash('버전을 찾을 수 없습니다.', 'danger')
        return redirect(url_for('admin.versions'))
    if request.method == 'POST':
        version.update(
            version_id,
            name=request.form['name'],
            description=request.form.get('description', ''),
            is_active='is_active' in request.form,
        )
        flash('버전 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin.versions'))
    return render_template('admin/version_form.html', version=v)


@admin_bp.route('/versions/<version_id>/delete', methods=['POST'])
def version_delete(version_id):
    version.delete(version_id)
    flash('버전이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.versions'))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@admin_bp.route('/api/settings')
def api_get_settings():
    return jsonify(settings.get())


@admin_bp.route('/api/settings', methods=['PUT'])
def api_update_settings():
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    updated = settings.update(data)
    return jsonify(updated)


@admin_bp.route('/api/users')
def api_get_users():
    return jsonify(user.get_all())


@admin_bp.route('/api/users', methods=['POST'])
def api_create_user():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': '이름을 입력해주세요.'}), 400
    u = user.create(
        name=data['name'],
        role=data.get('role', ''),
        color=data.get('color', '#4A90D9'),
    )
    return jsonify(u), 201


@admin_bp.route('/api/users/<user_id>', methods=['PUT'])
def api_update_user(user_id):
    u = user.get_by_id(user_id)
    if not u:
        return jsonify({'error': '팀원을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    updated = user.update(
        user_id,
        name=data.get('name', u['name']),
        role=data.get('role', u['role']),
        color=data.get('color', u['color']),
    )
    return jsonify(updated)


@admin_bp.route('/api/users/<user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    user.delete(user_id)
    return jsonify({'success': True})


@admin_bp.route('/api/locations')
def api_get_locations():
    return jsonify(location.get_all())


@admin_bp.route('/api/locations', methods=['POST'])
def api_create_location():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': '이름을 입력해주세요.'}), 400
    loc = location.create(
        name=data['name'],
        color=data.get('color', '#28a745'),
        description=data.get('description', ''),
    )
    return jsonify(loc), 201


@admin_bp.route('/api/locations/<loc_id>', methods=['PUT'])
def api_update_location(loc_id):
    loc = location.get_by_id(loc_id)
    if not loc:
        return jsonify({'error': '시험장소를 찾을 수 없습니다.'}), 404
    data = request.get_json()
    updated = location.update(
        loc_id,
        name=data.get('name', loc['name']),
        color=data.get('color', loc['color']),
        description=data.get('description', loc.get('description', '')),
    )
    return jsonify(updated)


@admin_bp.route('/api/locations/<loc_id>', methods=['DELETE'])
def api_delete_location(loc_id):
    location.delete(loc_id)
    return jsonify({'success': True})


@admin_bp.route('/api/versions')
def api_get_versions():
    return jsonify(version.get_all())


@admin_bp.route('/api/versions', methods=['POST'])
def api_create_version():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': '버전명을 입력해주세요.'}), 400
    v = version.create(
        name=data['name'],
        description=data.get('description', ''),
    )
    return jsonify(v), 201


@admin_bp.route('/api/versions/<version_id>', methods=['PUT'])
def api_update_version(version_id):
    v = version.get_by_id(version_id)
    if not v:
        return jsonify({'error': '버전을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    updated = version.update(
        version_id,
        name=data.get('name', v['name']),
        description=data.get('description', v.get('description', '')),
        is_active=data.get('is_active', v.get('is_active', True)),
    )
    return jsonify(updated)


@admin_bp.route('/api/versions/<version_id>', methods=['DELETE'])
def api_delete_version(version_id):
    version.delete(version_id)
    return jsonify({'success': True})
