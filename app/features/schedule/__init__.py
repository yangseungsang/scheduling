"""
스케줄 기능 패키지 초기화 모듈.

스케줄 기능의 블루프린트들을 Flask 앱에 등록하는
진입점 함수를 제공한다.
"""

from app.features.schedule.routes import (
    schedule_bp,
    tasks_bp,
    admin_bp,
    sync_bp,
    register_schedule_routes,
)


def register_blueprints(app):
    """스케줄 관련 모든 블루프린트를 Flask 앱에 등록한다.

    routes 패키지의 register_schedule_routes 함수에 위임하여
    schedule_bp, tasks_bp, admin_bp, sync_bp를 일괄 등록한다.

    Args:
        app (Flask): 블루프린트를 등록할 Flask 앱 인스턴스
    """
    register_schedule_routes(app)
