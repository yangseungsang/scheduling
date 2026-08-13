from flask import Blueprint, current_app, render_template, request

from app.repositories import JsonDomainRepository
from app.features.execution.barcode_config import TEST_ITEM_PREFIX

views_bp = Blueprint('execution', __name__, url_prefix='/execution')


def _index_context():
    repository = JsonDomainRepository(current_app.config['DOMAIN_DATA_DIR'])
    plan = repository.load_plan()
    procedures = plan.test_procedures
    schedule = plan.schedule
    names = sorted({
        item.location_name for item in procedures if item.location_name
    } | {
        block.location_name for block in schedule.blocks if block.location_name
    })
    locations = [{'id': name, 'name': name} for name in names]
    dates = sorted({
        block.date
        for block in schedule.blocks
        if block.date
    })
    documents = [
        {
            'id': procedure.id,
            'name': (
                f'{procedure.document_name} ({procedure.test_round}차)'
                if procedure.test_round not in (None, 1) else procedure.document_name
            ) or procedure.document_id or procedure.id,
        }
        for procedure in sorted(
            procedures,
            key=lambda item: (
                item.document_name, item.test_round or 0, item.id,
            ),
        )
    ]
    return dict(
        locations=locations, dates=dates, documents=documents,
        barcode_prefix=TEST_ITEM_PREFIX,
    )


@views_bp.route('/')
def index():
    return render_template('execution/index.html', **_index_context())


@views_bp.route('/<test_item_id>')
def detail(test_item_id):
    procedure_id = request.args.get('procedure_id', '')
    return render_template('execution/detail.html', test_item_id=test_item_id,
                           procedure_id=procedure_id,
                           barcode_prefix=TEST_ITEM_PREFIX)
