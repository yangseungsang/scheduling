"""Execution blueprint collection."""

from app.features.execution.routes.views import views_bp
from app.features.execution.routes.api import api_bp


def register_execution_routes(app):
    """Register execution HTML and REST API blueprints on the Flask app."""
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)
