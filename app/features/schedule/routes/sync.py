"""
외부 데이터 동기화 라우트 모듈.

외부 데이터 제공자(provider)로부터 버전 정보와 시험 데이터를 가져와
로컬 데이터와 동기화하는 API 엔드포인트를 제공한다.
전체 리셋 후 재동기화 기능도 포함한다.
"""

from flask import Blueprint, jsonify, request
from app.features.schedule.providers import get_provider
from app.features.schedule.services.sync import SyncService

# 동기화 관련 API가 등록되는 블루프린트
sync_bp = Blueprint('sync', __name__, url_prefix='/api/sync')


@sync_bp.route('/versions', methods=['POST'])
def sync_versions():
    """외부 제공자로부터 버전 목록을 동기화한다.

    외부 데이터 소스의 버전 정보를 가져와 로컬 versions.json에 반영한다.

    Returns:
        JSON: 동기화 결과 (추가/수정/삭제된 버전 수 등)
    """
    provider = get_provider()
    result = SyncService.sync_versions(provider)
    return jsonify(result)


@sync_bp.route('/test-data', methods=['POST'])
def sync_test_data():
    """외부 제공자로부터 시험 데이터(태스크)를 동기화한다.

    특정 버전의 시험 데이터만 선택적으로 동기화할 수 있다.

    Request Body (JSON, optional):
        - version_id (str): 동기화할 특정 버전 ID (미지정 시 전체)

    Returns:
        JSON: 동기화 결과 (추가/수정/삭제된 태스크 수 등)
    """
    provider = get_provider()
    data = request.get_json() or {}
    version_id = data.get('version_id')
    result = SyncService.sync_test_data(provider, version_id=version_id)
    return jsonify(result)


@sync_bp.route('/reset-and-sync', methods=['POST'])
def reset_and_sync():
    """모든 로컬 데이터를 삭제한 후 외부 소스에서 새로 동기화한다.

    실행 순서:
    1. 스케줄 블록, 태스크, 버전 데이터를 모두 삭제
    2. 외부 제공자에서 버전 정보 동기화
    3. 외부 제공자에서 시험 데이터 동기화

    Request Body (JSON, optional):
        - version_id (str): 동기화할 특정 버전 ID

    Returns:
        JSON: 버전 및 태스크 동기화 결과
    """
    from app.features.schedule.store import write_json
    # 1. 모든 로컬 데이터 초기화
    write_json('schedule_blocks.json', [])
    write_json('tasks.json', [])
    write_json('versions.json', [])

    # 2. 외부 제공자에서 버전 동기화
    provider = get_provider()
    ver_result = SyncService.sync_versions(provider)

    # 3. 외부 제공자에서 시험 데이터 동기화
    data = request.get_json() or {}
    version_id = data.get('version_id')
    task_result = SyncService.sync_test_data(provider, version_id=version_id)

    return jsonify({
        'versions': ver_result,
        'tasks': task_result,
    })


@sync_bp.route('/status', methods=['GET'])
def sync_status():
    """현재 동기화 상태를 조회한다.

    Returns:
        JSON: {versions: int, tasks: int}
    """
    from app.features.schedule.models import version, task
    return jsonify({
        'versions': len(version.get_all()),
        'tasks': len(task.get_all()),
    })
