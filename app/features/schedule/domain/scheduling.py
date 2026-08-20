"""Scheduling domain types."""

from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass(frozen=True)
class ScheduleBlock:
    """Immutable calendar placement for test work or a simple event."""
    id: str
    procedure_id: Optional[str] = None
    test_item_ids: Tuple[str, ...] = ()
    date: str = ''
    start_time: str = ''
    end_time: str = ''
    location_name: str = ''
    assignee_names: Tuple[str, ...] = ()
    kind: str = 'test'
    title: str = ''
    memo: str = ''
    is_locked: bool = False
    manual_status: str = ''
    overflow_minutes: int = 0

    @classmethod
    def from_dict(cls, data):
        """Create a block and infer its kind from procedure ownership."""
        return cls(
            id=data['id'],
            procedure_id=data.get('procedure_id'),
            test_item_ids=tuple(data.get('test_item_ids', [])),
            date=data.get('date', ''),
            start_time=data.get('start_time', ''),
            end_time=data.get('end_time', ''),
            location_name=data.get('location_name', ''),
            assignee_names=tuple(data.get('assignee_names', [])),
            kind='simple' if not data.get('procedure_id') else 'test',
            title=data.get('title', ''),
            memo=data.get('memo', ''),
            is_locked=bool(data.get('is_locked', False)),
            manual_status=data.get('manual_status', ''),
            overflow_minutes=int(data.get('overflow_minutes') or 0),
        )

    def to_dict(self):
        """Serialize fields required to restore the calendar placement."""
        result = {
            'id': self.id,
            'date': self.date,
            'start_time': self.start_time,
            'end_time': self.end_time,
        }
        if self.procedure_id is not None:
            result['procedure_id'] = self.procedure_id
        if self.test_item_ids:
            result['test_item_ids'] = list(self.test_item_ids)
        if self.location_name:
            result['location_name'] = self.location_name
        if self.assignee_names:
            result['assignee_names'] = list(self.assignee_names)
        if self.title:
            result['title'] = self.title
        if self.memo:
            result['memo'] = self.memo
        if self.is_locked:
            result['is_locked'] = True
        if self.manual_status:
            result['manual_status'] = self.manual_status
        if self.overflow_minutes:
            result['overflow_minutes'] = self.overflow_minutes
        return result


@dataclass(frozen=True)
class Schedule:
    """Immutable collection of calendar blocks."""
    blocks: Tuple[ScheduleBlock, ...] = ()

    @classmethod
    def from_dict(cls, data):
        """Deserialize a possibly empty schedule payload."""
        data = data or {}
        return cls(
            blocks=tuple(ScheduleBlock.from_dict(item) for item in data.get('blocks', [])),
        )

    def to_dict(self):
        """Serialize all blocks in display-independent form."""
        return {
            'blocks': [item.to_dict() for item in self.blocks],
        }
