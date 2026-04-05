from schedule.routes.calendar_views import schedule_bp
from schedule.routes.tasks import tasks_bp
from schedule.routes.admin import admin_bp
from schedule.routes.sync import sync_bp

# Register API routes on the same blueprint
import schedule.routes.calendar_api  # noqa: F401


def register_routes(app):
    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(sync_bp)
