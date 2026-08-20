"""Application settings shared by features."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.domain.common import SCHEMA_VERSION


@dataclass(frozen=True)
class AppSettings:
    """Optional work-hour and calendar presentation settings."""
    schema_version: str = SCHEMA_VERSION
    work_start: Optional[str] = None
    work_end: Optional[str] = None
    actual_work_start: Optional[str] = None
    actual_work_end: Optional[str] = None
    lunch_start: Optional[str] = None
    lunch_end: Optional[str] = None
    breaks: Optional[Tuple[Dict[str, str], ...]] = None
    grid_interval_minutes: Optional[int] = None
    max_schedule_days: Optional[int] = None
    block_color_by: Optional[str] = None

    @classmethod
    def from_dict(cls, data):
        """Create settings while preserving absent optional values as None."""
        data = data or {}
        breaks = data.get('breaks')
        return cls(
            schema_version=data.get('schema_version', SCHEMA_VERSION),
            work_start=data.get('work_start'),
            work_end=data.get('work_end'),
            actual_work_start=data.get('actual_work_start'),
            actual_work_end=data.get('actual_work_end'),
            lunch_start=data.get('lunch_start'),
            lunch_end=data.get('lunch_end'),
            breaks=tuple(dict(item) for item in breaks) if breaks is not None else None,
            grid_interval_minutes=data.get('grid_interval_minutes'),
            max_schedule_days=data.get('max_schedule_days'),
            block_color_by=data.get('block_color_by'),
        )

    def to_dict(self):
        """Serialize only configured values plus the schema version."""
        result = {'schema_version': self.schema_version}
        for key in (
            'work_start', 'work_end', 'actual_work_start', 'actual_work_end',
            'lunch_start', 'lunch_end', 'grid_interval_minutes',
            'max_schedule_days', 'block_color_by',
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.breaks is not None:
            result['breaks'] = [dict(item) for item in self.breaks]
        return result
