"""Execution domain types."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple


@dataclass(frozen=True)
class ExecutionRun:
    procedure_id: str
    test_item_id: str
    status: str = 'pending'
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    active_started_at: Optional[str] = None
    actual_seconds: int = 0
    total_count: int = 0
    fail_count: int = 0
    block_count: int = 0
    pass_count: int = 0
    comment: str = ''
    performer_name: str = ''

    @classmethod
    def from_dict(cls, data):
        return cls(
            procedure_id=data.get('procedure_id', ''),
            test_item_id=data.get('test_item_id', ''),
            status=data.get('status', 'pending'),
            started_at=data.get('started_at'),
            ended_at=data.get('ended_at'),
            active_started_at=data.get('active_started_at'),
            actual_seconds=int(data.get('actual_seconds') or 0),
            total_count=int(data.get('total_count') or 0),
            fail_count=int(data.get('fail_count') or 0),
            block_count=int(data.get('block_count') or 0),
            pass_count=int(data.get('pass_count') or 0),
            comment=data.get('comment', ''),
            performer_name=data.get('performer_name', ''),
        )

    def to_dict(self):
        result = {
            'procedure_id': self.procedure_id,
            'test_item_id': self.test_item_id,
        }
        if self.status != 'pending':
            result['status'] = self.status
        if self.started_at:
            result['started_at'] = self.started_at
        if self.ended_at:
            result['ended_at'] = self.ended_at
        if self.active_started_at:
            result['active_started_at'] = self.active_started_at
        if self.actual_seconds:
            result['actual_seconds'] = self.actual_seconds
        for key in ('total_count', 'fail_count', 'block_count', 'pass_count'):
            value = getattr(self, key)
            if value:
                result[key] = value
        if self.comment:
            result['comment'] = self.comment
        if self.performer_name:
            result['performer_name'] = self.performer_name
        return result

    @property
    def elapsed_seconds(self):
        elapsed = self.actual_seconds
        if self.status == 'in_progress' and self.active_started_at:
            active_start = datetime.fromisoformat(self.active_started_at)
            elapsed += max(0, int((datetime.now() - active_start).total_seconds()))
        return elapsed


@dataclass(frozen=True)
class Executions:
    runs: Tuple[ExecutionRun, ...] = ()

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            runs=tuple(ExecutionRun.from_dict(item) for item in data.get('runs', [])),
        )

    def to_dict(self):
        return {
            'runs': [item.to_dict() for item in self.runs],
        }
