from schedule.store import read_json, write_json

FILENAME = 'settings.json'

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


def get():
    settings = read_json(FILENAME)
    if not settings:
        settings = DEFAULTS.copy()
        write_json(FILENAME, settings)
    return settings


def update(data):
    settings = get()
    settings.update(data)
    write_json(FILENAME, settings)
    return settings
