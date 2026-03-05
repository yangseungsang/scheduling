from app.db import get_db


def get_all_settings():
    db = get_db()
    rows = db.execute('SELECT key, value FROM settings').fetchall()
    return {row['key']: row['value'] for row in rows}


def get_setting(key):
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else None


def update_setting(key, value):
    db = get_db()
    db.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        (key, value)
    )
    db.commit()


def get_work_hours():
    """근무시간 정보를 딕셔너리로 반환."""
    settings = get_all_settings()
    return {
        'work_start': settings.get('work_start', '09:00'),
        'work_end': settings.get('work_end', '18:00'),
        'lunch_start': settings.get('lunch_start', '12:00'),
        'lunch_end': settings.get('lunch_end', '13:00'),
    }
