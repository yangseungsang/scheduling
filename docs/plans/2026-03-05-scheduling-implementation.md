# Task Scheduling Web Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Flask + Bootstrap5 기반 팀 업무 공유 캘린더 서비스 구현 (드래그앤드랍 스케줄링, 추천 알고리즘 포함)

**Architecture:** Blueprint 기반 모듈화 구조로 blueprints(라우팅), repositories(SQL), services(비즈니스 로직) 레이어를 분리. SQLite 사용이나 config.py 한 줄 변경으로 MySQL 전환 가능하도록 설계.

**Tech Stack:** Python/Flask, Jinja2, Bootstrap 5, SortableJS, SQLite (raw SQL), Playwright (브라우저 테스트)

---

## 병렬 실행 가능한 태스크 그룹

- **Phase 1 (순차):** Task 1 → Task 2 → Task 3
- **Phase 2 (병렬):** Task 4 + Task 5 + Task 6 (DB 레이어 완료 후 동시 진행)
- **Phase 3 (순차):** Task 7 → Task 8
- **Phase 4 (병렬):** Task 9 + Task 10 + Task 11 (Blueprint 완료 후 동시 진행)
- **Phase 5 (순차):** Task 12 → Task 13 → Task 14

---

### Task 1: 프로젝트 초기 설정

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Create: `run.py`
- Create: `app/__init__.py`
- Create: `app/db.py`

**Step 1: 디렉토리 구조 생성**

```bash
mkdir -p scheduling/app/blueprints/tasks
mkdir -p scheduling/app/blueprints/schedule
mkdir -p scheduling/app/blueprints/admin
mkdir -p scheduling/app/repositories
mkdir -p scheduling/app/services
mkdir -p scheduling/app/templates/tasks
mkdir -p scheduling/app/templates/schedule
mkdir -p scheduling/app/templates/admin
mkdir -p scheduling/app/templates/components
mkdir -p scheduling/app/static/css
mkdir -p scheduling/app/static/js
mkdir -p scheduling/tests
touch scheduling/app/blueprints/__init__.py
touch scheduling/app/blueprints/tasks/__init__.py
touch scheduling/app/blueprints/schedule/__init__.py
touch scheduling/app/blueprints/admin/__init__.py
```

**Step 2: requirements.txt 작성**

```
Flask==3.0.3
python-dotenv==1.0.1
playwright==1.44.0
pytest==8.2.2
pytest-playwright==0.5.0
```

**Step 3: config.py 작성**

```python
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DATABASE = os.path.join(BASE_DIR, 'scheduling.db')
    # MySQL 전환 시 아래 주석 해제 후 DATABASE 주석 처리
    # DATABASE_URL = 'mysql+connector://user:password@localhost/scheduling'

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
```

**Step 4: app/db.py 작성**

```python
import sqlite3
import click
from flask import current_app, g


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))


@click.command('init-db')
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
```

**Step 5: app/__init__.py 작성**

```python
from flask import Flask
from config import config
from app.db import init_app as db_init_app


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db_init_app(app)

    from app.blueprints.tasks import tasks_bp
    from app.blueprints.schedule import schedule_bp
    from app.blueprints.admin import admin_bp

    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(schedule_bp, url_prefix='/schedule')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('schedule.day_view'))

    return app
```

**Step 6: run.py 작성**

```python
from app import create_app

app = create_app('development')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

**Step 7: 패키지 설치**

```bash
cd scheduling
pip install -r requirements.txt
playwright install chromium
```

Expected: 패키지 설치 완료

---

### Task 2: 데이터베이스 스키마

**Files:**
- Create: `app/schema.sql`

**Step 1: schema.sql 작성**

```sql
DROP TABLE IF EXISTS task_notes;
DROP TABLE IF EXISTS task_assignees;
DROP TABLE IF EXISTS schedule_blocks;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS settings;

CREATE TABLE settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL
);

INSERT INTO settings (key, value) VALUES
    ('work_start', '09:00'),
    ('work_end', '18:00'),
    ('lunch_start', '12:00'),
    ('lunch_end', '13:00');

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('admin', 'member')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#4A90E2',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    category_id INTEGER REFERENCES categories(id),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
    estimated_minutes INTEGER NOT NULL DEFAULT 60,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    due_date DATE,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task_assignees (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, user_id)
);

CREATE TABLE schedule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    assigned_date DATE NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    is_draft INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 샘플 데이터
INSERT INTO users (name, email, role) VALUES
    ('관리자', 'admin@example.com', 'admin'),
    ('김팀원', 'kim@example.com', 'member'),
    ('이팀원', 'lee@example.com', 'member');

INSERT INTO categories (name, color) VALUES
    ('개발', '#4A90E2'),
    ('디자인', '#7ED321'),
    ('마케팅', '#F5A623'),
    ('기획', '#9B59B6');
```

**Step 2: DB 초기화**

```bash
cd scheduling
flask --app run init-db
```

Expected: `Initialized the database.`

---

### Task 3: Repository 레이어 — Settings & Users

**Files:**
- Create: `app/repositories/settings_repo.py`
- Create: `app/repositories/user_repo.py`
- Create: `app/repositories/category_repo.py`

**Step 1: settings_repo.py 작성**

```python
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
```

**Step 2: user_repo.py 작성**

```python
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
```

**Step 3: category_repo.py 작성**

```python
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
```

---

### Task 4: Repository 레이어 — Tasks (병렬 가능)

**Files:**
- Create: `app/repositories/task_repo.py`

**Step 1: task_repo.py 작성**

```python
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
```

---

### Task 5: Repository 레이어 — Schedule (병렬 가능)

**Files:**
- Create: `app/repositories/schedule_repo.py`

**Step 1: schedule_repo.py 작성**

```python
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
    date_prefix = f'{year:04d}-{month:02d}'
    return db.execute('''
        SELECT sb.id, sb.task_id, sb.assigned_date, sb.start_time, sb.end_time,
               sb.is_draft, t.title, t.priority, t.status,
               c.name as category_name, c.color as category_color
        FROM schedule_blocks sb
        JOIN tasks t ON sb.task_id = t.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE sb.assigned_date LIKE ?
        ORDER BY sb.assigned_date, sb.start_time
    ''', (f'{date_prefix}%',)).fetchall()


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
```

---

### Task 6: 스케줄링 알고리즘 서비스 (병렬 가능)

**Files:**
- Create: `app/services/scheduler.py`

**Step 1: scheduler.py 작성**

```python
from datetime import datetime, timedelta, date


def time_to_minutes(time_str):
    """'HH:MM' 문자열을 자정 기준 분으로 변환."""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m


def minutes_to_time(minutes):
    """분을 'HH:MM' 문자열로 변환."""
    h = minutes // 60
    m = minutes % 60
    return f'{h:02d}:{m:02d}'


def get_available_slots(date_str, work_hours, occupied_slots, exclude_category_id=None,
                        existing_blocks=None):
    """
    주어진 날짜의 가용 시간 슬롯 목록을 계산.
    반환: [(start_min, end_min), ...] 형태의 가용 구간 목록
    """
    work_start = time_to_minutes(work_hours['work_start'])
    work_end = time_to_minutes(work_hours['work_end'])
    lunch_start = time_to_minutes(work_hours['lunch_start'])
    lunch_end = time_to_minutes(work_hours['lunch_end'])

    # 기본 가용 구간: 근무 시작~점심 시작, 점심 끝~근무 종료
    base_slots = [
        (work_start, lunch_start),
        (lunch_end, work_end),
    ]

    # 기존 확정 블록으로 인해 점유된 구간 제거
    busy = []
    for block in (occupied_slots or []):
        busy.append((
            time_to_minutes(block['start_time']),
            time_to_minutes(block['end_time'])
        ))

    # 점유 구간을 제외한 실제 가용 구간 계산
    free_slots = []
    for (slot_start, slot_end) in base_slots:
        free = [(slot_start, slot_end)]
        for (b_start, b_end) in busy:
            new_free = []
            for (f_start, f_end) in free:
                if b_end <= f_start or b_start >= f_end:
                    new_free.append((f_start, f_end))
                else:
                    if f_start < b_start:
                        new_free.append((f_start, b_start))
                    if b_end < f_end:
                        new_free.append((b_end, f_end))
            free = new_free
        free_slots.extend(free)

    return free_slots


def can_fit_in_day(task_minutes, available_slots, allow_lunch_break=True):
    """
    업무가 당일 가용 시간 내에 완료 가능한지 확인.
    점심 시간을 걸치는 경우 오전/오후로 분할 허용.
    """
    total_available = sum(end - start for start, end in available_slots)
    return task_minutes <= total_available


