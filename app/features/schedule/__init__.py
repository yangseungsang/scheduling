from app.features.schedule.routes import (
    schedule_bp,
    tasks_bp,
    admin_bp,
    sync_bp,
    register_routes,
)


def register_blueprints(app):
    """Register all schedule-related blueprints on the Flask app."""
    register_routes(app)
