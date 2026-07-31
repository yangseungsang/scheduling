"""Feature 간 schedule/execution 데이터 읽기 서비스."""

from app.domains.procedure import service as procedure_service


def schedule_snapshot():
    """다른 feature가 재사용할 수 있는 schedule 데이터 스냅샷을 반환한다."""
    return procedure_service.schedule_snapshot()


def execution_snapshot():
    """다른 feature가 재사용할 수 있는 execution 데이터 스냅샷을 반환한다."""
    return procedure_service.execution_snapshot()


def feature_snapshot():
    """schedule/execution을 함께 읽는 통합 스냅샷을 반환한다."""
    return procedure_service.feature_snapshot()
