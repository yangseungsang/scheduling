from flask import Blueprint, jsonify, request
from schedule.providers import get_provider
from schedule.services.sync import SyncService

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


@sync_bp.route('/status', methods=['GET'])
def sync_status():
    from schedule.models import version, task
    versions = version.get_all()
    tasks = task.get_all()
    external_tasks = [t for t in tasks if t.get('source') == 'external']
    return jsonify({
        'versions': len(versions),
        'external_tasks': len(external_tasks),
        'local_tasks': len(tasks) - len(external_tasks),
    })
