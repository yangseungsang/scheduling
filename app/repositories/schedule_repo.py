from app.db import get_db


def get_blocks_for_date(date_str):
    db = get_db()
    return db.execute('''
        SELECT sb.id, sb.task_id, sb.assigned_date, sb.start_time, sb.end_time,
               sb.is_draft, t.title, t.priority, t.status,
               c.name as category_name, c.color as category_color
        FROM schedule_blocks sb
        JOIN tasks t ON sb.task_id = t.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE sb.assigned_date = ?
        ORDER BY sb.start_time
    ''', (date_str,)).fetchall()


def get_blocks_for_week(start_date_str, end_date_str):
    db = get_db()
    return db.execute('''
        SELECT sb.id, sb.task_id, sb.assigned_date, sb.start_time, sb.end_time,
               sb.is_draft, t.title, t.priority, t.status,
               c.name as category_name, c.color as category_color
        FROM schedule_blocks sb
        JOIN tasks t ON sb.task_id = t.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE sb.assigned_date BETWEEN ? AND ?
        ORDER BY sb.assigned_date, sb.start_time
    ''', (start_date_str, end_date_str)).fetchall()


def get_blocks_for_month(year, month):
    db = get_db()
    import calendar as cal_mod
    _, last_day = cal_mod.monthrange(year, month)
    start_date = f'{year:04d}-{month:02d}-01'
    end_date = f'{year:04d}-{month:02d}-{last_day:02d}'
    return db.execute('''
        SELECT sb.id, sb.task_id, sb.assigned_date, sb.start_time, sb.end_time,
               sb.is_draft, t.title, t.priority, t.status,
               c.name as category_name, c.color as category_color
        FROM schedule_blocks sb
        JOIN tasks t ON sb.task_id = t.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE sb.assigned_date BETWEEN ? AND ?
        ORDER BY sb.assigned_date, sb.start_time
    ''', (start_date, end_date)).fetchall()


def create_block(task_id, assigned_date, start_time, end_time, is_draft=False):
    db = get_db()
    cursor = db.execute('''
        INSERT INTO schedule_blocks (task_id, assigned_date, start_time, end_time, is_draft)
        VALUES (?, ?, ?, ?, ?)
    ''', (task_id, assigned_date, start_time, end_time, 1 if is_draft else 0))
    db.commit()
    return cursor.lastrowid


def update_block(block_id, assigned_date, start_time, end_time):
    db = get_db()
    db.execute('''
        UPDATE schedule_blocks
        SET assigned_date = ?, start_time = ?, end_time = ?
        WHERE id = ?
    ''', (assigned_date, start_time, end_time, block_id))
    db.commit()


def delete_block(block_id):
    db = get_db()
    db.execute('DELETE FROM schedule_blocks WHERE id = ?', (block_id,))
    db.commit()


def approve_draft_blocks(category_id=None):
    """초안 블록을 승인 (is_draft=0으로 변경)."""
    db = get_db()
    if category_id:
        db.execute('''
            UPDATE schedule_blocks SET is_draft = 0
            WHERE is_draft = 1 AND task_id IN (
                SELECT id FROM tasks WHERE category_id = ?
            )
        ''', (category_id,))
    else:
        db.execute('UPDATE schedule_blocks SET is_draft = 0 WHERE is_draft = 1')
    db.commit()


def discard_draft_blocks(category_id=None):
    """초안 블록 삭제."""
    db = get_db()
    if category_id:
        db.execute('''
            DELETE FROM schedule_blocks
            WHERE is_draft = 1 AND task_id IN (
                SELECT id FROM tasks WHERE category_id = ?
            )
        ''', (category_id,))
    else:
        db.execute('DELETE FROM schedule_blocks WHERE is_draft = 1')
    db.commit()


def get_occupied_slots(date_str):
    """특정 날짜의 확정된 블록 목록 (is_draft=0)."""
    db = get_db()
    return db.execute('''
        SELECT start_time, end_time
        FROM schedule_blocks
        WHERE assigned_date = ? AND is_draft = 0
        ORDER BY start_time
    ''', (date_str,)).fetchall()
