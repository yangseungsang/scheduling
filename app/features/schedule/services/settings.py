"""Application settings used by schedule views and administration."""

from app.features.schedule.domain import AppSettings
from app.repositories import get_repository


DEFAULTS = {
    'work_start': '08:00',
    'work_end': '17:00',
    'actual_work_start': '08:30',
    'actual_work_end': '16:30',
    'lunch_start': '12:00',
    'lunch_end': '13:00',
    'breaks': [
        {'start': '09:45', 'end': '10:00'},
        {'start': '14:45', 'end': '15:00'},
    ],
    'grid_interval_minutes': 15,
    'max_schedule_days': 14,
    'block_color_by': 'assignee',
}


def _repository():
    return get_repository()


def get():
    """Return configured settings merged with display defaults."""
    saved = _repository().load_settings().to_dict()
    return {**DEFAULTS, **saved}


def update(values):
    """Merge supplied fields into the current settings document."""
    updated = {**get(), **values}
    _repository().replace_settings(AppSettings.from_dict(updated))
    return updated
