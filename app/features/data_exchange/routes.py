"""Feature 간 데이터 공유용 read-only API."""

from flask import Blueprint, jsonify

from app.features.data_exchange.service import (
    execution_snapshot,
    feature_snapshot,
    schedule_snapshot,
)

data_exchange_bp = Blueprint(
    'data_exchange',
    __name__,
    url_prefix='/features/api',
)


@data_exchange_bp.route('/schedule')
def schedule_data():
    return jsonify(schedule_snapshot())


@data_exchange_bp.route('/execution')
def execution_data():
    return jsonify(execution_snapshot())


@data_exchange_bp.route('/snapshot')
def snapshot_data():
    return jsonify(feature_snapshot())
