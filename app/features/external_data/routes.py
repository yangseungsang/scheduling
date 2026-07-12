"""Stable external data API built on compact read models."""

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from app.repositories.compact_snapshot import compact_snapshot_repository_from_config
from app.services.read_models import (
    build_execution_list_items,
    build_schedule_export_rows,
)

external_api_bp = Blueprint(
    'external_api',
    __name__,
    url_prefix='/api/external/v1',
)


def _snapshot():
    return compact_snapshot_repository_from_config(current_app.config).load_snapshot()


def _with_metadata(payload):
    return {
        'schema_version': '1.0',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        **payload,
    }


@external_api_bp.route('/snapshot')
def snapshot():
    """Return a complete compact snapshot for external consumers."""
    return jsonify(_with_metadata(_snapshot()))


@external_api_bp.route('/catalog')
def catalog():
    """Return synced documents, test items, and exam attempts."""
    snap = _snapshot()
    return jsonify(_with_metadata({'catalog': snap['catalog']}))


@external_api_bp.route('/schedule')
def schedule():
    """Return schedule blocks and derived export rows for an optional date range."""
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    snap = _snapshot()
    blocks = snap['schedule']['blocks']
    block_ids = None
    if start_date or end_date:
        filtered_blocks = []
        block_ids = set()
        for block in blocks:
            block_date = block.get('date', '')
            if start_date and block_date < start_date:
                continue
            if end_date and block_date > end_date:
                continue
            filtered_blocks.append(block)
            block_ids.add(block.get('id'))
        blocks = filtered_blocks

    block_items = snap['schedule']['block_items']
    if block_ids is not None:
        block_items = [
            item for item in block_items
            if item.get('block_id') in block_ids
        ]

    rows = build_schedule_export_rows(snap, start_date=start_date, end_date=end_date)
    return jsonify(_with_metadata({
        'schedule': {
            'schema_version': snap['schedule']['schema_version'],
            'blocks': blocks,
            'block_items': block_items,
            'rows': rows,
        },
    }))


@external_api_bp.route('/executions')
def executions():
    """Return execution list read-model rows."""
    snap = _snapshot()
    rows = build_execution_list_items(
        snap,
        date_filter=request.args.get('date', ''),
        location_filter=request.args.get('location', ''),
    )
    return jsonify(_with_metadata({'executions': {'items': rows}}))


@external_api_bp.route('/metadata')
def metadata():
    """Return snapshot metadata and record counts."""
    snap = _snapshot()
    return jsonify(_with_metadata({
        'counts': {
            'documents': len(snap['catalog']['documents']),
            'test_items': len(snap['catalog']['test_items']),
            'exam_attempts': len(snap['catalog']['exam_attempts']),
            'blocks': len(snap['schedule']['blocks']),
            'block_items': len(snap['schedule']['block_items']),
            'execution_runs': len(snap['executions']['runs']),
            'users': len(snap['resources']['users']),
            'locations': len(snap['resources']['locations']),
            'versions': len(snap['resources']['versions']),
        },
        'sync': snap['catalog'].get('sync', {}),
    }))
