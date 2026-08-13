"""Test cycle plan containing procedures and calendar placements."""

from dataclasses import dataclass
from typing import Tuple

from app.domain.scheduling import Schedule, ScheduleBlock
from app.domain.test_procedures import TestProcedure


@dataclass(frozen=True)
class TestPlan:
    __test__ = False
    version_id: str = ''
    test_procedures: Tuple[TestProcedure, ...] = ()
    schedule_blocks: Tuple[ScheduleBlock, ...] = ()

    @classmethod
    def from_dict(cls, data):
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
        return Schedule(blocks=self.schedule_blocks)

    def to_dict(self):
        return {
            'version_id': self.version_id,
            'test_procedures': [item.to_dict() for item in self.test_procedures],
            'schedule_blocks': [item.to_dict() for item in self.schedule_blocks],
        }
