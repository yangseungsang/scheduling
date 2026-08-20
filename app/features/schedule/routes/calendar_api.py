"""
캘린더 API 라우트 모듈.

스케줄 블록의 생성, 수정, 삭제, 잠금, 상태 변경, 분리, 일괄 이동 등
블록 관련 REST API 엔드포인트와 내보내기(CSV/XLSX) 기능을 제공한다.
"""

from datetime import datetime

from flask import current_app, request, jsonify, Response

from app.features.schedule.routes.calendar_views import schedule_bp
from app.features.schedule.services.blocks import (
    ScheduleBlockError,
    ScheduleBlockService,
    VALID_BLOCK_STATUSES,
)
from app.features.schedule.services.test_procedures import TestProcedureService
from app.repositories import JsonDomainRepository
from app.features.schedule.services.presentation import (
    build_export_blocks,
    schedule_settings,
)


def _schedule_service():
    """Create a schedule workflow service from the current app config."""
    return ScheduleBlockService(current_app.config['DOMAIN_DATA_DIR'])


def _schedule_error_response(exc):
    """Translate a business validation exception into a JSON response."""
    return jsonify({'error': str(exc)}), exc.status_code


def _schedule_settings():
    """Load settings and apply calendar defaults for command calculations."""
    settings = JsonDomainRepository(current_app.config['DOMAIN_DATA_DIR']).load_settings()
    return schedule_settings(settings)


