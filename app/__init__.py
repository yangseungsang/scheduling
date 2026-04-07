import os
import time

from flask import Flask, redirect, url_for

_START_TIME = int(time.time())

# Inline config
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'features', 'schedule', 'data')


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    )
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['DATA_DIR'] = DATA_DIR
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    os.makedirs(app.config['DATA_DIR'], exist_ok=True)

    # Jinja2 globals
    app.jinja_env.globals['cache_bust'] = _START_TIME

    # CORS for API
    @app.after_request
    def add_cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return response

    from app.features.schedule import register_blueprints
    register_blueprints(app)

    @app.route('/')
    def index():
        return redirect(url_for('schedule.week_view'))

    return app
