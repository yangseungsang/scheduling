"""SQLAlchemy ORM models for the compact scheduling domain."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import JSON

from app.db import Base


class SnapshotSync(Base):
    __tablename__ = 'snapshot_sync'

    id = Column(String(40), primary_key=True, default='current')
    schema_version = Column(String(20), nullable=False, default='1.0')
    provider = Column(String(80), nullable=False, default='')
    updated_at = Column(String(80), nullable=False, default='')
    data_hash = Column(String(160), nullable=False, default='')


class SourceDocument(Base):
    __tablename__ = 'source_documents'

    id = Column(String(64), primary_key=True)
    legacy_task_ids = Column(JSON, nullable=False, default=list)
    external_doc_id = Column(String(120), nullable=True)
    version_id = Column(String(120), nullable=False, default='')
    doc_name = Column(String(500), nullable=False, default='')
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint('version_id', 'external_doc_id', name='uq_documents_version_external_doc'),
    )


class TestItem(Base):
    __tablename__ = 'test_items'

    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey('source_documents.id'), nullable=False, index=True)
    external_test_id = Column(String(160), nullable=False)
    name = Column(String(500), nullable=False, default='')
    estimated_minutes = Column(Integer, nullable=False, default=0)
    total_count = Column(Integer, nullable=False, default=0)
    owner_names = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint('document_id', 'external_test_id', name='uq_test_items_document_external_test'),
    )


class ExamAttempt(Base):
    __tablename__ = 'exam_attempts'

    id = Column(String(64), primary_key=True)
    test_item_id = Column(String(64), ForeignKey('test_items.id'), nullable=False, index=True)
    exam_no = Column(Integer, nullable=True)
    legacy_task_id = Column(String(80), nullable=False, default='')
    legacy_identifier_id = Column(String(160), nullable=False, default='')
    default_location_id = Column(String(80), nullable=False, default='')
    default_assignee_names = Column(JSON, nullable=False, default=list)
    memo = Column(Text, nullable=False, default='')
    state = Column(String(40), nullable=False, default='active')


class ScheduleBlock(Base):
    __tablename__ = 'schedule_blocks'

    id = Column(String(64), primary_key=True)
    legacy_block_id = Column(String(80), nullable=False, default='', index=True)
    date = Column(String(20), nullable=False, default='', index=True)
    start_time = Column(String(20), nullable=False, default='')
    end_time = Column(String(20), nullable=False, default='')
    location_id = Column(String(80), nullable=False, default='', index=True)
    assignee_names = Column(JSON, nullable=False, default=list)
    kind = Column(String(40), nullable=False, default='test')
    title = Column(String(500), nullable=False, default='')
    memo = Column(Text, nullable=False, default='')
    is_locked = Column(Boolean, nullable=False, default=False)
    manual_status = Column(String(40), nullable=False, default='')
    overflow_minutes = Column(Integer, nullable=False, default=0)


class BlockItem(Base):
    __tablename__ = 'block_items'

    id = Column(String(64), primary_key=True)
    block_id = Column(String(64), ForeignKey('schedule_blocks.id'), nullable=False, index=True)
    exam_attempt_id = Column(String(64), ForeignKey('exam_attempts.id'), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint('block_id', 'exam_attempt_id', name='uq_block_items_block_attempt'),
    )


class ExecutionRun(Base):
    __tablename__ = 'execution_runs'

    id = Column(String(64), primary_key=True)
    legacy_execution_id = Column(String(80), nullable=False, default='', index=True)
    exam_attempt_id = Column(String(64), ForeignKey('exam_attempts.id'), nullable=False, index=True)
    status = Column(String(40), nullable=False, default='pending')
    segments = Column(JSON, nullable=False, default=list)
    total_count = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    block_count = Column(Integer, nullable=False, default=0)
    pass_count = Column(Integer, nullable=False, default=0)
    comment = Column(Text, nullable=False, default='')
    performer_name = Column(String(160), nullable=False, default='')
    created_at = Column(String(80), nullable=True)
    completed_at = Column(String(80), nullable=True)
    elapsed_seconds_snapshot = Column(Integer, nullable=False, default=0)
    elapsed_mins_snapshot = Column(Integer, nullable=False, default=0)


class ResourceRecord(Base):
    __tablename__ = 'resource_records'

    kind = Column(String(40), primary_key=True)
    id = Column(String(120), primary_key=True)
    payload = Column(JSON, nullable=False, default=dict)


class AppSettings(Base):
    __tablename__ = 'app_settings'

    id = Column(String(40), primary_key=True, default='current')
    payload = Column(JSON, nullable=False, default=dict)


class MigrationWarning(Base):
    __tablename__ = 'migration_warnings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(40), nullable=False)
    message = Column(Text, nullable=False)


class StoragePayload(Base):
    __tablename__ = 'storage_payloads'

    area = Column(String(40), primary_key=True)
    filename = Column(String(120), primary_key=True)
    payload = Column(JSON, nullable=False)
