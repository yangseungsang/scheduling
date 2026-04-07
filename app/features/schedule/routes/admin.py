"""
관리자 라우트 모듈.

시스템 설정, 팀원(사용자), 시험 장소, 버전 관리를 위한
웹 페이지 라우트와 REST API 엔드포인트를 제공한다.
프로젝트 전체 리셋 기능도 포함한다.
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash

from app.features.schedule.models import user, location, version, settings
from app.features.schedule.store import write_json

# 관리자 기능이 등록되는 블루프린트
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _snap_time(time_str, interval=15):
    """시간 문자열을 지정된 간격(분)에 맞게 반올림한다.

    예: interval=15일 때 '08:07' → '08:00', '08:08' → '08:15'

    Args:
        time_str (str): 시간 문자열 (HH:MM 형식)
        interval (int): 스냅할 시간 간격(분, 기본 15)

    Returns:
        str: 간격에 맞게 반올림된 시간 문자열 (HH:MM)
    """
    if not time_str or ':' not in time_str:
        return time_str
    parts = time_str.split(':')
    h, m = int(parts[0]), int(parts[1])
    # 분을 지정 간격으로 반올림
    m = round(m / interval) * interval
    # 60분 이상이면 시간 올림
    if m >= 60:
        h += 1
        m = 0
    return f'{h:02d}:{m:02d}'


# ---------------------------------------------------------------------------
# 설정 관리
# ---------------------------------------------------------------------------

@admin_bp.route('/settings', methods=['GET', 'POST'], endpoint='settings')
def settings_page():
    """시스템 설정 페이지를 렌더링하거나 설정을 저장한다.

    관리 가능한 설정 항목:
    - 근무 시간 (표시 범위 및 실제 근무 시간)
    - 점심 시간
    - 추가 휴식 시간 (복수)
    - 그리드 간격(분)
    - 최대 스케줄 일수
    - 블록 색상 기준 (담당자/장소)

    Returns:
        GET: 설정 페이지 HTML
        POST: 저장 후 설정 페이지로 리다이렉트
    """
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
        # 추가 휴식 시간 파싱 (동적으로 추가된 폼 필드)
        break_starts = request.form.getlist('break_start')
        break_ends = request.form.getlist('break_end')
        data['breaks'] = [
            {'start': _snap_time(s, grid), 'end': _snap_time(e, grid)}
            for s, e in zip(break_starts, break_ends)
            if s and e  # 시작/종료 모두 입력된 항목만 포함
        ]
        settings.update(data)
        flash('설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings'))
    return render_template('schedule/admin/settings.html', settings=settings.get())


# ---------------------------------------------------------------------------
# 팀원(사용자) 관리
# ---------------------------------------------------------------------------

@admin_bp.route('/users')
def users():
    """팀원 목록 페이지를 렌더링한다.

    Returns:
        렌더링된 팀원 목록 HTML
    """
    return render_template('schedule/admin/users.html', users=user.get_all())


@admin_bp.route('/users/new', methods=['GET', 'POST'])
def user_new():
    """새 팀원 추가 페이지를 렌더링하거나 생성 요청을 처리한다.

    Returns:
        GET: 빈 팀원 생성 폼 HTML
        POST: 생성 후 팀원 목록으로 리다이렉트
    """
    if request.method == 'POST':
        user.create(
            name=request.form['name'],
            role=request.form['role'],
            color=request.form['color'],
        )
        flash('팀원이 추가되었습니다.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('schedule/admin/user_form.html', user=None)


@admin_bp.route('/users/<user_id>/edit', methods=['GET', 'POST'])
def user_edit(user_id):
    """팀원 수정 페이지를 렌더링하거나 수정 요청을 처리한다.

    Args:
        user_id (str): 수정할 팀원 ID

    Returns:
        GET: 기존 데이터가 채워진 수정 폼 HTML
        POST: 수정 후 팀원 목록으로 리다이렉트
    """
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
    return render_template('schedule/admin/user_form.html', user=u)


@admin_bp.route('/users/<user_id>/delete', methods=['POST'])
def user_delete(user_id):
    """팀원을 삭제한다.

    Args:
        user_id (str): 삭제할 팀원 ID

    Returns:
        팀원 목록으로 리다이렉트
    """
    user.delete(user_id)
    flash('팀원이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.users'))


# ---------------------------------------------------------------------------
# 시험 장소 관리
# ---------------------------------------------------------------------------

@admin_bp.route('/locations')
def locations():
    """시험 장소 목록 페이지를 렌더링한다.

    Returns:
        렌더링된 장소 목록 HTML
    """
    return render_template('schedule/admin/locations.html', locations=location.get_all())


@admin_bp.route('/locations/new', methods=['GET', 'POST'])
def location_new():
    """새 시험 장소 추가 페이지를 렌더링하거나 생성 요청을 처리한다.

    Returns:
        GET: 빈 장소 생성 폼 HTML
        POST: 생성 후 장소 목록으로 리다이렉트
    """
    if request.method == 'POST':
        location.create(
            name=request.form['name'],
            color=request.form['color'],
            description=request.form.get('description', ''),
        )
        flash('시험장소가 추가되었습니다.', 'success')
        return redirect(url_for('admin.locations'))
    return render_template('schedule/admin/location_form.html', location=None)


@admin_bp.route('/locations/<loc_id>/edit', methods=['GET', 'POST'])
def location_edit(loc_id):
    """시험 장소 수정 페이지를 렌더링하거나 수정 요청을 처리한다.

    Args:
        loc_id (str): 수정할 장소 ID

    Returns:
        GET: 기존 데이터가 채워진 수정 폼 HTML
        POST: 수정 후 장소 목록으로 리다이렉트
    """
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
    return render_template('schedule/admin/location_form.html', location=loc)


@admin_bp.route('/locations/<loc_id>/delete', methods=['POST'])
def location_delete(loc_id):
    """시험 장소를 삭제한다.

    Args:
        loc_id (str): 삭제할 장소 ID

    Returns:
        장소 목록으로 리다이렉트
    """
    location.delete(loc_id)
    flash('시험장소가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.locations'))


# ---------------------------------------------------------------------------
# API 라우트 (JSON 응답)
# ---------------------------------------------------------------------------

@admin_bp.route('/api/settings')
def api_get_settings():
    """현재 시스템 설정을 JSON으로 반환한다.

    Returns:
        JSON: 시스템 설정 딕셔너리
    """
    return jsonify(settings.get())


@admin_bp.route('/api/settings', methods=['PUT'])
def api_update_settings():
    """API를 통해 시스템 설정을 업데이트한다.

    Request Body (JSON): 변경할 설정 키-값 쌍

    Returns:
        JSON: 업데이트된 설정 또는 에러 (400)
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    updated = settings.update(data)
    return jsonify(updated)


