"""Static JavaScript syntax checks."""

import subprocess
from pathlib import Path


def test_schedule_javascript_parses():
    """Catch syntax errors that prevent ScheduleApp modules from registering."""
    js_dir = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'schedule' / 'js'
    for path in sorted(js_dir.glob('*.js')):
        subprocess.run(['node', '--check', str(path)], check=True)


def test_schedule_javascript_does_not_auto_continue_to_next_workday():
    """Overflowing UI operations must ask to clamp, never create a next-day block."""
    js_dir = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'schedule' / 'js'
    sources = '\n'.join(path.read_text() for path in sorted(js_dir.glob('*.js')))
    assert 'nextWorkday' not in sources
    assert 'res.continuation' not in sources
    assert 'confirmWorkEndClamp' in sources
