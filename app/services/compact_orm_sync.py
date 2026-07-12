"""Synchronize transitional ORM storage payloads into compact ORM tables."""

from app.db.repository import CompactSnapshotOrmRepository
from app.services.compact_snapshot_storage import build_snapshot_from_legacy_storage


def sync_compact_from_orm_storage(database_url):
    """Rebuild compact ORM tables from legacy-shaped ORM storage payloads."""
    from app.features.execution.repositories import OrmExecutionStorage
    from app.features.schedule.repositories import OrmScheduleStorage

    schedule_storage = OrmScheduleStorage(database_url, sync_compact=False)
    execution_storage = OrmExecutionStorage(database_url, sync_compact=False)
    snapshot = build_snapshot_from_legacy_storage(schedule_storage, execution_storage)
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema()
    repository.replace_snapshot(snapshot)
    return snapshot
