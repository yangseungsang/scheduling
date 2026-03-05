from app.db import get_db


def get_all_users():
    db = get_db()
    return db.execute(
        'SELECT id, name, email, role, created_at FROM users ORDER BY name'
    ).fetchall()


def get_user_by_id(user_id):
    db = get_db()
    return db.execute(
        'SELECT id, name, email, role FROM users WHERE id = ?', (user_id,)
    ).fetchone()


def create_user(name, email, role='member'):
    db = get_db()
    cursor = db.execute(
        'INSERT INTO users (name, email, role) VALUES (?, ?, ?)',
        (name, email, role)
    )
    db.commit()
    return cursor.lastrowid


def update_user(user_id, name, email, role):
    db = get_db()
    db.execute(
        'UPDATE users SET name = ?, email = ?, role = ? WHERE id = ?',
        (name, email, role, user_id)
    )
    db.commit()


def delete_user(user_id):
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
