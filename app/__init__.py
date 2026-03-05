from flask import Flask
from config import config
from app.db import init_app as db_init_app


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db_init_app(app)

    # Jinja2 전역 함수 등록
    app.jinja_env.globals['enumerate'] = enumerate

    from app.blueprints.tasks import tasks_bp
    from app.blueprints.schedule import schedule_bp
    from app.blueprints.admin import admin_bp

    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(schedule_bp, url_prefix='/schedule')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('schedule.day_view'))

    return app
