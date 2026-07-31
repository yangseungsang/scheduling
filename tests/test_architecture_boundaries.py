"""Feature 간 직접 의존성 방지 테스트."""

from pathlib import Path


def _python_files(path):
    return Path(path).rglob('*.py')


def test_schedule_and_execution_do_not_import_each_other_directly():
    schedule_forbidden = (
        'from app.features.execution',
        'import app.features.execution',
    )
    execution_forbidden = (
        'from app.features.schedule',
        'import app.features.schedule',
    )

    for path in _python_files('app/features/schedule'):
        source = path.read_text(encoding='utf-8')
        assert not any(token in source for token in schedule_forbidden), path

    for path in _python_files('app/features/execution'):
        source = path.read_text(encoding='utf-8')
        assert not any(token in source for token in execution_forbidden), path
