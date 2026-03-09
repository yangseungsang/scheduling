import os
import time

from flask import Flask, redirect, url_for

from config import Config

_START_TIME = int(time.time())


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    os.makedirs(app.config['DATA_DIR'], exist_ok=True)

    # Jinja2 globals
    app.jinja_env.globals['enumerate'] = enumerate
    app.jinja_env.globals['cache_bust'] = _START_TIME

    # CORS for API
    @app.after_request
    def add_cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return response

    from app.blueprints.tasks.routes import tasks_bp
    from app.blueprints.schedule.routes import schedule_bp
    from app.blueprints.admin.routes import admin_bp

    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(admin_bp)

    @app.route('/')
    def index():
        return redirect(url_for('schedule.day_view'))

    return app
