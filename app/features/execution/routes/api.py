"""
시험실행(Execution) REST API 블루프린트.

URL 접두사: /execution/api

이 모듈은 시험 실행의 전체 생명주기를 HTTP 엔드포인트로 노출한다.
- 실행 목록 조회 (/list, /item/<id>)
- 상태 전이 (/start, /pause, /resume, /complete, /reset)
- 메타데이터 갱신 (/comment, /pending-comment, /performer)
- 외부 연동 (/timing/<id>)

데이터 흐름:
    routes/api.py는 HTTP 요청·응답만 처리한다.
    실행 목록/상세 조회 조립은 services/listing.py가 담당하고,
    실행 상태 변경은 ExecutionRepository가 담당한다.
"""

import logging
import os
import threading

import requests
from flask import Blueprint, jsonify, request, session

from app.features.execution.repository import ExecutionRepository
from app.repositories import get_repository
from app.features.execution.services.listing import (
    build_daily_procedure_metrics,
    build_execution_item,
    build_execution_items,
    get_total_count,
)

api_bp = Blueprint('execution_api', __name__, url_prefix='/execution/api')

logger = logging.getLogger(__name__)


@api_bp.route('/analytics/daily-procedures')
def daily_procedure_metrics():
    """Return daily unique-procedure plan and execution metrics for charting."""
    try:
        return jsonify(build_daily_procedure_metrics(
            request.args.get('start_date', ''),
            request.args.get('end_date', ''),
        ))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


def _notify_timing(test_item_id: str, procedure_id: str, elapsed_seconds: int):
    """시험완료 후 외부 서버에 소요시간을 비동기로 전송한다.

    완료 API 응답 지연을 막기 위해 daemon 스레드에서 실행한다.
    API_BASE_URL 환경변수가 없으면 즉시 반환하여 내부 전용 배포에서는 동작하지 않는다.

    전송 실패는 경고 로그만 남기고 예외를 전파하지 않는다.
    (시험 완료 자체는 이미 저장됐으므로 알림 실패가 치명적이지 않다.)
    """
    base_url = os.environ.get('API_BASE_URL', '').rstrip('/')
    if not base_url:
        return
    version_id = get_repository().load_plan().version_id

    def _send():
        """Run the optional provider notification outside the request thread."""
        try:
            api_key = os.environ.get('API_KEY', '')
            headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
            resp = requests.post(
                f'{base_url}/update_test_time',
                json={
                    'test_id': test_item_id,
                    'ofp_id': version_id,
                    'time_taking': int(elapsed_seconds),
                },
                headers=headers,
                timeout=10,
            )
            if not resp.ok:
                logger.warning('update_test_time 실패: %s %s', resp.status_code, resp.text)
        except Exception as e:
            logger.warning('update_test_time 전송 오류: %s', e)

    threading.Thread(target=_send, daemon=True).start()


@api_bp.route('/list')
def execution_list():
    """전체 시험 항목 목록을 실행 상태와 함께 반환한다.

    쿼리 파라미터:
        date     (str): YYYY-MM-DD 형식. 해당 날짜에 배치된 시험 항목만 반환
        location (str): location_name. 해당 장소의 시험 항목만 반환
        status   (str): pending, in_progress, paused, completed 중 하나
        procedure_id  (str): 선택한 문서 작업 ID

    장소 필터는 블록 장소 우선, 없으면 시험 절차서 장소 기준으로 적용한다.
    """
    date_filter = request.args.getlist('date')
    location_filter = request.args.getlist('location')
    status_filter = request.args.getlist('status')
    procedure_filter = request.args.getlist('procedure_id')

    return jsonify(build_execution_items(
        date_filter, location_filter, status_filter, procedure_filter,
    ))


@api_bp.route('/item/<test_item_id>')
def get_item(test_item_id):
    """단일 시험 항목의 상세 실행 정보를 반환한다."""
    item = build_execution_item(test_item_id, request.args.get('procedure_id', ''))
    if item:
        return jsonify(item)
    return jsonify({'error': 'not found'}), 404


@api_bp.route('/total-count/<test_item_id>')
def total_count(test_item_id):
    """시험 항목의 전체 시험 케이스 수를 반환한다."""
    return jsonify({'total_count': get_total_count(test_item_id, request.args.get('procedure_id', ''))})


@api_bp.route('/whoami')
def whoami():
    """세션에 저장된 현재 로그인 사용자명을 반환한다."""
    return jsonify({'username': session.get('username', '')})


