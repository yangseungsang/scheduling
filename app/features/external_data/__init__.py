"""External read-only data APIs."""

from app.features.external_data.routes import external_api_bp


def register_blueprints(app):
    app.register_blueprint(external_api_bp)
