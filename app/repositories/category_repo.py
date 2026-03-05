from app.db import get_db


def get_all_categories():
    db = get_db()
    return db.execute(
        'SELECT id, name, color FROM categories ORDER BY name'
    ).fetchall()


def get_category_by_id(category_id):
    db = get_db()
    return db.execute(
        'SELECT id, name, color FROM categories WHERE id = ?', (category_id,)
    ).fetchone()


def create_category(name, color):
    db = get_db()
    cursor = db.execute(
        'INSERT INTO categories (name, color) VALUES (?, ?)', (name, color)
    )
    db.commit()
    return cursor.lastrowid


def update_category(category_id, name, color):
    db = get_db()
    db.execute(
        'UPDATE categories SET name = ?, color = ? WHERE id = ?',
        (name, color, category_id)
    )
    db.commit()


def delete_category(category_id):
    db = get_db()
    db.execute('DELETE FROM categories WHERE id = ?', (category_id,))
    db.commit()