@schedule_bp.route('/api/blocks', methods=['POST'])
def api_create_block():
    """새로운 스케줄 블록을 생성한다.

    일반 블록(시험 절차서 연결)과 간단 블록(제목만 있는 비시험 블록)을 모두 처리한다.

    Request Body (JSON):
        - is_simple (bool, optional): True이면 간단 블록으로 생성
        - procedure_id (str): 연결할 시험 절차서 ID (일반 블록 필수)
        - date (str): 배치 날짜 (YYYY-MM-DD, 필수)
        - start_time (str): 시작 시간 (HH:MM, 필수)
        - end_time (str): 종료 시간 (HH:MM, 필수)
        - assignee_names (list, optional): 담당자 ID 리스트
        - location_name (str, optional): 시험 장소 ID
        - test_item_ids (list, optional): 배치할 시험 항목 ID 리스트
        - overflow_minutes (int, optional): 초과 배치 시간(분)
        - is_locked (bool, optional): 잠금 여부
        - title (str, optional): 간단 블록 제목

    Returns:
        JSON: 생성된 블록 데이터 (201) 또는 에러 (400/409)
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    try:
        return jsonify(_schedule_service().create(data)), 201
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)


@schedule_bp.route('/api/blocks/<block_id>', methods=['PUT'])
def api_update_block(block_id):
    """기존 스케줄 블록을 수정한다.

    이동(드래그), 리사이즈, 상세 팝업 수정 등에서 호출된다.

    Args:
        block_id (str): 수정할 블록 ID

    Request Body (JSON):
        - date (str, optional): 변경할 날짜
        - start_time (str, optional): 변경할 시작 시간
        - end_time (str, optional): 변경할 종료 시간
        - is_locked (bool, optional): 잠금 상태
        - block_status (str, optional): 블록 상태
        - location_name (str, optional): 장소 ID
        - resize (bool, optional): 리사이즈 작업 여부
        - duration_minutes (int, optional): 상세 팝업에서 지정한 소요 시간(분)

    Returns:
        JSON: 수정된 블록 데이터 또는 에러 (404/409)
    """
    try:
        return jsonify(_schedule_service().update(block_id, request.get_json()))
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)


@schedule_bp.route('/api/blocks/<block_id>', methods=['DELETE'])
def api_delete_block(block_id):
    """스케줄 블록을 삭제한다.

    Args:
        block_id (str): 삭제할 블록 ID

    Query Parameters:
        restore (str, optional): '1'이면 시험 절차서의 장소 정보도 초기화 (큐로 복원)

    Returns:
        JSON: 성공 여부 또는 에러 (404)
    """
    try:
        return jsonify(_schedule_service().delete(
            block_id,
            restore=request.args.get('restore') == '1',
        ))
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)


@schedule_bp.route('/api/blocks/<block_id>/lock', methods=['PUT'])
def api_toggle_lock(block_id):
    """블록의 잠금 상태를 토글한다.

    잠금된 블록은 드래그 이동/리사이즈/일괄 이동에서 제외된다.

    Args:
        block_id (str): 대상 블록 ID

    Returns:
        JSON: 수정된 블록 데이터 또는 에러 (404)
    """
    try:
        return jsonify(_schedule_service().toggle_lock(block_id))
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)


@schedule_bp.route('/api/blocks/<block_id>/status', methods=['PUT'])
def api_update_block_status(block_id):
    """블록의 진행 상태를 변경한다.

    블록 상태 변경 시 해당 시험 절차서의 전체 상태도 자동 동기화된다.

    Args:
        block_id (str): 대상 블록 ID

    Request Body (JSON):
        - block_status (str): 변경할 상태 (pending/in_progress/completed/cancelled)

    Returns:
        JSON: 수정된 블록 데이터 또는 에러 (400/404)
    """
    data = request.get_json()
    if not data or 'block_status' not in data:
        return jsonify({'error': '상태 값이 필요합니다.'}), 400
    status = data['block_status']
    if status not in VALID_BLOCK_STATUSES:
        return jsonify({'error': '유효하지 않은 상태입니다.'}), 400
    try:
        return jsonify(_schedule_service().set_status(block_id, status))
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)


@schedule_bp.route('/api/simple-blocks', methods=['POST'])
def api_create_simple_block():
    """간단 블록용 시험 절차서를 생성한다.

    시험이 아닌 일반 작업(회의, 점검 등)을 큐에 추가할 때 사용한다.
    내부적으로 'BLK-' 접두사가 붙은 절차서 ID로 시험 절차서를 생성하고
    is_simple=True로 마킹한다.

    Request Body (JSON):
        - title (str): 블록 제목 (필수)
        - estimated_minutes (int, optional): 예상 소요 시간(분, 기본 60)

    Returns:
        JSON: 생성된 시험 절차서 데이터 (201) 또는 에러 (400)
    """
    data = request.get_json()
    if not data or not data.get('title', '').strip():
        return jsonify({'error': '제목을 입력해주세요.'}), 400
    title = data['title'].strip()
    minutes = int(data.get('estimated_minutes', 60))
    t = TestProcedureService(current_app.config['DOMAIN_DATA_DIR']).create_procedure({
        'document_id': int(str(int(__import__('time').time()))[-6:]),
        'assignee_names': [],
        'location_name': '',
        'document_name': title,
        'test_items': [],
        'estimated_minutes': minutes,
        'memo': '',
        'is_simple': True,
    })
    return jsonify(t), 201


@schedule_bp.route('/api/blocks/<block_id>/memo', methods=['PUT'])
def api_update_block_memo(block_id):
    """블록의 메모를 수정한다.

    블록 메모 변경 시 연결된 시험 절차서의 메모도 함께 갱신된다.

    Args:
        block_id (str): 대상 블록 ID

    Request Body (JSON):
        - memo (str): 메모 내용

    Returns:
        JSON: 수정된 블록 데이터 또는 에러 (400/404)
    """
    data = request.get_json()
    if data is None:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    try:
        return jsonify(_schedule_service().set_memo(block_id, data.get('memo', '')))
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)


@schedule_bp.route('/api/export')
def api_export():
    """스케줄 데이터를 CSV 또는 XLSX 형식으로 내보낸다.

    Query Parameters:
        start_date (str): 시작 날짜 (YYYY-MM-DD, 필수)
        end_date (str): 종료 날짜 (YYYY-MM-DD, 필수)
        format (str, optional): 내보내기 형식 ('csv' 또는 'xlsx', 기본 'csv')

    Returns:
        Response: CSV/XLSX 파일 다운로드 응답 또는 에러 (400)
    """
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    fmt = request.args.get('format', 'csv')

    if not start_date or not end_date:
        return jsonify({'error': 'start_date와 end_date는 필수입니다.'}), 400

    # 날짜 형식 유효성 검사
    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': '날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)'}), 400

    from app.features.schedule.services.export import export_xlsx, export_csv
    from urllib.parse import quote

    repository = JsonDomainRepository(current_app.config['DOMAIN_DATA_DIR'])
    operations = repository.load_operations()
    procedures = operations.test_procedures
    schedule = operations.schedule
    executions = operations.executions
    enriched = build_export_blocks(
        procedures, schedule, executions, start_date, end_date,
    )
    version_label = operations.version_id
    safe_version = version_label.replace('/', '_').replace('\\', '_')
    filename_base = (
        f'schedule_{safe_version}_{start_date}_{end_date}'
        if safe_version else f'schedule_{start_date}_{end_date}'
    )

    def _content_disposition(filename):
        """Build an RFC-compatible attachment header for non-ASCII filenames."""
        encoded = quote(filename, safe='')
        ascii_name = filename.encode('ascii', errors='ignore').decode()
        return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"

    if fmt == 'xlsx':
        try:
            data = export_xlsx(enriched, start_date, end_date, version_name=version_label)
            return Response(
                data,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': _content_disposition(f'{filename_base}.xlsx')},
            )
        except ImportError:
            current_app.logger.warning('openpyxl 없음 - CSV로 대체')
        except Exception:
            current_app.logger.exception('xlsx 생성 실패 - CSV로 대체')

    return Response(
        export_csv(enriched),
        content_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': _content_disposition(f'{filename_base}.csv')},
    )


@schedule_bp.route('/api/blocks/by-procedure/<procedure_id>')
def api_blocks_by_procedure(procedure_id):
    """특정 시험 절차서에 연결된 모든 블록을 조회한다.

    분할 블록의 시험 항목 배분 현황을 확인할 때 사용된다.

    Args:
        procedure_id (str): 조회할 시험 절차서 ID

    Returns:
        JSON: 해당 시험 절차서의 블록 리스트 (test_item_ids 포함)
    """
    return jsonify(_schedule_service().list_by_procedure(procedure_id))


@schedule_bp.route('/api/blocks/shift', methods=['POST'])
def api_shift_blocks():
    """지정 날짜 이후의 모든 블록을 +1일 또는 -1일 이동한다.

    주말(토/일)은 자동으로 건너뛴다.
    잠금된 블록(is_locked=True)은 이동에서 제외된다.

    Request Body (JSON):
        - from_date (str): 기준 날짜 (이 날짜 이후 블록만 이동, 필수)
        - direction (int, optional): 이동 방향 (1=미래, -1=과거, 기본 1)

    Returns:
        JSON: 성공 여부 및 이동된 블록 수
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    from_date = data.get('from_date', '')
    direction = data.get('direction', 1)

    if not from_date:
        return jsonify({'error': 'from_date는 필수입니다.'}), 400
    try:
        return jsonify(_schedule_service().shift(from_date, direction))
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)


