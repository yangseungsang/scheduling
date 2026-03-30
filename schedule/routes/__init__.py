from schedule.routes.calendar import schedule_bp
from schedule.routes.tasks import tasks_bp
from schedule.routes.admin import admin_bp


def register_routes(app):
    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(admin_bp)
