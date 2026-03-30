import os
import time

from flask import Flask, redirect, url_for

_START_TIME = int(time.time())

# Inline config (was config.py)
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['DATA_DIR'] = DATA_DIR
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

    from schedule.routes import register_routes
    register_routes(app)

    @app.route('/')
    def index():
        return redirect(url_for('schedule.day_view'))

    return app
