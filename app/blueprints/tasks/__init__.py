from flask import Blueprint

tasks_bp = Blueprint('tasks', __name__)

from app.blueprints.tasks import routes  # noqa: E402, F401
