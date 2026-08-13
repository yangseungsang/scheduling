"""Application settings used by schedule views and administration."""

from flask import current_app

from app.domain.settings import AppSettings
from app.repositories import JsonDomainRepository


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
    return JsonDomainRepository(current_app.config['DOMAIN_DATA_DIR'])


def get():
    saved = _repository().load_settings().to_dict()
    return {**DEFAULTS, **saved}


def update(values):
    updated = {**get(), **values}
    _repository().replace_settings(AppSettings.from_dict(updated))
    return updated
