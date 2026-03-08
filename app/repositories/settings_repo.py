from app.json_store import read_json, write_json

FILENAME = 'settings.json'

DEFAULTS = {
    'work_start': '09:00',
    'work_end': '18:00',
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
