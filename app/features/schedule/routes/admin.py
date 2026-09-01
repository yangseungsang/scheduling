"""
관리자 라우트 모듈.

시스템 설정을 위한 웹 페이지 라우트와 REST API 엔드포인트를 제공한다.
프로젝트 전체 리셋 기능도 포함한다.
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash

from app.features.schedule.services import settings

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


# ---------------------------------------------------------------------------
# 프로젝트 리셋 (전체 초기화)
# ---------------------------------------------------------------------------

@admin_bp.route('/api/project-reset', methods=['POST'])
def api_project_reset():
    """프로젝트 전체를 리셋한다: 시험 절차서, 블록, 실행 결과를 삭제한다.

    새 프로젝트(예: 2차 통합시험)를 시작할 때 사용한다.
    Returns:
        JSON: 성공 메시지
    """
    from app.repositories import get_repository
    from app.features.execution.domain import Executions
    from app.features.schedule.domain import Schedule

    repository = get_repository()
    repository.replace_all(
        test_procedures=(),
        schedule=Schedule(),
        executions=Executions(),
        settings=repository.load_settings(),
    )

    return jsonify({
        'success': True,
        'message': '프로젝트가 리셋되었습니다.',
    })
