from app.db import get_db


def get_all_tasks(status=None, category_id=None, assignee_id=None):
    db = get_db()
    query = '''
        SELECT t.id, t.title, t.description, t.category_id, t.priority,
               t.estimated_minutes, t.status, t.due_date, t.created_by,
               t.created_at, t.updated_at,
               c.name as category_name, c.color as category_color,
               GROUP_CONCAT(u.name, ', ') as assignees
        FROM tasks t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN task_assignees ta ON t.id = ta.task_id
        LEFT JOIN users u ON ta.user_id = u.id
        WHERE 1=1
    '''
    params = []
    if status:
        query += ' AND t.status = ?'
        params.append(status)
    if category_id:
        query += ' AND t.category_id = ?'
        params.append(category_id)
    if assignee_id:
        query += ' AND ta.user_id = ?'
        params.append(assignee_id)
    query += ' GROUP BY t.id ORDER BY t.created_at DESC'
    return db.execute(query, params).fetchall()


def get_task_by_id(task_id):
    db = get_db()
    task = db.execute('''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM tasks t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.id = ?
    ''', (task_id,)).fetchone()
    if task:
        assignees = db.execute('''
            SELECT u.id, u.name FROM users u
            JOIN task_assignees ta ON u.id = ta.user_id
            WHERE ta.task_id = ?
        ''', (task_id,)).fetchall()
        return dict(task), [dict(a) for a in assignees]
    return None, []


def create_task(title, description, category_id, priority, estimated_minutes,
                due_date, created_by, assignee_ids):
    db = get_db()
    cursor = db.execute('''
        INSERT INTO tasks (title, description, category_id, priority,
                           estimated_minutes, due_date, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (title, description, category_id, priority, estimated_minutes,
          due_date, created_by))
    task_id = cursor.lastrowid
    for uid in assignee_ids:
        db.execute(
            'INSERT INTO task_assignees (task_id, user_id) VALUES (?, ?)',
            (task_id, uid)
        )
    db.commit()
    return task_id


def update_task(task_id, title, description, category_id, priority,
                estimated_minutes, due_date, assignee_ids):
    db = get_db()
    db.execute('''
        UPDATE tasks
        SET title=?, description=?, category_id=?, priority=?,
            estimated_minutes=?, due_date=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    ''', (title, description, category_id, priority, estimated_minutes,
          due_date, task_id))
    db.execute('DELETE FROM task_assignees WHERE task_id = ?', (task_id,))
    for uid in assignee_ids:
        db.execute(
            'INSERT INTO task_assignees (task_id, user_id) VALUES (?, ?)',
            (task_id, uid)
        )
    db.commit()


def update_task_status(task_id, status):
    db = get_db()
    db.execute('''
        UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (status, task_id))
    db.commit()


def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()


def get_unscheduled_tasks(category_id=None):
    """스케줄에 배치되지 않은 미완료 업무 목록."""
    db = get_db()
    query = '''
        SELECT t.id, t.title, t.category_id, t.priority, t.estimated_minutes,
               t.status, t.due_date, c.name as category_name, c.color as category_color,
               GROUP_CONCAT(u.name, ', ') as assignees
        FROM tasks t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN task_assignees ta ON t.id = ta.task_id
        LEFT JOIN users u ON ta.user_id = u.id
        WHERE t.status NOT IN ('completed', 'cancelled')
        AND t.id NOT IN (
            SELECT DISTINCT task_id FROM schedule_blocks WHERE is_draft = 0
        )
    '''
    params = []
    if category_id:
        query += ' AND t.category_id = ?'
        params.append(category_id)
    query += ' GROUP BY t.id ORDER BY t.priority DESC, t.due_date ASC'
    return db.execute(query, params).fetchall()


def get_task_notes(task_id):
    db = get_db()
    return db.execute('''
        SELECT tn.id, tn.content, tn.created_at, u.name as author
        FROM task_notes tn
        LEFT JOIN users u ON tn.user_id = u.id
        WHERE tn.task_id = ?
        ORDER BY tn.created_at DESC
    ''', (task_id,)).fetchall()


def add_task_note(task_id, user_id, content):
    db = get_db()
    db.execute(
        'INSERT INTO task_notes (task_id, user_id, content) VALUES (?, ?, ?)',
        (task_id, user_id, content)
    )
    db.commit()
