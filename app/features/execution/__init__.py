"""Execution feature blueprint registration entry point."""


def register_blueprints(app):
    """Register execution routes without importing them during domain imports."""
    # Domain 모듈을 import할 때 route와 repository가 따라오지 않도록 지연 import한다.
    from app.features.execution.routes import register_execution_routes

    register_execution_routes(app)
