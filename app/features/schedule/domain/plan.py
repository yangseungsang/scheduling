"""Test cycle plan containing procedures and calendar placements."""

from dataclasses import dataclass
from typing import Tuple

from app.features.schedule.domain.procedures import TestProcedure
from app.features.schedule.domain.scheduling import Schedule, ScheduleBlock


@dataclass(frozen=True)
class TestPlan:
    """Schedule aggregate persisted as a single test-plan document."""
    __test__ = False
    version_id: str = ''
    test_procedures: Tuple[TestProcedure, ...] = ()
    schedule_blocks: Tuple[ScheduleBlock, ...] = ()

    @classmethod
    def from_dict(cls, data):
        """Deserialize procedures and blocks from stored JSON data."""
        data = data or {}
        return cls(
            version_id=data.get('version_id', ''),
            test_procedures=tuple(TestProcedure.from_dict(item) for item in data.get('test_procedures', [])),
            schedule_blocks=tuple(
                ScheduleBlock.from_dict(item)
                for item in data.get('schedule_blocks', [])
            ),
        )

    @property
    def schedule(self):
        """Expose schedule blocks through the Schedule collection type."""
        return Schedule(blocks=self.schedule_blocks)

    def to_dict(self):
        """Serialize the complete plan for repository persistence."""
        return {
            'version_id': self.version_id,
            'test_procedures': [item.to_dict() for item in self.test_procedures],
            'schedule_blocks': [item.to_dict() for item in self.schedule_blocks],
        }
