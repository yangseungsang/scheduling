from flask import Blueprint, render_template

from app.features.schedule.models import location as loc_repo
from app.features.schedule.models import schedule_block as block_repo

views_bp = Blueprint('execution', __name__, url_prefix='/execution')


def _index_context():
    locations = loc_repo.get_all()
    blocks = block_repo.get_all()
    dates = sorted({b['date'] for b in blocks if b.get('date')})
    return dict(locations=locations, dates=dates)


@views_bp.route('/')
def index():
    return render_template('execution/index.html', **_index_context())


@views_bp.route('/<identifier_id>')
def detail(identifier_id):
    return render_template('execution/detail.html', identifier_id=identifier_id)
