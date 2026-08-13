"""
외부 데이터 동기화 라우트 모듈.

DynReady 연동에서 시험 데이터를 가져와 로컬 데이터와
동기화하는 API 엔드포인트를 제공한다.
전체 리셋 후 재동기화 기능도 포함한다.
"""

from flask import Blueprint, current_app, jsonify, request
from app.repositories import JsonDomainRepository
from app.domain.execution import Executions
from app.domain.scheduling import Schedule
from app.features.schedule.integrations.dyn_ready import DynReadyClient
from app.features.schedule.services.sync import SyncService

# 동기화 관련 API가 등록되는 블루프린트
sync_bp = Blueprint('sync', __name__, url_prefix='/api/sync')


@sync_bp.route('/test-data', methods=['POST'])
def sync_test_data():
    """외부 제공자로부터 시험 데이터(시험 절차서)를 동기화한다.

    전달된 버전 ID를 현재 전체 시험 사이클 버전으로 저장한다.

    Request Body (JSON, optional):
        - version_id (str): 전체 시험 사이클 버전 (미지정 시 기존 값 유지)

    Returns:
        JSON: 동기화 결과 (추가/수정/삭제된 시험 절차서 수 등)
    """
    version_id = (request.get_json(silent=True) or {}).get('version_id')
    client = DynReadyClient()
    result = SyncService.sync_test_data(client, version_id)
    return jsonify(result)


@sync_bp.route('/reset-and-sync', methods=['POST'])
def reset_and_sync():
    """모든 로컬 데이터를 삭제한 후 외부 소스에서 새로 동기화한다.

    실행 순서:
    1. 스케줄 블록, 시험 절차서, 시험실행 데이터를 모두 삭제
    2. 외부 제공자에서 시험 데이터 동기화

    Request Body (JSON, optional):
        - version_id (str): 새 전체 시험 사이클 버전

    Returns:
        JSON: 시험 절차서 동기화 결과
    """
    repository = JsonDomainRepository(current_app.config['DOMAIN_DATA_DIR'])
    version_id = (request.get_json(silent=True) or {}).get('version_id')
    repository.replace_all(
        test_procedures=(),
        schedule=Schedule(),
        executions=Executions(),
        settings=repository.load_settings(),
        version_id=version_id,
    )

    client = DynReadyClient()
    procedure_result = SyncService.sync_test_data(client, version_id)

    return jsonify({'procedures': procedure_result})


@sync_bp.route('/status', methods=['GET'])
def sync_status():
    """현재 동기화 상태를 조회한다.

    Returns:
        JSON: {procedures: int}
    """
    from app.features.schedule.services import test_procedures as procedure
    return jsonify({'test_procedures': len(procedure.get_all())})
