"""Feature 간 schedule/execution 데이터 읽기 서비스."""

from app.repositories import get_repository


def _schedule_snapshot(operations):
    return {
        'version_id': operations.version_id,
        'test_procedures': [
            item.to_dict() for item in operations.test_procedures
        ],
        'schedule_blocks': [
            item.to_dict() for item in operations.schedule_blocks
        ],
    }


def _execution_snapshot(operations):
    return {
        'execution_runs': [
            item.to_dict() for item in operations.execution_runs
        ],
    }


def schedule_snapshot():
    """다른 feature가 재사용할 수 있는 schedule 데이터 스냅샷을 반환한다."""
    return _schedule_snapshot(get_repository().load_operations())


def execution_snapshot():
    """다른 feature가 재사용할 수 있는 execution 데이터 스냅샷을 반환한다."""
    return _execution_snapshot(get_repository().load_operations())


def feature_snapshot():
    """schedule/execution을 함께 읽는 통합 스냅샷을 반환한다."""
    operations = get_repository().load_operations()
    return {
        'schedule': _schedule_snapshot(operations),
        'execution': _execution_snapshot(operations),
    }
