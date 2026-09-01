"""Server-rendered execution list and detail views."""

from flask import Blueprint, render_template, request

from app.repositories import get_repository
from app.features.execution.barcode_config import TEST_ITEM_PREFIX

views_bp = Blueprint('execution', __name__, url_prefix='/execution')


def _index_context():
    """Build initial filters and rows required by the execution list page."""
    repository = get_repository()
    plan = repository.load_plan()
    procedures = plan.test_procedures
    schedule = plan.schedule
    names = ('STE1', 'STE2', 'STE3')
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
    """Render the execution list screen."""
    return render_template('execution/index.html', **_index_context())


@views_bp.route('/<test_item_id>')
def detail(test_item_id):
    """Render one test item, disambiguated by the optional procedure ID."""
    procedure_id = request.args.get('procedure_id', '')
    return render_template('execution/detail.html', test_item_id=test_item_id,
                           procedure_id=procedure_id,
                           barcode_prefix=TEST_ITEM_PREFIX)
