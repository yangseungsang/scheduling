"""Static JavaScript syntax checks."""

import subprocess
from pathlib import Path


def test_schedule_javascript_parses():
    """Catch syntax errors that prevent ScheduleApp modules from registering."""
    js_dir = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'schedule' / 'js'
    for path in sorted(js_dir.glob('*.js')):
        subprocess.run(['node', '--check', str(path)], check=True)