def schedule_task_in_slots(task_minutes, available_slots, allow_split=True):
    """
    업무를 가용 슬롯에 배치. 점심을 걸치는 경우 분할하여 배치.
    반환: [(start_min, end_min), ...] 배치된 블록 목록
    """
    remaining = task_minutes
    blocks = []

    for (slot_start, slot_end) in available_slots:
        if remaining <= 0:
            break
        slot_duration = slot_end - slot_start
        use = min(remaining, slot_duration)
        blocks.append((slot_start, slot_start + use))
        remaining -= use

    return blocks if remaining <= 0 else []


def generate_draft(tasks, work_hours, occupied_by_date, start_date, days=14):
    """
    스케줄링 초안 생성 알고리즘.

    Args:
        tasks: 배치할 업무 목록 (각 업무는 dict with id, estimated_minutes, priority)
        work_hours: 근무시간 설정 dict
        occupied_by_date: {date_str: [occupied_slots]} 기존 확정 블록
        start_date: 시작 날짜 (date 객체)
        days: 최대 배치 일수

    Returns:
        draft_blocks: [{'task_id': int, 'assigned_date': str,
                        'start_time': str, 'end_time': str}, ...]
    """
    priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}

    # 당일 완료 가능 업무 먼저, 같은 조건이면 소요시간 짧은 것 우선
    work_start = time_to_minutes(work_hours['work_start'])
    work_end = time_to_minutes(work_hours['work_end'])
    lunch_start = time_to_minutes(work_hours['lunch_start'])
    lunch_end = time_to_minutes(work_hours['lunch_end'])
    total_work_minutes = (work_end - work_start) - (lunch_end - lunch_start)

    def sort_key(task):
        fits_today = 1 if task['estimated_minutes'] <= total_work_minutes else 0
        return (-fits_today, priority_order.get(task['priority'], 2), task['estimated_minutes'])

    sorted_tasks = sorted(tasks, key=sort_key)

    draft_blocks = []
    # 날짜별 가용 슬롯 추적 (초안 블록도 점유로 취급)
    date_slots_used = {}

    for task in sorted_tasks:
        task_minutes = task['estimated_minutes']
        remaining = task_minutes
        placed = False

        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            date_str = current_date.strftime('%Y-%m-%d')

            occupied = list(occupied_by_date.get(date_str, []))
            # 이미 배치된 초안 블록도 점유로 추가
            for draft in date_slots_used.get(date_str, []):
                occupied.append({'start_time': draft[0], 'end_time': draft[1]})

            free_slots = get_available_slots(date_str, work_hours, occupied)

            if not free_slots:
                continue

            total_free = sum(e - s for s, e in free_slots)
            if total_free <= 0:
                continue

            blocks = schedule_task_in_slots(remaining, free_slots)
            if blocks:
                for (b_start, b_end) in blocks:
                    start_str = minutes_to_time(b_start)
                    end_str = minutes_to_time(b_end)
                    draft_blocks.append({
                        'task_id': task['id'],
                        'assigned_date': date_str,
                        'start_time': start_str,
                        'end_time': end_str,
                    })
                    if date_str not in date_slots_used:
                        date_slots_used[date_str] = []
                    date_slots_used[date_str].append((start_str, end_str))
                placed = True
                break
            else:
                # 당일에 전부 못 들어가면 가능한 만큼 채우고 나머지는 다음날
                for (slot_start, slot_end) in free_slots:
                    if remaining <= 0:
                        break
                    use = min(remaining, slot_end - slot_start)
                    start_str = minutes_to_time(slot_start)
                    end_str = minutes_to_time(slot_start + use)
                    draft_blocks.append({
                        'task_id': task['id'],
                        'assigned_date': date_str,
                        'start_time': start_str,
                        'end_time': end_str,
                    })
                    if date_str not in date_slots_used:
                        date_slots_used[date_str] = []
                    date_slots_used[date_str].append((start_str, end_str))
                    remaining -= use

                if remaining <= 0:
                    placed = True
                    break

    return draft_blocks
```

---

### Task 7: Blueprint — Tasks

**Files:**
- Create: `app/blueprints/tasks/routes.py`
- Modify: `app/blueprints/tasks/__init__.py`

**Step 1: tasks/__init__.py 작성**

```python
from flask import Blueprint

tasks_bp = Blueprint('tasks', __name__)

from app.blueprints.tasks import routes  # noqa
```

**Step 2: tasks/routes.py 작성**

```python
from flask import render_template, request, redirect, url_for, jsonify, flash
from app.blueprints.tasks import tasks_bp
from app.repositories import task_repo, category_repo, user_repo


@tasks_bp.route('/')
def task_list():
    status = request.args.get('status')
    category_id = request.args.get('category_id', type=int)
    assignee_id = request.args.get('assignee_id', type=int)
    tasks = task_repo.get_all_tasks(status=status, category_id=category_id,
                                    assignee_id=assignee_id)
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/list.html', tasks=tasks, categories=categories,
                           users=users, selected_status=status,
                           selected_category=category_id, selected_assignee=assignee_id)


@tasks_bp.route('/new', methods=['GET', 'POST'])
def create_task():
    if request.method == 'POST':
        assignee_ids = request.form.getlist('assignee_ids', type=int)
        task_id = task_repo.create_task(
            title=request.form['title'],
            description=request.form.get('description', ''),
            category_id=request.form.get('category_id', type=int),
            priority=request.form.get('priority', 'medium'),
            estimated_minutes=request.form.get('estimated_minutes', 60, type=int),
            due_date=request.form.get('due_date') or None,
            created_by=request.form.get('created_by', type=int),
            assignee_ids=assignee_ids,
        )
        flash('업무가 생성되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/form.html', categories=categories, users=users,
                           task=None, assignees=[])


@tasks_bp.route('/<int:task_id>')
def task_detail(task_id):
    task, assignees = task_repo.get_task_by_id(task_id)
    if not task:
        flash('업무를 찾을 수 없습니다.', 'danger')
        return redirect(url_for('tasks.task_list'))
    notes = task_repo.get_task_notes(task_id)
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/detail.html', task=task, assignees=assignees,
                           notes=notes, categories=categories, users=users)


