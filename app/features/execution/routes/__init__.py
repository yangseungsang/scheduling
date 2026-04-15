"""execution 라우트 패키지."""

from app.features.execution.routes.execution_views import execution_bp
import app.features.execution.routes.execution_api  # noqa: F401


def register_execution_routes(app):
    app.register_blueprint(execution_bp)
