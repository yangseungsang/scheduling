import secrets
from flask import Flask, render_template, request, session, abort
from config import config
from app.db import init_app as db_init_app


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db_init_app(app)

    # Jinja2 전역 함수 등록
    app.jinja_env.globals['enumerate'] = enumerate

    # CSRF 보호: form POST 요청에만 적용 (JSON API는 제외)
    @app.before_request
    def csrf_protect():
        if request.method == 'POST' and not request.is_json:
            token = session.get('csrf_token')
            if not token or token != request.form.get('csrf_token'):
                abort(403)

    @app.context_processor
    def inject_csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(16)
        return {'csrf_token': session['csrf_token']}

    # 보안 헤더
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

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

    # HTTP 에러 핸들러
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors.html',
                               error_code=404,
                               error_message='요청하신 페이지를 찾을 수 없습니다.'), 404

    @app.errorhandler(500)
    def internal_error(e):
        return render_template('errors.html',
                               error_code=500,
                               error_message='서버 내부 오류가 발생했습니다.'), 500

    return app