@api_bp.route('/login', methods=['POST'])
def login():
    """간이 로그인: 사용자명을 세션에 저장한다.

    인증이 목적이 아니라 시험 수행자를 추적하기 위한 최소한의 식별 기능이다.
    중복 시험 시작 방지(동일 사용자가 두 개 이상 진행 불가) 로직에 사용된다.
    """
    body = request.get_json(silent=True) or {}
    username = body.get('username', '').strip()
    if not username:
        return jsonify({'error': 'username required'}), 400
    session['username'] = username
    return jsonify({'username': username})


@api_bp.route('/start', methods=['POST'])
def start():
    """시험 실행을 시작한다.

    중복 진행 방지 로직:
        세션 사용자가 현재 다른 시험 항목를 진행 중이면 409를 반환한다.
        다른 수행자가 진행 중인 실행은 현재 사용자의 시작을 막지 않는다.
        단, 동일 시험 항목에 대한 재시작은 항상 허용한다.

    시작 후 performer가 비어 있으면 현재 세션 사용자를 자동으로 지정한다.
    (ExecutionRepository.start()에서 performer를 초기화하지 않으므로 여기서 설정)
    """
    body = request.get_json(silent=True) or {}
    test_item_id = body.get('test_item_id', '').strip()
    procedure_id = body.get('procedure_id', '').strip()
    if not test_item_id or not procedure_id:
        return jsonify({'error': 'test_item_id and procedure_id required'}), 400

    current_user = session.get('username', '')
    if current_user:
        for ex in ExecutionRepository.get_all():
            if ex.get('status') != 'in_progress':
                continue
            if ex.get('test_item_id') == test_item_id:
                # 같은 시험 항목면 재시작 허용 — 충돌 아님
                continue
            performer = ex.get('performer', '')
            if performer == current_user:
                return jsonify({'error': '이미 진행 중인 시험이 있습니다.', 'code': 'user_busy'}), 409

    total = get_total_count(test_item_id, procedure_id)
    ex = ExecutionRepository.start(test_item_id, procedure_id, total_count=total)

    # start() 후 performer가 비어 있을 때만 세션 사용자를 지정
    if ex and current_user and not ex.get('performer'):
        ExecutionRepository.update_performer(procedure_id, test_item_id, current_user)
        ex['performer'] = current_user

    return jsonify(ex), 201


@api_bp.route('/pause', methods=['POST'])
def pause():
    """진행 중인 시험을 일시정지한다."""
    body = request.get_json(silent=True) or {}
    procedure_id, test_item_id = _execution_key(body)
    if not procedure_id or not test_item_id:
        return jsonify({'error': 'procedure_id and test_item_id required'}), 400
    ex = ExecutionRepository.pause(procedure_id, test_item_id)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404
    return jsonify(ex)


@api_bp.route('/resume', methods=['POST'])
def resume():
    """일시정지된 시험을 재개한다."""
    body = request.get_json(silent=True) or {}
    procedure_id, test_item_id = _execution_key(body)
    if not procedure_id or not test_item_id:
        return jsonify({'error': 'procedure_id and test_item_id required'}), 400
    ex = ExecutionRepository.resume(procedure_id, test_item_id)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404
    return jsonify(ex)


@api_bp.route('/complete', methods=['POST'])
def complete():
    """시험을 완료 처리하고, 소요시간을 외부 서버에 비동기로 전송한다.

    완료 후 _notify_timing()을 호출하지만, 전송 실패가 완료 응답에 영향을 주지 않는다.
    """
    body = request.get_json(silent=True) or {}
    procedure_id, test_item_id = _execution_key(body)
    fail_count = body.get('fail_count', 0)
    block_count = body.get('block_count', 0)
    if not procedure_id or not test_item_id:
        return jsonify({'error': 'procedure_id and test_item_id required'}), 400
    ex = ExecutionRepository.complete(procedure_id, test_item_id, fail_count, block_count)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404

    elapsed = int(ex.get('elapsed_seconds') or 0)
    _notify_timing(ex.get('test_item_id', ''), ex.get('procedure_id', ''), elapsed)

    return jsonify(ex)


