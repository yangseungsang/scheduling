from flask import Flask, redirect, url_for

from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure data directory exists
    import os
    os.makedirs(app.config['DATA_DIR'], exist_ok=True)

    # Jinja2 globals
    app.jinja_env.globals['enumerate'] = enumerate

    # Register blueprints
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
