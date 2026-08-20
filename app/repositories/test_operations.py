"""Persistence read model joining schedule and execution records."""

from dataclasses import dataclass
from typing import Tuple

from app.features.execution.domain import ExecutionRun, Executions
from app.features.schedule.domain.procedures import TestProcedure
from app.features.schedule.domain.scheduling import Schedule, ScheduleBlock


@dataclass(frozen=True)
class TestOperations:
    """Temporary joined model used for cross-feature atomic workflows."""
    __test__ = False
    version_id: str = ''
    test_procedures: Tuple[TestProcedure, ...] = ()
    schedule_blocks: Tuple[ScheduleBlock, ...] = ()
    execution_runs: Tuple[ExecutionRun, ...] = ()

    @classmethod
    def from_dict(cls, data):
        """Deserialize a joined representation used by tests and migration tools."""
        data = data or {}
        return cls(
            version_id=data.get('version_id', ''),
            test_procedures=tuple(TestProcedure.from_dict(item) for item in data.get('test_procedures', [])),
            schedule_blocks=tuple(
                ScheduleBlock.from_dict(item)
                for item in data.get('schedule_blocks', [])
            ),
            execution_runs=tuple(
                ExecutionRun.from_dict(item)
                for item in data.get('execution_runs', [])
            ),
        )

    @property
    def schedule(self):
        """Expose joined blocks as the schedule feature's collection type."""
        return Schedule(blocks=self.schedule_blocks)

    @property
    def executions(self):
        """Expose joined runs as the execution feature's collection type."""
        return Executions(runs=self.execution_runs)

    def to_dict(self):
        """Serialize the joined in-memory representation."""
        return {
            'version_id': self.version_id,
            'test_procedures': [item.to_dict() for item in self.test_procedures],
            'schedule_blocks': [item.to_dict() for item in self.schedule_blocks],
            'execution_runs': [item.to_dict() for item in self.execution_runs],
        }
