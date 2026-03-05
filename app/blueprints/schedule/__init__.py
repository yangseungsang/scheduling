from flask import Blueprint

schedule_bp = Blueprint('schedule', __name__)

from app.blueprints.schedule import routes  # noqa: E402, F401
