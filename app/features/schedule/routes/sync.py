from flask import Blueprint, jsonify, request
from app.features.schedule.providers import get_provider
from app.features.schedule.services.sync import SyncService

sync_bp = Blueprint('sync', __name__, url_prefix='/api/sync')


@sync_bp.route('/versions', methods=['POST'])
def sync_versions():
    provider = get_provider()
    result = SyncService.sync_versions(provider)
    return jsonify(result)


@sync_bp.route('/test-data', methods=['POST'])
def sync_test_data():
    provider = get_provider()
    data = request.get_json() or {}
    version_id = data.get('version_id')
    result = SyncService.sync_test_data(provider, version_id=version_id)
    return jsonify(result)


@sync_bp.route('/reset-and-sync', methods=['POST'])
def reset_and_sync():
    """Reset all schedule blocks and tasks, then sync fresh from provider."""
    from app.features.schedule.store import write_json
    # 1. Clear all data
    write_json('schedule_blocks.json', [])
    write_json('tasks.json', [])
    write_json('versions.json', [])

    # 3. Sync versions
    provider = get_provider()
    ver_result = SyncService.sync_versions(provider)

    # 4. Sync test data
    data = request.get_json() or {}
    version_id = data.get('version_id')
    task_result = SyncService.sync_test_data(provider, version_id=version_id)

    return jsonify({
        'versions': ver_result,
        'tasks': task_result,
    })


@sync_bp.route('/status', methods=['GET'])
def sync_status():
    from app.features.schedule.models import version, task
    versions = version.get_all()
    tasks = task.get_all()
    external_tasks = [t for t in tasks if t.get('source') == 'external']
    return jsonify({
        'versions': len(versions),
        'external_tasks': len(external_tasks),
        'local_tasks': len(tasks) - len(external_tasks),
    })
