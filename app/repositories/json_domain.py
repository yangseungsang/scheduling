"""Typed JSON repository for test operations and application settings."""

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import replace

import portalocker

from app.features.execution.domain import Executions
from app.features.schedule.domain import AppSettings, Schedule, TestPlan, TestProcedure
from app.repositories.test_operations import TestOperations


class JsonDomainRepository:
    """Persist feature domain aggregates in locked, atomically replaced JSON files."""

    # 파일 이름은 repository만 알고 feature service에는 노출하지 않는다.
    PLAN_FILE = 'test_plan.json'
    EXECUTIONS_FILE = 'test_executions.json'
    SETTINGS_FILE = 'settings.json'

    def __init__(self, data_dir):
        """Bind the repository to one independently lockable data directory."""
        self.data_dir = os.path.abspath(data_dir)
        self.lock_path = os.path.join(self.data_dir, '.data.lock')

    def initialize(self, reset=False):
        """Create missing domain documents, or replace all documents when reset."""
        defaults = {
            self.PLAN_FILE: TestPlan().to_dict(),
            self.EXECUTIONS_FILE: _executions_dict(Executions()),
            self.SETTINGS_FILE: AppSettings().to_dict(),
        }
        with self._locked():
            for filename, value in defaults.items():
                path = self._path(filename)
                if reset or not os.path.exists(path):
                    self._write(path, value)

    def load_operations(self):
        """Return a joined read model; it is not stored as one JSON document."""
        with self._locked():
            return self._read_operations_unlocked()

    def update_operations(self, operation):
        """Apply a short mutation while holding the shared data lock."""
        with self._locked():
            current = self._read_operations_unlocked()
            updated = operation(current)
            if not isinstance(updated, TestOperations):
                raise TypeError('operation must return TestOperations')
            self._write_operations_unlocked(updated)
            return updated

    def replace_all(
        self, *, test_procedures, schedule, executions, settings, version_id=None,
    ):
        """Replace plan, executions, and settings while preserving version by default."""
        settings = _as_type(settings, AppSettings)
        with self._locked():
            current_version = ''
            if version_id is None and os.path.exists(self._path(self.PLAN_FILE)):
                current_version = self._read_plan_unlocked().version_id
            operations = _as_operations(
                test_procedures, schedule, executions,
                version_id=current_version if version_id is None else version_id,
            )
            self._write_operations_unlocked(operations)
            self._write(self._path(self.SETTINGS_FILE), settings.to_dict())

    def replace_test_procedures_schedule_executions(self, procedures, schedule, executions):
        """Replace operational data while retaining the current plan version."""
        self.update_operations(lambda current: replace(
            _as_operations(procedures, schedule, executions),
            version_id=current.version_id,
        ))

    def set_version_id(self, version_id):
        """Update only the test-plan version identifier."""
        plan = self.update_plan(
            lambda current: replace(current, version_id=str(version_id or ''))
        )
        return plan.version_id

    def update_plan(self, operation):
        """Apply a typed read-modify-write callback to `test_plan.json`."""
        with self._locked():
            current = self._read_plan_unlocked()
            updated = operation(current)
            if not isinstance(updated, TestPlan):
                raise TypeError('operation must return TestPlan')
            self._write(self._path(self.PLAN_FILE), updated.to_dict())
            return updated

    def update_test_procedures(self, operation):
        """Update only the procedure tuple inside the current plan."""
        return self.update_plan(
            lambda current: replace(current, test_procedures=tuple(operation(current.test_procedures)))
        ).test_procedures

    def update_schedule(self, operation):
        """Update schedule blocks without replacing procedures or version data."""
        def update(current):
            schedule = operation(current.schedule)
            schedule = _as_type(schedule, Schedule)
            return replace(current, schedule_blocks=schedule.blocks)
        return self.update_plan(update).schedule

    def update_executions(self, operation):
        """Apply a typed read-modify-write callback to execution records."""
        with self._locked():
            current = self._read_executions_unlocked()
            updated = _as_type(operation(current), Executions)
            self._write(self._path(self.EXECUTIONS_FILE), _executions_dict(updated))
            return updated

    def replace_test_procedures(self, procedures):
        """Replace all procedures with normalized domain objects."""
        self.update_test_procedures(lambda _current: _as_test_procedures(procedures))

    def replace_schedule(self, schedule):
        """Replace all schedule blocks."""
        self.update_schedule(lambda _current: schedule)

    def replace_executions(self, executions):
        """Replace all execution runs."""
        self.update_executions(lambda _current: executions)

    def replace_settings(self, settings):
        """Replace the settings document with normalized AppSettings."""
        settings = _as_type(settings, AppSettings)
        with self._locked():
            self._write(self._path(self.SETTINGS_FILE), settings.to_dict())

    def load_test_procedures(self):
        """Load the immutable procedure tuple from the current plan."""
        return self.load_plan().test_procedures

    def load_schedule(self):
        """Load current blocks wrapped in a Schedule collection."""
        return self.load_plan().schedule

    def load_executions(self):
        """Load typed execution records."""
        with self._locked():
            return self._read_executions_unlocked()

    def load_plan(self):
        """Load the complete typed test plan."""
        with self._locked():
            return self._read_plan_unlocked()

    def load_settings(self):
        """Load typed application settings."""
        with self._locked():
            with open(self._path(self.SETTINGS_FILE), encoding='utf-8') as file:
                return AppSettings.from_dict(json.load(file))

    def _read_operations_unlocked(self):
        """Join plan and execution data; caller must already hold the lock."""
        plan = self._read_plan_unlocked()
        executions = self._read_executions_unlocked()
        return TestOperations(
            version_id=plan.version_id,
            test_procedures=plan.test_procedures,
            schedule_blocks=plan.schedule_blocks,
            execution_runs=executions.runs,
        )

    def _read_plan_unlocked(self):
        """Read the plan without acquiring a nested file lock."""
        with open(self._path(self.PLAN_FILE), encoding='utf-8') as file:
            return TestPlan.from_dict(json.load(file))

    def _read_executions_unlocked(self):
        """Read executions and adapt the persisted top-level key."""
        with open(self._path(self.EXECUTIONS_FILE), encoding='utf-8') as file:
            data = json.load(file)
        return Executions.from_dict({'runs': data.get('execution_runs', [])})

    def _write_operations_unlocked(self, operations):
        """Split a joined operation model back into its two owned documents."""
        plan = TestPlan(
            version_id=operations.version_id,
            test_procedures=operations.test_procedures,
            schedule_blocks=operations.schedule_blocks,
        )
        executions = Executions(runs=operations.execution_runs)
        self._write(self._path(self.PLAN_FILE), plan.to_dict())
        self._write(self._path(self.EXECUTIONS_FILE), _executions_dict(executions))

    def _path(self, filename):
        """Resolve a repository-owned filename inside the configured directory."""
        return os.path.join(self.data_dir, filename)

    @contextmanager
    def _locked(self):
        """Serialize all domain reads and writes through one directory lock."""
        os.makedirs(self.data_dir, exist_ok=True)
        with portalocker.Lock(self.lock_path, 'a+', timeout=10):
            yield

    @staticmethod
    def _write(path, value):
        """Write complete JSON to a temporary file before atomic replacement."""
        # 임시 파일도 대상과 같은 디렉터리에 두어 os.replace의 원자성을 보장한다.
        fd, temp_path = tempfile.mkstemp(prefix='.write-', suffix='.json', dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                json.dump(value, file, ensure_ascii=False, indent=2)
                file.write('\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


def _as_operations(test_procedures, schedule, executions, version_id=''):
    """Normalize separate feature values into the cross-feature persistence model."""
    schedule = _as_type(schedule, Schedule)
    executions = _as_type(executions, Executions)
    return TestOperations(
        version_id=str(version_id or ''),
        test_procedures=_as_test_procedures(test_procedures),
        schedule_blocks=schedule.blocks,
        execution_runs=executions.runs,
    )


def _as_type(value, domain_type):
    """Accept typed objects, serializable objects, or raw mappings at boundaries."""
    if isinstance(value, domain_type):
        return value
    if hasattr(value, 'to_dict'):
        value = value.to_dict()
    return domain_type.from_dict(value)


def _as_test_procedures(value):
    """Normalize an iterable of procedure objects or dictionaries."""
    return tuple(
        item if isinstance(item, TestProcedure) else TestProcedure.from_dict(item)
        for item in value or ()
    )


def _executions_dict(executions):
    """Adapt the domain collection key to the persisted JSON schema."""
    return {'execution_runs': [item.to_dict() for item in executions.runs]}
