"""Static JavaScript syntax checks."""

import subprocess
from pathlib import Path


def test_schedule_javascript_parses():
    """Catch syntax errors that prevent ScheduleApp modules from registering."""
    js_dir = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'schedule' / 'js'
    for path in sorted(js_dir.glob('*.js')):
        subprocess.run(['node', '--check', str(path)], check=True)


def test_schedule_rollover_confirmation_accept_and_cancel():
    """Exercise the real API wrapper to ensure cancellation never sends a save."""
    script = Path(__file__).with_name('schedule_confirmation_console.js')
    subprocess.run(['node', str(script)], check=True)