@api_bp.route('/pending-comment', methods=['PUT'])
def pending_comment():
    """시험 시작 전 시험 항목에 코멘트를 저장한다.

    실행 레코드가 없으면 pending 상태로 생성, 이미 있으면 save_pre_comment()의
    상태 분기 로직에 따라 처리된다. (진행 중이면 무시)
    """
    body = request.get_json(silent=True) or {}
    test_item_id = body.get('test_item_id', '').strip()
    procedure_id = body.get('procedure_id', '').strip()
    comment = body.get('comment', '')
    if not test_item_id or not procedure_id:
        return jsonify({'error': 'test_item_id and procedure_id required'}), 400
    ExecutionRepository.save_pre_comment(test_item_id, procedure_id, comment)
    return jsonify({'ok': True})


@api_bp.route('/comment', methods=['PUT'])
def update_comment():
    """진행 중/완료된 실행 레코드의 코멘트를 갱신한다."""
    body = request.get_json(silent=True) or {}
    procedure_id, test_item_id = _execution_key(body)
    comment = body.get('comment', '')
    if not procedure_id or not test_item_id:
        return jsonify({'error': 'procedure_id and test_item_id required'}), 400
    ex = ExecutionRepository.update_comment(procedure_id, test_item_id, comment)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@api_bp.route('/performer', methods=['PUT'])
def update_performer():
    """실행 레코드의 수행자(performer)를 갱신한다."""
    body = request.get_json(silent=True) or {}
    procedure_id, test_item_id = _execution_key(body)
    performer = body.get('performer', '')
    if not procedure_id or not test_item_id:
        return jsonify({'error': 'procedure_id and test_item_id required'}), 400
    ex = ExecutionRepository.update_performer(procedure_id, test_item_id, performer)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@api_bp.route('/timing/<test_item_id>', methods=['PATCH'])
def update_timing(test_item_id):
    """외부 API로부터 시험 소요시간(초)을 수신해 estimated_minutes를 갱신한다.

    실제 소요시간을 올림(ceil)하여 분 단위로 변환 후,
    해당 시험 항목의 estimated_minutes를 업데이트하고
    시험 절차서 전체의 estimated_minutes(시험 항목 합계)도 재계산한다.

    선택적 검증 파라미터(document_name, test_item_name)가 제공되면
    일치 여부를 확인하여 잘못된 시험 항목에 적용되는 것을 방지한다.
    """
    body = request.get_json(silent=True) or {}
    elapsed_seconds = body.get('elapsed_seconds')
    if elapsed_seconds is None:
        return jsonify({'error': 'elapsed_seconds required'}), 400

    from app.features.schedule.services import test_procedures as procedure_repo
    from math import ceil

    for t in procedure_repo.get_all():
        for item in t.get('test_items', []):
            if not isinstance(item, dict) or item.get('id') != test_item_id:
                continue

            # document_name / test_item_name이 넘어왔을 때만 일치 여부 검증
            if body.get('document_name') and t.get('document_name') != body['document_name']:
                return jsonify({'error': 'document_name mismatch'}), 400
            if body.get('test_item_name') and item.get('name') != body['test_item_name']:
                return jsonify({'error': 'test_item_name mismatch'}), 400

            # 초 단위 소요시간을 올림하여 분으로 변환
            new_minutes = ceil(int(elapsed_seconds) / 60)
            test_items = list(t['test_items'])
            idx = test_items.index(item)
            test_items[idx] = {**item, 'estimated_minutes': new_minutes}

            # 시험 절차서 전체 estimated_minutes = 소속 시험 항목 시간 합계
            total_minutes = sum(
                i.get('estimated_minutes', 0) for i in test_items if isinstance(i, dict)
            )
            procedure_repo.patch(t['id'], test_items=test_items, estimated_minutes=total_minutes)
            return jsonify({'ok': True, 'test_item_id': test_item_id, 'estimated_minutes': new_minutes})

    return jsonify({'error': 'test_item not found'}), 404


@api_bp.route('/reset', methods=['POST'])
def reset():
    """실행 레코드를 pending 상태로 초기화한다. (재시험 또는 잘못 시작된 경우)"""
    body = request.get_json(silent=True) or {}
    procedure_id, test_item_id = _execution_key(body)
    if not procedure_id or not test_item_id:
        return jsonify({'error': 'procedure_id and test_item_id required'}), 400
    ex = ExecutionRepository.reset(procedure_id, test_item_id)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(ex)


def _execution_key(body):
    """Read and normalize the composite execution key from a request body."""
    return (
        str(body.get('procedure_id') or '').strip(),
        str(body.get('test_item_id') or '').strip(),
    )
