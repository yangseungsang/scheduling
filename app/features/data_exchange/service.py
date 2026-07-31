"""Feature 간 schedule/execution 데이터 읽기 서비스."""

from app.domains.procedure import service as procedure_service
from app.features.execution.models.execution import ExecutionRepository
from app.features.schedule.models import location, schedule_block, task, user, version


def schedule_snapshot():
    """다른 feature가 재사용할 수 있는 schedule 데이터 스냅샷을 반환한다."""
    return {
        'tasks': task.get_all(),
        'schedule_blocks': schedule_block.get_all(),
        'users': user.get_all(),
        'locations': location.get_all(),
        'versions': version.get_all(),
    }


def execution_snapshot():
    """다른 feature가 재사용할 수 있는 execution 데이터 스냅샷을 반환한다."""
    return {
        'executions': ExecutionRepository.get_all(),
    }


def feature_snapshot():
    """schedule/execution을 함께 읽는 통합 스냅샷을 반환한다."""
    return {
        'schedule': schedule_snapshot(),
        'execution': execution_snapshot(),
        'procedure_items': procedure_service.execution_items(),
    }