@admin_bp.route('/api/users')
def api_get_users():
    """전체 팀원 목록을 JSON으로 반환한다.

    Returns:
        JSON: 팀원 리스트
    """
    return jsonify(user.get_all())


@admin_bp.route('/api/users', methods=['POST'])
def api_create_user():
    """API를 통해 새 팀원을 생성한다.

    Request Body (JSON):
        - name (str): 팀원명 (필수)
        - role (str, optional): 역할
        - color (str, optional): 표시 색상 (기본 '#4A90D9')

    Returns:
        JSON: 생성된 팀원 데이터 (201) 또는 에러 (400)
    """
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
    """API를 통해 팀원 정보를 수정한다.

    Args:
        user_id (str): 수정할 팀원 ID

    Request Body (JSON): 변경할 필드 (name, role, color)

    Returns:
        JSON: 수정된 팀원 데이터 또는 에러 (404)
    """
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
    """API를 통해 팀원을 삭제한다.

    Args:
        user_id (str): 삭제할 팀원 ID

    Returns:
        JSON: 성공 여부
    """
    user.delete(user_id)
    return jsonify({'success': True})


@admin_bp.route('/api/locations')
def api_get_locations():
    """전체 시험 장소 목록을 JSON으로 반환한다.

    Returns:
        JSON: 장소 리스트
    """
    return jsonify(location.get_all())


@admin_bp.route('/api/locations', methods=['POST'])
def api_create_location():
    """API를 통해 새 시험 장소를 생성한다.

    Request Body (JSON):
        - name (str): 장소명 (필수)
        - color (str, optional): 표시 색상 (기본 '#28a745')
        - description (str, optional): 설명

    Returns:
        JSON: 생성된 장소 데이터 (201) 또는 에러 (400)
    """
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
    """API를 통해 시험 장소를 수정한다.

    Args:
        loc_id (str): 수정할 장소 ID

    Request Body (JSON): 변경할 필드 (name, color, description)

    Returns:
        JSON: 수정된 장소 데이터 또는 에러 (404)
    """
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
    """API를 통해 시험 장소를 삭제한다.

    Args:
        loc_id (str): 삭제할 장소 ID

    Returns:
        JSON: 성공 여부
    """
    location.delete(loc_id)
    return jsonify({'success': True})


@admin_bp.route('/api/versions')
def api_get_versions():
    """전체 버전 목록을 JSON으로 반환한다.

    Returns:
        JSON: 버전 리스트
    """
    return jsonify(version.get_all())


@admin_bp.route('/api/versions', methods=['POST'])
def api_create_version():
    """API를 통해 새 버전을 생성한다.

    Request Body (JSON):
        - name (str): 버전명 (필수)
        - description (str, optional): 설명

    Returns:
        JSON: 생성된 버전 데이터 (201) 또는 에러 (400)
    """
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
    """API를 통해 버전을 수정한다.

    Args:
        version_id (str): 수정할 버전 ID

    Request Body (JSON): 변경할 필드 (name, description, is_active)

    Returns:
        JSON: 수정된 버전 데이터 또는 에러 (404)
    """
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
    """API를 통해 버전을 삭제한다.

    Args:
        version_id (str): 삭제할 버전 ID

    Returns:
        JSON: 성공 여부
    """
    version.delete(version_id)
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# 프로젝트 리셋 (전체 초기화)
# ---------------------------------------------------------------------------

@admin_bp.route('/api/project-reset', methods=['POST'])
def api_project_reset():
    """프로젝트 전체를 리셋한다: 태스크, 블록, 버전을 모두 삭제한다.

    새 프로젝트(예: 2차 통합시험)를 시작할 때 사용한다.
    선택적으로 리셋 후 새 버전을 생성할 수 있다.

    Request Body (JSON, optional):
        - version_name (str): 생성할 새 버전명
        - version_description (str): 새 버전 설명

    Returns:
        JSON: 성공 메시지 및 새 버전 정보 (있는 경우)
    """
    # 모든 데이터 파일을 빈 배열로 초기화
    write_json('tasks.json', [])
    write_json('schedule_blocks.json', [])
    write_json('versions.json', [])

    data = request.get_json(silent=True) or {}
    new_version = None
    # 버전명이 제공되면 새 버전 생성
    if data.get('version_name'):
        new_version = version.create(
            name=data['version_name'],
            description=data.get('version_description', ''),
        )

    return jsonify({
        'success': True,
        'message': '프로젝트가 리셋되었습니다.',
        'version': new_version,
    })
