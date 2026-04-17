from flask import Blueprint, render_template

from app.features.schedule.models import location as loc_repo
from app.features.schedule.models import schedule_block as block_repo

views_bp = Blueprint('execution', __name__, url_prefix='/execution')


@views_bp.route('/')
def index():
    locations = loc_repo.get_all()
    blocks = block_repo.get_all()
    dates = sorted({b['date'] for b in blocks if b.get('date')})
    return render_template('execution/index.html',
                           locations=locations,
                           dates=dates)