@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
def edit_task(task_id):
    task, assignees = task_repo.get_task_by_id(task_id)
    if not task:
        return redirect(url_for('tasks.task_list'))
    if request.method == 'POST':
        assignee_ids = request.form.getlist('assignee_ids', type=int)
        task_repo.update_task(
            task_id=task_id,
            title=request.form['title'],
            description=request.form.get('description', ''),
            category_id=request.form.get('category_id', type=int),
            priority=request.form.get('priority', 'medium'),
            estimated_minutes=request.form.get('estimated_minutes', 60, type=int),
            due_date=request.form.get('due_date') or None,
            assignee_ids=assignee_ids,
        )
        flash('업무가 수정되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    categories = category_repo.get_all_categories()
    users = user_repo.get_all_users()
    return render_template('tasks/form.html', task=task, assignees=assignees,
                           categories=categories, users=users)


@tasks_bp.route('/<int:task_id>/status', methods=['POST'])
def update_status(task_id):
    status = request.form.get('status') or request.json.get('status')
    task_repo.update_task_status(task_id, status)
    if request.is_json:
        return jsonify({'success': True})
    flash('상태가 업데이트되었습니다.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


@tasks_bp.route('/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    task_repo.delete_task(task_id)
    flash('업무가 삭제되었습니다.', 'info')
    return redirect(url_for('tasks.task_list'))


@tasks_bp.route('/<int:task_id>/notes', methods=['POST'])
def add_note(task_id):
    content = request.form.get('content', '').strip()
    user_id = request.form.get('user_id', type=int)
    if content:
        task_repo.add_task_note(task_id, user_id, content)
        flash('메모가 추가되었습니다.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))
```

---

### Task 8: Blueprint — Admin

**Files:**
- Create: `app/blueprints/admin/routes.py`
- Modify: `app/blueprints/admin/__init__.py`

**Step 1: admin/__init__.py 작성**

```python
from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

from app.blueprints.admin import routes  # noqa
```

**Step 2: admin/routes.py 작성**

```python
from flask import render_template, request, redirect, url_for, flash
from app.blueprints.admin import admin_bp
from app.repositories import settings_repo, user_repo, category_repo


@admin_bp.route('/')
def index():
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        for key in ['work_start', 'work_end', 'lunch_start', 'lunch_end']:
            value = request.form.get(key)
            if value:
                settings_repo.update_setting(key, value)
        flash('설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings'))
    work_hours = settings_repo.get_work_hours()
    return render_template('admin/settings.html', work_hours=work_hours)


@admin_bp.route('/users')
def user_list():
    users = user_repo.get_all_users()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
def create_user():
    if request.method == 'POST':
        user_repo.create_user(
            name=request.form['name'],
            email=request.form['email'],
            role=request.form.get('role', 'member'),
        )
        flash('사용자가 추가되었습니다.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('admin/user_form.html', user=None)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    user = user_repo.get_user_by_id(user_id)
    if request.method == 'POST':
        user_repo.update_user(
            user_id=user_id,
            name=request.form['name'],
            email=request.form['email'],
            role=request.form.get('role', 'member'),
        )
        flash('사용자 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('admin/user_form.html', user=user)


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    user_repo.delete_user(user_id)
    flash('사용자가 삭제되었습니다.', 'info')
    return redirect(url_for('admin.user_list'))


@admin_bp.route('/categories')
def category_list():
    categories = category_repo.get_all_categories()
    return render_template('admin/categories.html', categories=categories)


@admin_bp.route('/categories/new', methods=['GET', 'POST'])
def create_category():
    if request.method == 'POST':
        category_repo.create_category(
            name=request.form['name'],
            color=request.form.get('color', '#4A90E2'),
        )
        flash('카테고리가 추가되었습니다.', 'success')
        return redirect(url_for('admin.category_list'))
    return render_template('admin/category_form.html', category=None)


@admin_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
def edit_category(category_id):
    category = category_repo.get_category_by_id(category_id)
    if request.method == 'POST':
        category_repo.update_category(
            category_id=category_id,
            name=request.form['name'],
            color=request.form.get('color', '#4A90E2'),
        )
        flash('카테고리가 수정되었습니다.', 'success')
        return redirect(url_for('admin.category_list'))
    return render_template('admin/category_form.html', category=category)


@admin_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
def delete_category(category_id):
    category_repo.delete_category(category_id)
    flash('카테고리가 삭제되었습니다.', 'info')
    return redirect(url_for('admin.category_list'))
```

---

### Task 9: Blueprint — Schedule (병렬 가능)

**Files:**
- Create: `app/blueprints/schedule/routes.py`
- Modify: `app/blueprints/schedule/__init__.py`

**Step 1: schedule/__init__.py 작성**

```python
from flask import Blueprint

schedule_bp = Blueprint('schedule', __name__)

from app.blueprints.schedule import routes  # noqa
```

**Step 2: schedule/routes.py 작성**

```python
from datetime import date, timedelta, datetime
from flask import render_template, request, redirect, url_for, jsonify, flash
from app.blueprints.schedule import schedule_bp
from app.repositories import schedule_repo, task_repo, category_repo, settings_repo
from app.services.scheduler import generate_draft


@schedule_bp.route('/')
def day_view():
    date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    category_id = request.args.get('category_id', type=int)
    current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    prev_date = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
    next_date = (current_date + timedelta(days=1)).strftime('%Y-%m-%d')

    blocks = schedule_repo.get_blocks_for_date(date_str)
    unscheduled = task_repo.get_unscheduled_tasks(category_id=category_id)
    categories = category_repo.get_all_categories()
    work_hours = settings_repo.get_work_hours()

    return render_template('schedule/day.html',
                           blocks=blocks, unscheduled=unscheduled,
                           categories=categories, work_hours=work_hours,
                           current_date=date_str, prev_date=prev_date,
                           next_date=next_date, selected_category=category_id)


@schedule_bp.route('/week')
def week_view():
    date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    category_id = request.args.get('category_id', type=int)
    current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)
    prev_week = (week_start - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (week_start + timedelta(days=7)).strftime('%Y-%m-%d')

    blocks = schedule_repo.get_blocks_for_week(
        week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d'))
    categories = category_repo.get_all_categories()
    work_hours = settings_repo.get_work_hours()
    week_days = [week_start + timedelta(days=i) for i in range(7)]

    blocks_by_date = {}
    for block in blocks:
        d = block['assigned_date']
        if d not in blocks_by_date:
            blocks_by_date[d] = []
        blocks_by_date[d].append(block)

    return render_template('schedule/week.html',
                           blocks_by_date=blocks_by_date, week_days=week_days,
                           categories=categories, work_hours=work_hours,
                           prev_week=prev_week, next_week=next_week,
                           selected_category=category_id)


@schedule_bp.route('/month')
def month_view():
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    category_id = request.args.get('category_id', type=int)

    blocks = schedule_repo.get_blocks_for_month(year, month)
    categories = category_repo.get_all_categories()

    blocks_by_date = {}
    for block in blocks:
        d = block['assigned_date']
        if d not in blocks_by_date:
            blocks_by_date[d] = []
        blocks_by_date[d].append(block)

    # 캘린더 그리드 생성
    import calendar
    cal = calendar.monthcalendar(year, month)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template('schedule/month.html',
                           blocks_by_date=blocks_by_date, cal=cal,
                           year=year, month=month, today=today,
                           categories=categories, selected_category=category_id,
                           prev_month=prev_month, prev_year=prev_year,
                           next_month=next_month, next_year=next_year)


# --- API Endpoints ---

@schedule_bp.route('/api/blocks', methods=['POST'])
def api_create_block():
    data = request.json
    block_id = schedule_repo.create_block(
        task_id=data['task_id'],
        assigned_date=data['assigned_date'],
        start_time=data['start_time'],
        end_time=data['end_time'],
        is_draft=data.get('is_draft', False),
    )
    return jsonify({'success': True, 'block_id': block_id})


@schedule_bp.route('/api/blocks/<int:block_id>', methods=['PUT'])
def api_update_block(block_id):
    data = request.json
    schedule_repo.update_block(
        block_id=block_id,
        assigned_date=data['assigned_date'],
        start_time=data['start_time'],
        end_time=data['end_time'],
    )
    return jsonify({'success': True})


@schedule_bp.route('/api/blocks/<int:block_id>', methods=['DELETE'])
def api_delete_block(block_id):
    schedule_repo.delete_block(block_id)
    return jsonify({'success': True})


@schedule_bp.route('/api/draft/generate', methods=['POST'])
def api_generate_draft():
    data = request.json
    category_id = data.get('category_id')
    start_date_str = data.get('start_date', date.today().strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

    work_hours = settings_repo.get_work_hours()
    tasks = task_repo.get_unscheduled_tasks(category_id=category_id)
    tasks_list = [dict(t) for t in tasks]

    # 기존 확정 블록 로드
    from app.repositories.schedule_repo import get_blocks_for_week
    end_date = (start_date + timedelta(days=14)).strftime('%Y-%m-%d')
    existing = schedule_repo.get_blocks_for_week(start_date_str, end_date)
    occupied_by_date = {}
    for block in existing:
        if not block['is_draft']:
            d = block['assigned_date']
            if d not in occupied_by_date:
                occupied_by_date[d] = []
            occupied_by_date[d].append({'start_time': block['start_time'],
                                         'end_time': block['end_time']})

    draft_blocks = generate_draft(tasks_list, work_hours, occupied_by_date, start_date)

    # 기존 초안 삭제 후 새 초안 저장
    schedule_repo.discard_draft_blocks(category_id=category_id)
    for b in draft_blocks:
        schedule_repo.create_block(
            task_id=b['task_id'],
            assigned_date=b['assigned_date'],
            start_time=b['start_time'],
            end_time=b['end_time'],
            is_draft=True,
        )

    return jsonify({'success': True, 'count': len(draft_blocks), 'blocks': draft_blocks})


@schedule_bp.route('/api/draft/approve', methods=['POST'])
def api_approve_draft():
    data = request.json or {}
    category_id = data.get('category_id')
    schedule_repo.approve_draft_blocks(category_id=category_id)
    return jsonify({'success': True})


@schedule_bp.route('/api/draft/discard', methods=['POST'])
def api_discard_draft():
    data = request.json or {}
    category_id = data.get('category_id')
    schedule_repo.discard_draft_blocks(category_id=category_id)
    return jsonify({'success': True})
```

**Step 3: repositories/__init__.py 생성**

```python
# repositories 패키지 초기화
```

`app/repositories/__init__.py` 파일 생성.

---

### Task 10: 베이스 템플릿 & 공통 컴포넌트 (병렬 가능)

**Files:**
- Create: `app/templates/base.html`
- Create: `app/templates/components/task_card.html`
- Create: `app/static/css/style.css`

**Step 1: base.html 작성**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}업무 스케줄러{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
    <link href="{{ url_for('static', filename='css/style.css') }}" rel="stylesheet">
</head>
<body class="bg-light">

<nav class="navbar navbar-expand-lg navbar-dark bg-dark">
    <div class="container-fluid">
        <a class="navbar-brand fw-bold" href="{{ url_for('schedule.day_view') }}">
            <i class="bi bi-calendar3"></i> 업무 스케줄러
        </a>
        <div class="navbar-nav flex-row gap-2 ms-auto">
            <a class="nav-link text-white" href="{{ url_for('schedule.day_view') }}">
                <i class="bi bi-calendar-day"></i> 일
            </a>
            <a class="nav-link text-white" href="{{ url_for('schedule.week_view') }}">
                <i class="bi bi-calendar-week"></i> 주
            </a>
            <a class="nav-link text-white" href="{{ url_for('schedule.month_view') }}">
                <i class="bi bi-calendar-month"></i> 월
            </a>
            <a class="nav-link text-white" href="{{ url_for('tasks.task_list') }}">
                <i class="bi bi-list-task"></i> 업무
            </a>
            <a class="nav-link text-white" href="{{ url_for('admin.settings') }}">
                <i class="bi bi-gear"></i> 설정
            </a>
        </div>
    </div>
</nav>

<div class="container-fluid py-3">
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% for category, message in messages %}
        <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
            {{ message }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
        {% endfor %}
    {% endwith %}

    {% block content %}{% endblock %}
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"></script>
<script src="{{ url_for('static', filename='js/drag_drop.js') }}"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

**Step 2: style.css 작성**

```css
/* Timeline */
.timeline-container {
    overflow-y: auto;
    max-height: calc(100vh - 200px);
    position: relative;
}

.time-slot {
    display: grid;
    grid-template-columns: 60px 1fr;
    min-height: 30px;
    border-bottom: 1px solid #eee;
}

.time-label {
    font-size: 0.75rem;
    color: #999;
    padding: 4px;
    text-align: right;
    padding-right: 8px;
    white-space: nowrap;
}

.time-slot-content {
    position: relative;
    border-left: 1px solid #dee2e6;
    min-height: 30px;
}

.lunch-slot {
    background-color: #f8f9fa;
}

.lunch-slot .time-slot-content {
    background: repeating-linear-gradient(
        45deg, #f8f9fa, #f8f9fa 5px, #e9ecef 5px, #e9ecef 10px
    );
}

/* Task Blocks */
.schedule-block {
    position: relative;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 0.8rem;
    cursor: grab;
    border-left: 4px solid rgba(0,0,0,0.2);
    margin: 2px;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    transition: box-shadow 0.15s;
}

.schedule-block:hover {
    box-shadow: 0 3px 8px rgba(0,0,0,0.2);
}

.schedule-block.is-draft {
    opacity: 0.65;
    border-style: dashed;
}

/* Priority badges */
.priority-urgent { border-left-color: #dc3545 !important; }
.priority-high    { border-left-color: #fd7e14 !important; }
.priority-medium  { border-left-color: #0d6efd !important; }
.priority-low     { border-left-color: #6c757d !important; }

/* Unscheduled task list */
.task-item {
    cursor: grab;
    transition: transform 0.15s, box-shadow 0.15s;
    user-select: none;
}

.task-item:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.task-item.sortable-chosen {
    box-shadow: 0 6px 16px rgba(0,0,0,0.2);
    transform: scale(1.02);
}

/* Drop zone highlight */
.drop-zone-active {
    background-color: rgba(13, 110, 253, 0.08);
    outline: 2px dashed #0d6efd;
}

/* Status badges */
.status-pending     { background-color: #6c757d; color: white; }
.status-in_progress { background-color: #0d6efd; color: white; }
.status-completed   { background-color: #198754; color: white; }
.status-cancelled   { background-color: #dc3545; color: white; }

/* Draft banner */
.draft-banner {
    position: sticky;
    top: 0;
    z-index: 100;
}

/* Month view */
.month-day {
    min-height: 100px;
    vertical-align: top;
    font-size: 0.85rem;
}

.month-day.today {
    background-color: #e8f4fd;
}

.month-day.other-month {
    opacity: 0.4;
}
```

---

### Task 11: 스케줄 뷰 템플릿 (병렬 가능)

**Files:**
- Create: `app/templates/schedule/day.html`
- Create: `app/templates/schedule/week.html`
- Create: `app/templates/schedule/month.html`

**Step 1: schedule/day.html 작성**

```html
{% extends 'base.html' %}
{% block title %}일간 스케줄{% endblock %}

{% block content %}
<!-- 초안 배너 -->
{% set has_draft = blocks | selectattr('is_draft', 'equalto', 1) | list | length > 0 %}
{% if has_draft %}
<div class="draft-banner alert alert-warning d-flex align-items-center justify-content-between mb-3">
    <span><i class="bi bi-exclamation-triangle-fill me-2"></i>초안이 생성되었습니다. 검토 후 승인 또는 취소하세요.</span>
    <div class="btn-group">
        <button class="btn btn-success btn-sm" onclick="approveDraft()">
            <i class="bi bi-check-circle"></i> 승인
        </button>
        <button class="btn btn-outline-danger btn-sm" onclick="discardDraft()">
            <i class="bi bi-x-circle"></i> 취소
        </button>
    </div>
</div>
{% endif %}

<div class="row g-3">
    <!-- 좌측: 미배치 업무 -->
    <div class="col-lg-3">
        <div class="card h-100">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span class="fw-semibold"><i class="bi bi-inbox"></i> 미배치 업무</span>
                <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#draftModal">
                    <i class="bi bi-magic"></i> 초안 생성
                </button>
            </div>
            <div class="card-body p-2">
                <!-- 카테고리 필터 -->
                <form method="get" class="mb-2">
                    <input type="hidden" name="date" value="{{ current_date }}">
                    <select name="category_id" class="form-select form-select-sm" onchange="this.form.submit()">
                        <option value="">전체 카테고리</option>
                        {% for cat in categories %}
                        <option value="{{ cat.id }}" {% if selected_category == cat.id %}selected{% endif %}>
                            {{ cat.name }}
                        </option>
                        {% endfor %}
                    </select>
                </form>
                <!-- 미배치 업무 목록 (드래그 소스) -->
                <div id="unscheduled-list" class="d-flex flex-column gap-2">
                    {% for task in unscheduled %}
                    <div class="task-item card p-2 priority-{{ task.priority }}"
                         data-task-id="{{ task.id }}"
                         data-estimated="{{ task.estimated_minutes }}"
                         style="border-left: 4px solid {{ task.category_color or '#4A90E2' }};">
                        <div class="fw-semibold text-truncate small">{{ task.title }}</div>
                        <div class="d-flex gap-1 flex-wrap mt-1">
                            <span class="badge" style="background:{{ task.category_color or '#4A90E2' }}">{{ task.category_name or '미분류' }}</span>
                            <span class="badge bg-secondary">{{ task.estimated_minutes }}분</span>
                            {% if task.due_date %}<span class="badge bg-warning text-dark">{{ task.due_date }}</span>{% endif %}
                        </div>
                    </div>
                    {% else %}
                    <div class="text-muted text-center py-3 small">미배치 업무 없음</div>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>

    <!-- 우측: 타임라인 -->
    <div class="col-lg-9">
        <div class="card">
            <div class="card-header d-flex align-items-center gap-3">
                <a href="{{ url_for('schedule.day_view', date=prev_date) }}" class="btn btn-outline-secondary btn-sm">
                    <i class="bi bi-chevron-left"></i>
                </a>
                <span class="fw-bold fs-5">{{ current_date }}</span>
                <a href="{{ url_for('schedule.day_view', date=next_date) }}" class="btn btn-outline-secondary btn-sm">
                    <i class="bi bi-chevron-right"></i>
                </a>
                <a href="{{ url_for('schedule.day_view', date='') }}" class="btn btn-outline-primary btn-sm ms-auto">오늘</a>
            </div>
            <div class="card-body p-0 timeline-container">
                {% set work_start_h = work_hours.work_start.split(':')[0] | int %}
                {% set work_end_h = work_hours.work_end.split(':')[0] | int %}
                {% set lunch_start_h = work_hours.lunch_start.split(':')[0] | int %}
                {% set lunch_end_h = work_hours.lunch_end.split(':')[0] | int %}

                {% for hour in range(work_start_h, work_end_h + 1) %}
                {% for minute in [0, 30] %}
                {% set time_str = '%02d:%02d' | format(hour, minute) %}
                {% set is_lunch = (hour == lunch_start_h and minute >= 0) or (hour > lunch_start_h and hour < lunch_end_h) %}
                <div class="time-slot {% if is_lunch %}lunch-slot{% endif %}"
                     data-time="{{ time_str }}"
                     data-date="{{ current_date }}">
                    <div class="time-label">{{ time_str }}</div>
                    <div class="time-slot-content drop-target"
                         data-time="{{ time_str }}"
                         data-date="{{ current_date }}">
                        {% for block in blocks %}
                        {% if block.start_time == time_str %}
                        <div class="schedule-block priority-{{ block.priority }} {% if block.is_draft %}is-draft{% endif %}"
                             style="background-color: {{ block.category_color or '#4A90E2' }}22; color: #333;"
                             data-block-id="{{ block.id }}"
                             data-task-id="{{ block.task_id }}"
                             title="{{ block.title }}">
                            <span class="fw-semibold">{{ block.title }}</span>
                            <span class="text-muted ms-1 small">{{ block.start_time }}-{{ block.end_time }}</span>
                            {% if block.is_draft %}<span class="badge bg-warning text-dark ms-1">초안</span>{% endif %}
                            <button class="btn btn-sm btn-link text-danger p-0 float-end"
                                    onclick="removeBlock({{ block.id }}, event)">
                                <i class="bi bi-x"></i>
                            </button>
                        </div>
                        {% endif %}
                        {% endfor %}
                    </div>
                </div>
                {% endfor %}
                {% endfor %}
            </div>
        </div>
    </div>
</div>

<!-- 초안 생성 모달 -->
<div class="modal fade" id="draftModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title"><i class="bi bi-magic"></i> 스케줄 초안 생성</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <p class="text-muted small">선택한 카테고리의 미배치 업무를 근무시간 내에 자동 배치합니다. 기존 확정 스케줄은 유지됩니다.</p>
                <label class="form-label">카테고리 선택</label>
                <select id="draft-category" class="form-select">
                    <option value="">전체 카테고리</option>
                    {% for cat in categories %}
                    <option value="{{ cat.id }}">{{ cat.name }}</option>
                    {% endfor %}
                </select>
                <label class="form-label mt-3">시작 날짜</label>
                <input type="date" id="draft-start-date" class="form-control" value="{{ current_date }}">
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" data-bs-dismiss="modal">취소</button>
                <button class="btn btn-primary" onclick="generateDraft()">
                    <i class="bi bi-magic"></i> 초안 생성
                </button>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
const currentDate = '{{ current_date }}';
</script>
{% endblock %}
```

**Step 2: schedule/week.html 작성**

```html
{% extends 'base.html' %}
{% block title %}주간 스케줄{% endblock %}

{% block content %}
<div class="card">
    <div class="card-header d-flex align-items-center gap-3">
        <a href="{{ url_for('schedule.week_view', date=prev_week) }}" class="btn btn-outline-secondary btn-sm">
            <i class="bi bi-chevron-left"></i>
        </a>
        <span class="fw-bold">
            {{ week_days[0].strftime('%Y.%m.%d') }} ~ {{ week_days[6].strftime('%m.%d') }}
        </span>
        <a href="{{ url_for('schedule.week_view', date=next_week) }}" class="btn btn-outline-secondary btn-sm">
            <i class="bi bi-chevron-right"></i>
        </a>
        <a href="{{ url_for('schedule.week_view') }}" class="btn btn-outline-primary btn-sm ms-auto">이번 주</a>
        <!-- 카테고리 필터 -->
        <form method="get" class="d-flex gap-2">
            <select name="category_id" class="form-select form-select-sm" onchange="this.form.submit()" style="width:auto">
                <option value="">전체 카테고리</option>
                {% for cat in categories %}
                <option value="{{ cat.id }}" {% if selected_category == cat.id %}selected{% endif %}>{{ cat.name }}</option>
                {% endfor %}
            </select>
        </form>
    </div>
    <div class="card-body p-0">
        <div class="table-responsive">
            <table class="table table-bordered mb-0">
                <thead class="table-light">
                    <tr>
                        {% set day_names = ['월', '화', '수', '목', '금', '토', '일'] %}
                        {% for i, day in enumerate(week_days) %}
                        <th class="text-center" style="width:14.28%">
                            {{ day_names[i] }}<br>
                            <a href="{{ url_for('schedule.day_view', date=day.strftime('%Y-%m-%d')) }}"
                               class="fw-bold {% if day.strftime('%Y-%m-%d') == work_hours.get('today', '') %}text-primary{% endif %}">
                                {{ day.strftime('%m/%d') }}
                            </a>
                        </th>
                        {% endfor %}
                    </tr>
                </thead>
                <tbody>
                    <tr style="vertical-align: top;">
                        {% for day in week_days %}
                        <td style="min-height: 200px;">
                            {% set date_str = day.strftime('%Y-%m-%d') %}
                            {% for block in blocks_by_date.get(date_str, []) %}
                            {% if not selected_category or block.category_id == selected_category %}
                            <div class="schedule-block mb-1 {% if block.is_draft %}is-draft{% endif %}"
                                 style="background-color: {{ block.category_color or '#4A90E2' }}33;">
                                <div class="fw-semibold small text-truncate">{{ block.title }}</div>
                                <div class="small text-muted">{{ block.start_time }}-{{ block.end_time }}</div>
                            </div>
                            {% endif %}
                            {% endfor %}
                        </td>
                        {% endfor %}
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 3: schedule/month.html 작성**

```html
{% extends 'base.html' %}
{% block title %}월간 스케줄{% endblock %}

{% block content %}
<div class="card">
    <div class="card-header d-flex align-items-center gap-3">
        <a href="{{ url_for('schedule.month_view', year=prev_year, month=prev_month) }}" class="btn btn-outline-secondary btn-sm">
            <i class="bi bi-chevron-left"></i>
        </a>
        <span class="fw-bold fs-5">{{ year }}년 {{ month }}월</span>
        <a href="{{ url_for('schedule.month_view', year=next_year, month=next_month) }}" class="btn btn-outline-secondary btn-sm">
            <i class="bi bi-chevron-right"></i>
        </a>
        <a href="{{ url_for('schedule.month_view') }}" class="btn btn-outline-primary btn-sm ms-auto">이번 달</a>
        <form method="get" class="d-flex gap-2">
            <input type="hidden" name="year" value="{{ year }}">
            <input type="hidden" name="month" value="{{ month }}">
            <select name="category_id" class="form-select form-select-sm" onchange="this.form.submit()" style="width:auto">
                <option value="">전체 카테고리</option>
                {% for cat in categories %}
                <option value="{{ cat.id }}" {% if selected_category == cat.id %}selected{% endif %}>{{ cat.name }}</option>
                {% endfor %}
            </select>
        </form>
    </div>
    <div class="card-body p-0">
        <table class="table table-bordered mb-0">
            <thead class="table-light">
                <tr>
                    {% for name in ['월', '화', '수', '목', '금', '토', '일'] %}
                    <th class="text-center">{{ name }}</th>
                    {% endfor %}
                </tr>
            </thead>
            <tbody>
                {% for week in cal %}
                <tr>
                    {% for day_num in week %}
                    {% set date_str = '%04d-%02d-%02d' | format(year, month, day_num) if day_num else '' %}
                    <td class="month-day {% if day_num and today.day == day_num and today.month == month and today.year == year %}today{% endif %} {% if not day_num %}other-month{% endif %}">
                        {% if day_num %}
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <a href="{{ url_for('schedule.day_view', date=date_str) }}" class="text-decoration-none fw-bold">
                                {{ day_num }}
                            </a>
                            <span class="badge bg-secondary rounded-pill small">
                                {{ blocks_by_date.get(date_str, []) | length }}
                            </span>
                        </div>
                        {% for block in blocks_by_date.get(date_str, [])[:3] %}
                        <div class="schedule-block mb-1 small {% if block.is_draft %}is-draft{% endif %}"
                             style="background-color: {{ block.category_color or '#4A90E2' }}33; padding: 2px 4px;">
                            <span class="text-truncate d-block">{{ block.title }}</span>
                        </div>
                        {% endfor %}
                        {% if blocks_by_date.get(date_str, []) | length > 3 %}
                        <small class="text-muted">+{{ blocks_by_date.get(date_str, []) | length - 3 }}개 더</small>
                        {% endif %}
                        {% endif %}
                    </td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

---

### Task 12: 업무 & 관리자 템플릿 (병렬 가능)

**Files:**
- Create: `app/templates/tasks/list.html`
- Create: `app/templates/tasks/form.html`
- Create: `app/templates/tasks/detail.html`
- Create: `app/templates/admin/settings.html`
- Create: `app/templates/admin/users.html`
- Create: `app/templates/admin/user_form.html`
- Create: `app/templates/admin/categories.html`
- Create: `app/templates/admin/category_form.html`

**Step 1: tasks/list.html 작성**

```html
{% extends 'base.html' %}
{% block title %}업무 목록{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
    <h4 class="mb-0"><i class="bi bi-list-task"></i> 업무 목록</h4>
    <a href="{{ url_for('tasks.create_task') }}" class="btn btn-primary">
        <i class="bi bi-plus-circle"></i> 업무 추가
    </a>
</div>

<!-- 필터 -->
<div class="card mb-3">
    <div class="card-body py-2">
        <form method="get" class="row g-2 align-items-center">
            <div class="col-auto">
                <select name="status" class="form-select form-select-sm">
                    <option value="">전체 상태</option>
                    {% for s in ['pending', 'in_progress', 'completed', 'cancelled'] %}
                    <option value="{{ s }}" {% if selected_status == s %}selected{% endif %}>
                        {{ {'pending': '대기', 'in_progress': '진행중', 'completed': '완료', 'cancelled': '취소'}[s] }}
                    </option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-auto">
                <select name="category_id" class="form-select form-select-sm">
                    <option value="">전체 카테고리</option>
                    {% for cat in categories %}
                    <option value="{{ cat.id }}" {% if selected_category == cat.id %}selected{% endif %}>{{ cat.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-auto">
                <select name="assignee_id" class="form-select form-select-sm">
                    <option value="">전체 담당자</option>
                    {% for user in users %}
                    <option value="{{ user.id }}" {% if selected_assignee == user.id %}selected{% endif %}>{{ user.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-auto">
                <button class="btn btn-outline-secondary btn-sm" type="submit">적용</button>
                <a href="{{ url_for('tasks.task_list') }}" class="btn btn-link btn-sm">초기화</a>
            </div>
        </form>
    </div>
</div>

<!-- 업무 테이블 -->
<div class="card">
    <div class="table-responsive">
        <table class="table table-hover mb-0">
            <thead class="table-light">
                <tr>
                    <th>업무명</th><th>카테고리</th><th>담당자</th>
                    <th>우선순위</th><th>예상시간</th><th>상태</th><th>마감일</th><th></th>
                </tr>
            </thead>
            <tbody>
                {% for task in tasks %}
                <tr>
                    <td><a href="{{ url_for('tasks.task_detail', task_id=task.id) }}" class="text-decoration-none fw-semibold">{{ task.title }}</a></td>
                    <td>
                        {% if task.category_name %}
                        <span class="badge" style="background:{{ task.category_color }}">{{ task.category_name }}</span>
                        {% endif %}
                    </td>
                    <td><small>{{ task.assignees or '-' }}</small></td>
                    <td>
                        {% set p_map = {'urgent':'danger','high':'warning','medium':'primary','low':'secondary'} %}
                        <span class="badge bg-{{ p_map[task.priority] }}">
                            {{ {'urgent':'긴급','high':'높음','medium':'보통','low':'낮음'}[task.priority] }}
                        </span>
                    </td>
                    <td>{{ task.estimated_minutes }}분</td>
                    <td>
                        <form method="post" action="{{ url_for('tasks.update_status', task_id=task.id) }}" class="d-inline">
                            <select name="status" class="form-select form-select-sm d-inline-block w-auto status-{{ task.status }}"
                                    onchange="this.form.submit()">
                                {% for s, label in [('pending','대기'),('in_progress','진행중'),('completed','완료'),('cancelled','취소')] %}
                                <option value="{{ s }}" {% if task.status == s %}selected{% endif %}>{{ label }}</option>
                                {% endfor %}
                            </select>
                        </form>
                    </td>
                    <td>{{ task.due_date or '-' }}</td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <a href="{{ url_for('tasks.edit_task', task_id=task.id) }}" class="btn btn-outline-secondary"><i class="bi bi-pencil"></i></a>
                            <form method="post" action="{{ url_for('tasks.delete_task', task_id=task.id) }}" onsubmit="return confirm('삭제하시겠습니까?')">
                                <button class="btn btn-outline-danger"><i class="bi bi-trash"></i></button>
                            </form>
                        </div>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="8" class="text-center text-muted py-4">업무가 없습니다.</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

**Step 2: tasks/form.html 작성**

```html
{% extends 'base.html' %}
{% block title %}{% if task %}업무 수정{% else %}업무 추가{% endif %}{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-lg-8">
        <div class="card">
            <div class="card-header fw-semibold">
                {% if task %}업무 수정{% else %}업무 추가{% endif %}
            </div>
            <div class="card-body">
                <form method="post">
                    <div class="mb-3">
                        <label class="form-label">업무명 *</label>
                        <input type="text" name="title" class="form-control" required value="{{ task.title if task else '' }}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">설명</label>
                        <textarea name="description" class="form-control" rows="3">{{ task.description if task else '' }}</textarea>
                    </div>
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label">카테고리</label>
                            <select name="category_id" class="form-select">
                                <option value="">선택 없음</option>
                                {% for cat in categories %}
                                <option value="{{ cat.id }}" {% if task and task.category_id == cat.id %}selected{% endif %}>{{ cat.name }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">우선순위</label>
                            <select name="priority" class="form-select">
                                {% for p, label in [('low','낮음'),('medium','보통'),('high','높음'),('urgent','긴급')] %}
                                <option value="{{ p }}" {% if task and task.priority == p %}selected{% elif not task and p == 'medium' %}selected{% endif %}>{{ label }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">예상 소요시간 (분)</label>
                            <input type="number" name="estimated_minutes" class="form-control" min="1" value="{{ task.estimated_minutes if task else 60 }}">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">마감일</label>
                            <input type="date" name="due_date" class="form-control" value="{{ task.due_date if task else '' }}">
                        </div>
                    </div>
                    <div class="mb-3 mt-3">
                        <label class="form-label">담당자 (복수 선택 가능)</label>
                        <div class="d-flex flex-wrap gap-2">
                            {% for user in users %}
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" name="assignee_ids"
                                       value="{{ user.id }}" id="user_{{ user.id }}"
                                       {% if user.id in (assignees | map(attribute='id') | list) %}checked{% endif %}>
                                <label class="form-check-label" for="user_{{ user.id }}">{{ user.name }}</label>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                    <div class="d-flex gap-2">
                        <button type="submit" class="btn btn-primary">저장</button>
                        <a href="{{ url_for('tasks.task_list') }}" class="btn btn-outline-secondary">취소</a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 3: tasks/detail.html 작성**

```html
{% extends 'base.html' %}
{% block title %}{{ task.title }}{% endblock %}
{% block content %}
<div class="row g-3">
    <div class="col-lg-8">
        <div class="card mb-3">
            <div class="card-header d-flex justify-content-between">
                <span class="fw-semibold">{{ task.title }}</span>
                <div class="btn-group btn-group-sm">
                    <a href="{{ url_for('tasks.edit_task', task_id=task.id) }}" class="btn btn-outline-secondary"><i class="bi bi-pencil"></i> 수정</a>
                    <form method="post" action="{{ url_for('tasks.delete_task', task_id=task.id) }}" onsubmit="return confirm('삭제하시겠습니까?')">
                        <button class="btn btn-outline-danger"><i class="bi bi-trash"></i> 삭제</button>
                    </form>
                </div>
            </div>
            <div class="card-body">
                <div class="row g-3">
                    <div class="col-md-6">
                        <small class="text-muted">카테고리</small>
                        <div><span class="badge" style="background:{{ task.category_color or '#ccc' }}">{{ task.category_name or '미분류' }}</span></div>
                    </div>
                    <div class="col-md-6">
                        <small class="text-muted">우선순위</small>
                        {% set p_map = {'urgent':'danger','high':'warning','medium':'primary','low':'secondary'} %}
                        <div><span class="badge bg-{{ p_map[task.priority] }}">{{ task.priority }}</span></div>
                    </div>
                    <div class="col-md-6">
                        <small class="text-muted">예상 소요시간</small>
                        <div>{{ task.estimated_minutes }}분</div>
                    </div>
                    <div class="col-md-6">
                        <small class="text-muted">마감일</small>
                        <div>{{ task.due_date or '-' }}</div>
                    </div>
                    <div class="col-12">
                        <small class="text-muted">담당자</small>
                        <div>{{ assignees | map(attribute='name') | join(', ') or '-' }}</div>
                    </div>
                    <div class="col-12">
                        <small class="text-muted">설명</small>
                        <div>{{ task.description or '-' }}</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 메모 -->
        <div class="card">
            <div class="card-header fw-semibold"><i class="bi bi-journal-text"></i> 메모</div>
            <div class="card-body">
                <form method="post" action="{{ url_for('tasks.add_note', task_id=task.id) }}" class="mb-3">
                    <select name="user_id" class="form-select form-select-sm mb-2" style="width:auto">
                        {% for user in users %}
                        <option value="{{ user.id }}">{{ user.name }}</option>
                        {% endfor %}
                    </select>
                    <div class="input-group">
                        <textarea name="content" class="form-control" rows="2" placeholder="메모를 입력하세요..."></textarea>
                        <button class="btn btn-primary" type="submit">추가</button>
                    </div>
                </form>
                {% for note in notes %}
                <div class="border rounded p-2 mb-2 bg-light">
                    <div class="d-flex justify-content-between">
                        <strong class="small">{{ note.author or '익명' }}</strong>
                        <small class="text-muted">{{ note.created_at }}</small>
                    </div>
                    <div class="mt-1">{{ note.content }}</div>
                </div>
                {% else %}
                <div class="text-muted text-center py-2">메모가 없습니다.</div>
                {% endfor %}
            </div>
        </div>
    </div>

    <div class="col-lg-4">
        <div class="card">
            <div class="card-header fw-semibold">상태 변경</div>
            <div class="card-body">
                <form method="post" action="{{ url_for('tasks.update_status', task_id=task.id) }}">
                    <select name="status" class="form-select mb-2">
                        {% for s, label in [('pending','대기'),('in_progress','진행중'),('completed','완료'),('cancelled','취소')] %}
                        <option value="{{ s }}" {% if task.status == s %}selected{% endif %}>{{ label }}</option>
                        {% endfor %}
                    </select>
                    <button type="submit" class="btn btn-primary w-100">상태 업데이트</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 4: admin 템플릿 작성 (settings, users, categories)**

`admin/settings.html`:
```html
{% extends 'base.html' %}
{% block title %}관리자 설정{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-lg-6">
        <div class="card mb-3">
            <div class="card-header fw-semibold"><i class="bi bi-clock"></i> 근무시간 설정</div>
            <div class="card-body">
                <form method="post">
                    <div class="row g-3">
                        <div class="col-6">
                            <label class="form-label">업무 시작</label>
                            <input type="time" name="work_start" class="form-control" value="{{ work_hours.work_start }}" step="60">
                        </div>
                        <div class="col-6">
                            <label class="form-label">업무 종료</label>
                            <input type="time" name="work_end" class="form-control" value="{{ work_hours.work_end }}" step="60">
                        </div>
                        <div class="col-6">
                            <label class="form-label">점심 시작</label>
                            <input type="time" name="lunch_start" class="form-control" value="{{ work_hours.lunch_start }}" step="60">
                        </div>
                        <div class="col-6">
                            <label class="form-label">점심 종료</label>
                            <input type="time" name="lunch_end" class="form-control" value="{{ work_hours.lunch_end }}" step="60">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary mt-3">저장</button>
                </form>
            </div>
        </div>
        <div class="d-flex gap-2">
            <a href="{{ url_for('admin.user_list') }}" class="btn btn-outline-secondary"><i class="bi bi-people"></i> 사용자 관리</a>
            <a href="{{ url_for('admin.category_list') }}" class="btn btn-outline-secondary"><i class="bi bi-tags"></i> 카테고리 관리</a>
        </div>
    </div>
</div>
{% endblock %}
```

`admin/users.html`:
```html
{% extends 'base.html' %}
{% block title %}사용자 관리{% endblock %}
{% block content %}
<div class="d-flex justify-content-between mb-3">
    <h4>사용자 관리</h4>
    <a href="{{ url_for('admin.create_user') }}" class="btn btn-primary"><i class="bi bi-person-plus"></i> 사용자 추가</a>
</div>
<div class="card">
    <table class="table mb-0">
        <thead class="table-light"><tr><th>이름</th><th>이메일</th><th>역할</th><th></th></tr></thead>
        <tbody>
        {% for user in users %}
        <tr>
            <td>{{ user.name }}</td>
            <td>{{ user.email }}</td>
            <td><span class="badge {% if user.role == 'admin' %}bg-danger{% else %}bg-secondary{% endif %}">{{ user.role }}</span></td>
            <td>
                <a href="{{ url_for('admin.edit_user', user_id=user.id) }}" class="btn btn-sm btn-outline-secondary">수정</a>
                <form method="post" action="{{ url_for('admin.delete_user', user_id=user.id) }}" class="d-inline" onsubmit="return confirm('삭제?')">
                    <button class="btn btn-sm btn-outline-danger">삭제</button>
                </form>
            </td>
        </tr>
        {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

`admin/user_form.html`:
```html
{% extends 'base.html' %}
{% block title %}{% if user %}사용자 수정{% else %}사용자 추가{% endif %}{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-lg-6">
        <div class="card">
            <div class="card-header">{% if user %}사용자 수정{% else %}사용자 추가{% endif %}</div>
            <div class="card-body">
                <form method="post">
                    <div class="mb-3">
                        <label class="form-label">이름</label>
                        <input type="text" name="name" class="form-control" required value="{{ user.name if user else '' }}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">이메일</label>
                        <input type="email" name="email" class="form-control" required value="{{ user.email if user else '' }}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">역할</label>
                        <select name="role" class="form-select">
                            <option value="member" {% if not user or user.role == 'member' %}selected{% endif %}>Member</option>
                            <option value="admin" {% if user and user.role == 'admin' %}selected{% endif %}>Admin</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">저장</button>
                    <a href="{{ url_for('admin.user_list') }}" class="btn btn-outline-secondary">취소</a>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

`admin/categories.html`:
```html
{% extends 'base.html' %}
{% block title %}카테고리 관리{% endblock %}
{% block content %}
<div class="d-flex justify-content-between mb-3">
    <h4>카테고리 관리</h4>
    <a href="{{ url_for('admin.create_category') }}" class="btn btn-primary"><i class="bi bi-plus"></i> 카테고리 추가</a>
</div>
<div class="card">
    <table class="table mb-0">
        <thead class="table-light"><tr><th>색상</th><th>이름</th><th></th></tr></thead>
        <tbody>
        {% for cat in categories %}
        <tr>
            <td><span class="badge" style="background:{{ cat.color }}; width:60px;">&nbsp;</span></td>
            <td>{{ cat.name }}</td>
            <td>
                <a href="{{ url_for('admin.edit_category', category_id=cat.id) }}" class="btn btn-sm btn-outline-secondary">수정</a>
                <form method="post" action="{{ url_for('admin.delete_category', category_id=cat.id) }}" class="d-inline" onsubmit="return confirm('삭제?')">
                    <button class="btn btn-sm btn-outline-danger">삭제</button>
                </form>
            </td>
        </tr>
        {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

`admin/category_form.html`:
```html
{% extends 'base.html' %}
{% block title %}카테고리{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-lg-6">
        <div class="card">
            <div class="card-header">{% if category %}카테고리 수정{% else %}카테고리 추가{% endif %}</div>
            <div class="card-body">
                <form method="post">
                    <div class="mb-3">
                        <label class="form-label">이름</label>
                        <input type="text" name="name" class="form-control" required value="{{ category.name if category else '' }}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">색상</label>
                        <input type="color" name="color" class="form-control form-control-color" value="{{ category.color if category else '#4A90E2' }}">
                    </div>
                    <button type="submit" class="btn btn-primary">저장</button>
                    <a href="{{ url_for('admin.category_list') }}" class="btn btn-outline-secondary">취소</a>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

---

### Task 13: 드래그앤드랍 JavaScript

**Files:**
- Create: `app/static/js/drag_drop.js`

**Step 1: drag_drop.js 작성**

```javascript
/* drag_drop.js — SortableJS 기반 스케줄 드래그앤드랍 */

document.addEventListener('DOMContentLoaded', function () {
    initDragDrop();
});

function initDragDrop() {
    const unscheduledList = document.getElementById('unscheduled-list');
    const dropTargets = document.querySelectorAll('.drop-target');

    if (!unscheduledList) return;

    // 미배치 업무 목록 → 드래그 가능
    new Sortable(unscheduledList, {
        group: {
            name: 'schedule',
            pull: 'clone',
            put: false,
        },
        sort: false,
        animation: 150,
        ghostClass: 'sortable-ghost',
        chosenClass: 'sortable-chosen',
    });

    // 각 타임슬롯 → 드롭 가능
    dropTargets.forEach(function (target) {
        new Sortable(target, {
            group: {
                name: 'schedule',
                pull: true,
                put: true,
            },
            animation: 150,
            ghostClass: 'sortable-ghost',
            onAdd: function (evt) {
                const taskId = evt.item.dataset.taskId;
                const estimatedMinutes = parseInt(evt.item.dataset.estimated || 60);
                const date = target.dataset.date;
                const startTime = target.dataset.time;

                if (!taskId || !date || !startTime) return;

                const endTime = addMinutes(startTime, estimatedMinutes);

                fetch('/schedule/api/blocks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        task_id: parseInt(taskId),
                        assigned_date: date,
                        start_time: startTime,
                        end_time: endTime,
                        is_draft: false,
                    }),
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        // 블록 렌더링 업데이트
                        evt.item.dataset.blockId = data.block_id;
                        evt.item.classList.add('schedule-block');
                        const timeSpan = document.createElement('span');
                        timeSpan.className = 'text-muted ms-1 small';
                        timeSpan.textContent = `${startTime}-${endTime}`;
                        evt.item.appendChild(timeSpan);

                        // 삭제 버튼 추가
                        const removeBtn = document.createElement('button');
                        removeBtn.className = 'btn btn-sm btn-link text-danger p-0 float-end';
                        removeBtn.innerHTML = '<i class="bi bi-x"></i>';
                        removeBtn.onclick = function(e) { removeBlock(data.block_id, e); };
                        evt.item.appendChild(removeBtn);
                    }
                })
                .catch(console.error);
            },
            onUpdate: function (evt) {
                // 같은 타임라인 내 이동
                const blockId = evt.item.dataset.blockId;
                const date = target.dataset.date;
                const startTime = target.dataset.time;
                const estimatedMinutes = parseInt(evt.item.dataset.estimated || 60);
                const endTime = addMinutes(startTime, estimatedMinutes);

                if (!blockId) return;

                fetch(`/schedule/api/blocks/${blockId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        assigned_date: date,
                        start_time: startTime,
                        end_time: endTime,
                    }),
                })
                .then(r => r.json())
                .catch(console.error);
            },
        });
    });
}

function removeBlock(blockId, event) {
    event.stopPropagation();
    if (!confirm('이 스케줄 블록을 삭제하시겠습니까?')) return;

    fetch(`/schedule/api/blocks/${blockId}`, { method: 'DELETE' })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const el = document.querySelector(`[data-block-id="${blockId}"]`);
            if (el) el.remove();
        }
    })
    .catch(console.error);
}

function generateDraft() {
    const categoryId = document.getElementById('draft-category')?.value;
    const startDate = document.getElementById('draft-start-date')?.value;

    fetch('/schedule/api/draft/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            category_id: categoryId ? parseInt(categoryId) : null,
            start_date: startDate,
        }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('draftModal'))?.hide();
            showToast(`초안 ${data.count}개 블록이 생성되었습니다.`, 'success');
            setTimeout(() => location.reload(), 1000);
        }
    })
    .catch(console.error);
}

function approveDraft() {
    fetch('/schedule/api/draft/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('초안이 승인되었습니다.', 'success');
            setTimeout(() => location.reload(), 800);
        }
    });
}

function discardDraft() {
    if (!confirm('초안을 취소하시겠습니까?')) return;
    fetch('/schedule/api/draft/discard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('초안이 취소되었습니다.', 'info');
            setTimeout(() => location.reload(), 800);
        }
    });
}

function addMinutes(timeStr, minutes) {
    const [h, m] = timeStr.split(':').map(Number);
    const total = h * 60 + m + minutes;
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} position-fixed bottom-0 end-0 m-3`;
    toast.style.zIndex = 9999;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
```

---

### Task 14: 앱 실행 검증 & Playwright 테스트

**Files:**
- Create: `tests/test_app.py`

**Step 1: Flask 앱 실행**

```bash
cd scheduling
flask --app run init-db
python run.py
```

Expected: `Running on http://0.0.0.0:5000`

**Step 2: Playwright 테스트 파일 작성**

```python
# tests/test_app.py
import pytest
from playwright.sync_api import Page, expect


BASE_URL = 'http://localhost:5000'


def test_home_redirects_to_day_view(page: Page):
    page.goto(BASE_URL)
    expect(page).to_have_url(f'{BASE_URL}/schedule/')


def test_admin_settings_save(page: Page):
    page.goto(f'{BASE_URL}/admin/settings')
    page.fill('input[name="work_start"]', '09:00')
    page.fill('input[name="work_end"]', '18:00')
    page.fill('input[name="lunch_start"]', '12:00')
    page.fill('input[name="lunch_end"]', '13:00')
    page.click('button[type="submit"]')
    expect(page.locator('.alert-success')).to_be_visible()


def test_create_category(page: Page):
    page.goto(f'{BASE_URL}/admin/categories/new')
    page.fill('input[name="name"]', '테스트카테고리')
    page.click('button[type="submit"]')
    expect(page.locator('text=테스트카테고리')).to_be_visible()


def test_create_task(page: Page):
    page.goto(f'{BASE_URL}/tasks/new')
    page.fill('input[name="title"]', '테스트 업무')
    page.fill('input[name="estimated_minutes"]', '120')
    page.click('button[type="submit"]')
    expect(page.locator('text=테스트 업무')).to_be_visible()


def test_task_list_filter(page: Page):
    page.goto(f'{BASE_URL}/tasks')
    page.select_option('select[name="status"]', 'pending')
    page.click('button[type="submit"]')
    expect(page).to_have_url(f'{BASE_URL}/tasks?status=pending')


def test_task_status_update(page: Page):
    page.goto(f'{BASE_URL}/tasks')
    # 첫 번째 업무의 상태 변경
    status_select = page.locator('select[name="status"]').first
    status_select.select_option('in_progress')
    expect(page.locator('.alert-success')).to_be_visible(timeout=3000)


def test_day_view_loads(page: Page):
    page.goto(f'{BASE_URL}/schedule/')
    expect(page.locator('text=미배치 업무')).to_be_visible()
    expect(page.locator('text=초안 생성')).to_be_visible()


def test_week_view_loads(page: Page):
    page.goto(f'{BASE_URL}/schedule/week')
    expect(page.locator('table')).to_be_visible()


def test_month_view_loads(page: Page):
    page.goto(f'{BASE_URL}/schedule/month')
    expect(page.locator('table')).to_be_visible()
    expect(page.locator('text=월')).to_be_visible()


def test_generate_draft(page: Page):
    page.goto(f'{BASE_URL}/schedule/')
    page.click('button:has-text("초안 생성")')
    expect(page.locator('#draftModal')).to_be_visible()
    page.click('#draftModal button:has-text("초안 생성")')
    # 토스트 메시지 확인
    expect(page.locator('text=초안')).to_be_visible(timeout=5000)


def test_add_task_note(page: Page):
    # 업무 상세로 이동
    page.goto(f'{BASE_URL}/tasks')
    page.locator('a.fw-semibold').first.click()
    page.fill('textarea[name="content"]', '테스트 메모입니다.')
    page.click('button:has-text("추가")')
    expect(page.locator('text=테스트 메모입니다.')).to_be_visible()
```

**Step 3: Playwright 테스트 실행**

Flask 서버가 실행 중인 상태에서:

```bash
cd scheduling
pytest tests/test_app.py -v
```

Expected: 모든 테스트 PASS

**Step 4: 최종 수동 확인**
- 브라우저에서 드래그앤드랍 동작 확인
- 초안 생성 → 승인 플로우 확인
- 일/주/월 뷰 전환 확인

---

## 주요 주의사항

1. **repositories `__init__.py`**: `app/repositories/__init__.py` 파일 필수 생성
2. **Jinja2 `enumerate`**: week.html에서 `enumerate` 사용 시 Flask 앱에 필터 등록 필요:
   ```python
   app.jinja_env.globals['enumerate'] = enumerate
   ```
3. **SQLite `ON CONFLICT`**: SQLite 3.24+ 이상 필요 (Python 3.8+ 번들 SQLite는 지원)
4. **MySQL 전환 시**: `db.py`의 `sqlite3.connect()`를 `mysql.connector.connect()`로 교체, `schema.sql`의 `INTEGER PRIMARY KEY AUTOINCREMENT`를 `INT AUTO_INCREMENT`로 변경
5. **Flask 앱 실행 전**: 반드시 `flask --app run init-db` 실행
