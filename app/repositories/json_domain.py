"""Typed JSON repository for test operations and application settings."""

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import replace

import portalocker

from app.domain.execution import Executions
from app.domain.scheduling import Schedule
from app.domain.settings import AppSettings
from app.domain.test_procedures import TestProcedure
from app.domain.test_operations import TestOperations
from app.domain.test_plan import TestPlan


class JsonDomainRepository:
    PLAN_FILE = 'test_plan.json'
    EXECUTIONS_FILE = 'test_executions.json'
    SETTINGS_FILE = 'settings.json'

    def __init__(self, data_dir):
        self.data_dir = os.path.abspath(data_dir)
        self.lock_path = os.path.join(self.data_dir, '.data.lock')

    def initialize(self, reset=False):
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
        self.initialize()
        with self._locked():
            return self._read_operations_unlocked()

    def update_operations(self, operation):
        """Apply a short mutation while holding the shared data lock."""
        self.initialize()
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
        self.update_operations(lambda current: replace(
            _as_operations(procedures, schedule, executions),
            version_id=current.version_id,
        ))

    def set_version_id(self, version_id):
        plan = self.update_plan(
            lambda current: replace(current, version_id=str(version_id or ''))
        )
        return plan.version_id

    def update_plan(self, operation):
        self.initialize()
        with self._locked():
            current = self._read_plan_unlocked()
            updated = operation(current)
            if not isinstance(updated, TestPlan):
                raise TypeError('operation must return TestPlan')
            self._write(self._path(self.PLAN_FILE), updated.to_dict())
            return updated

    def update_test_procedures(self, operation):
        return self.update_plan(
            lambda current: replace(current, test_procedures=tuple(operation(current.test_procedures)))
        ).test_procedures

    def update_schedule(self, operation):
        def update(current):
            schedule = operation(current.schedule)
            schedule = _as_type(schedule, Schedule)
            return replace(current, schedule_blocks=schedule.blocks)
        return self.update_plan(update).schedule

    def update_executions(self, operation):
        self.initialize()
        with self._locked():
            current = self._read_executions_unlocked()
            updated = _as_type(operation(current), Executions)
            self._write(self._path(self.EXECUTIONS_FILE), _executions_dict(updated))
            return updated

    def replace_test_procedures(self, procedures):
        self.update_test_procedures(lambda _current: _as_test_procedures(procedures))

    def replace_schedule(self, schedule):
        self.update_schedule(lambda _current: schedule)

    def replace_executions(self, executions):
        self.update_executions(lambda _current: executions)

    def replace_settings(self, settings):
        settings = _as_type(settings, AppSettings)
        with self._locked():
            self._write(self._path(self.SETTINGS_FILE), settings.to_dict())

    def load_test_procedures(self):
        return self.load_plan().test_procedures

    def load_schedule(self):
        return self.load_plan().schedule

    def load_executions(self):
        self.initialize()
        with self._locked():
            return self._read_executions_unlocked()

    def load_plan(self):
        self.initialize()
        with self._locked():
            return self._read_plan_unlocked()

    def load_settings(self):
        self.initialize()
        with self._locked():
            with open(self._path(self.SETTINGS_FILE), encoding='utf-8') as file:
                return AppSettings.from_dict(json.load(file))

    def _read_operations_unlocked(self):
        plan = self._read_plan_unlocked()
        executions = self._read_executions_unlocked()
        return TestOperations(
            version_id=plan.version_id,
            test_procedures=plan.test_procedures,
            schedule_blocks=plan.schedule_blocks,
            execution_runs=executions.runs,
        )

    def _read_plan_unlocked(self):
        with open(self._path(self.PLAN_FILE), encoding='utf-8') as file:
            return TestPlan.from_dict(json.load(file))

    def _read_executions_unlocked(self):
        with open(self._path(self.EXECUTIONS_FILE), encoding='utf-8') as file:
            data = json.load(file)
        return Executions.from_dict({'runs': data.get('execution_runs', [])})

    def _write_operations_unlocked(self, operations):
        plan = TestPlan(
            version_id=operations.version_id,
            test_procedures=operations.test_procedures,
            schedule_blocks=operations.schedule_blocks,
        )
        executions = Executions(runs=operations.execution_runs)
        self._write(self._path(self.PLAN_FILE), plan.to_dict())
        self._write(self._path(self.EXECUTIONS_FILE), _executions_dict(executions))

    def _path(self, filename):
        return os.path.join(self.data_dir, filename)

    @contextmanager
    def _locked(self):
        os.makedirs(self.data_dir, exist_ok=True)
        with portalocker.Lock(self.lock_path, 'a+', timeout=10):
            yield

    @staticmethod
    def _write(path, value):
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
    schedule = _as_type(schedule, Schedule)
    executions = _as_type(executions, Executions)
    return TestOperations(
        version_id=str(version_id or ''),
        test_procedures=_as_test_procedures(test_procedures),
        schedule_blocks=schedule.blocks,
        execution_runs=executions.runs,
    )


def _as_type(value, domain_type):
    if isinstance(value, domain_type):
        return value
    if hasattr(value, 'to_dict'):
        value = value.to_dict()
    return domain_type.from_dict(value)


def _as_test_procedures(value):
    return tuple(
        item if isinstance(item, TestProcedure) else TestProcedure.from_dict(item)
        for item in value or ()
    )


def _executions_dict(executions):
    return {'execution_runs': [item.to_dict() for item in executions.runs]}
