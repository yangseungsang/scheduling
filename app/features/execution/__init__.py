"""시험 실행 기능 패키지."""

from app.features.execution.routes import register_execution_routes


def register_blueprints(app):
    register_execution_routes(app)