@schedule_bp.route('/api/blocks/<block_id>/split', methods=['POST'])
def api_split_block(block_id):
    """블록을 시험 항목 기준으로 두 개로 분리한다.

    선택한 시험 항목는 원래 블록에 유지되고,
    나머지 시험 항목는 원래 블록 바로 뒤에 새 블록으로 생성된다.

    Args:
        block_id (str): 분리할 블록 ID

    Request Body (JSON):
        - keep_test_item_ids (list): 원래 블록에 유지할 시험 항목 ID 리스트

    Returns:
        JSON: 성공 여부 및 새로 생성된 블록 데이터 또는 에러 (400/404/409)
    """
    data = request.get_json() or {}
    try:
        return jsonify(_schedule_service().split(
            block_id,
            data.get('keep_test_item_ids', []),
            _schedule_settings(),
        ))
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)


@schedule_bp.route('/api/blocks/<block_id>/return-test_items', methods=['POST'])
def api_return_test_items_to_queue(block_id):
    """블록에서 선택한 시험 항목를 큐로 되돌린다.

    유지할 시험 항목만 블록에 남기고, 나머지는 미배치 상태로 전환한다.
    유지 시험 항목가 없으면 블록 자체를 삭제한다.

    Args:
        block_id (str): 대상 블록 ID

    Request Body (JSON):
        - keep_test_item_ids (list): 블록에 남길 시험 항목 ID 목록

    Returns:
        JSON: 성공 여부
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    try:
        return jsonify(_schedule_service().return_test_items(
            block_id,
            data.get('keep_test_item_ids', []),
            _schedule_settings(),
        ))
    except ScheduleBlockError as exc:
        return _schedule_error_response(exc)
