"""
스케줄 라우트 패키지 초기화 모듈.

모든 스케줄 관련 블루프린트를 한곳에서 임포트하고,
Flask 앱에 일괄 등록하는 함수를 제공한다.
"""

from app.features.schedule.routes.calendar_views import schedule_bp
from app.features.schedule.routes.tasks import tasks_bp
from app.features.schedule.routes.admin import admin_bp
from app.features.schedule.routes.sync import sync_bp

# calendar_api 모듈은 schedule_bp에 API 라우트를 추가 등록하므로
# 임포트만으로 라우트가 등록된다 (사용하지 않으므로 noqa 처리)
import app.features.schedule.routes.calendar_api  # noqa: F401


def register_routes(app):
    """모든 스케줄 관련 블루프린트를 Flask 앱에 등록한다.

    Args:
        app (Flask): 블루프린트를 등록할 Flask 앱 인스턴스
    """
    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(sync_bp)
