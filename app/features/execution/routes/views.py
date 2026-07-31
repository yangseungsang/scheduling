from flask import Blueprint, render_template, request

from app.domains.procedure import service as procedure_service
from app.features.execution.barcode_config import IDENTIFIER_PREFIX

views_bp = Blueprint('execution', __name__, url_prefix='/execution')


def _index_context():
    filters = procedure_service.execution_filter_context()
    return dict(
        locations=filters['locations'],
        dates=filters['dates'],
        barcode_prefix=IDENTIFIER_PREFIX,
    )


@views_bp.route('/')
def index():
    return render_template('execution/index.html', **_index_context())


@views_bp.route('/<identifier_id>')
def detail(identifier_id):
    task_id = request.args.get('task_id', '')
    return render_template('execution/detail.html', identifier_id=identifier_id,
                           task_id=task_id,
                           barcode_prefix=IDENTIFIER_PREFIX)
