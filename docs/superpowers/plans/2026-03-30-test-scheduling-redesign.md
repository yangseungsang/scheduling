# Test Scheduling Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the team task scheduler into a software test procedure scheduling system with test locations, procedure IDs, multi-assignee support, software version-based calendars, same-day completion constraint, and chip-based filtering.

**Architecture:** Replace category with location, add version as a top-level entity filtering all views, extend task/block models with procedure fields and multi-assignee arrays. Keep existing repository+service+blueprint pattern. Maintain JSON file storage.

**Tech Stack:** Flask, Jinja2, Bootstrap 5, vanilla JS, JSON files with portalocker

---

### Task 1: Version Repository + Data File

**Files:**
- Create: `data/versions.json`
- Create: `app/repositories/version_repo.py`
- Create: `tests/test_version_repo.py`

- [ ] **Step 1: Create empty versions data file**

```json
[]
```

Write to `data/versions.json`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_version_repo.py`:

```python
import json
import os
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00', 'work_end': '17:00',
            'actual_work_start': '08:30', 'actual_work_end': '16:30',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [], 'grid_interval_minutes': 15,
            'max_schedule_days': 14, 'block_color_by': 'assignee',
        }, f)
    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def test_create_version(app):
    with app.app_context():
        from app.repositories import version_repo
        v = version_repo.create(name='v1.0.0', description='Initial')
        assert v['id'].startswith('v_')
        assert v['name'] == 'v1.0.0'
        assert v['is_active'] is True


def test_get_all_versions(app):
    with app.app_context():
        from app.repositories import version_repo
        version_repo.create(name='v1.0.0', description='')
        version_repo.create(name='v2.0.0', description='')
        assert len(version_repo.get_all()) == 2


def test_get_by_id(app):
    with app.app_context():
        from app.repositories import version_repo
        v = version_repo.create(name='v1.0.0', description='test')
        found = version_repo.get_by_id(v['id'])
        assert found['name'] == 'v1.0.0'
        assert version_repo.get_by_id('v_nonexist') is None


def test_update_version(app):
    with app.app_context():
        from app.repositories import version_repo
        v = version_repo.create(name='v1.0.0', description='old')
        updated = version_repo.update(v['id'], name='v1.1.0', description='new', is_active=False)
        assert updated['name'] == 'v1.1.0'
        assert updated['is_active'] is False


def test_delete_version(app):
    with app.app_context():
        from app.repositories import version_repo
        v = version_repo.create(name='v1.0.0', description='')
        version_repo.delete(v['id'])
        assert len(version_repo.get_all()) == 0


def test_get_active_versions(app):
    with app.app_context():
        from app.repositories import version_repo
        version_repo.create(name='v1.0.0', description='')
        v2 = version_repo.create(name='v2.0.0', description='')
        version_repo.update(v2['id'], name='v2.0.0', description='', is_active=False)
        active = version_repo.get_active()
        assert len(active) == 1
        assert active[0]['name'] == 'v1.0.0'
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/yangseungmin/Projects/scheduling && source venv/bin/activate && pytest tests/test_version_repo.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: Write version_repo implementation**

Create `app/repositories/version_repo.py`:

```python
from datetime import datetime

from app.json_store import read_json, write_json, generate_id

FILENAME = 'versions.json'


def get_all():
    return read_json(FILENAME)


def get_active():
    return [v for v in read_json(FILENAME) if v.get('is_active', True)]


def get_by_id(version_id):
    for v in read_json(FILENAME):
        if v['id'] == version_id:
            return v
    return None


def create(name, description=''):
    versions = read_json(FILENAME)
    version = {
        'id': generate_id('v_'),
        'name': name,
        'description': description,
        'is_active': True,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    versions.append(version)
    write_json(FILENAME, versions)
    return version


def update(version_id, name, description, is_active=True):
    versions = read_json(FILENAME)
    for v in versions:
        if v['id'] == version_id:
            v['name'] = name
            v['description'] = description
            v['is_active'] = is_active
            write_json(FILENAME, versions)
            return v
    return None


def delete(version_id):
    versions = read_json(FILENAME)
    versions = [v for v in versions if v['id'] != version_id]
    write_json(FILENAME, versions)
```

- [ ] **Step 5: Register in repositories __init__**

Add to `app/repositories/__init__.py` (if it exists) or ensure the import path works.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_version_repo.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add data/versions.json app/repositories/version_repo.py tests/test_version_repo.py
git commit -m "feat: add version repository with CRUD operations"
```

---

### Task 2: Location Repository (Replace Category)

**Files:**
- Create: `data/locations.json`
- Create: `app/repositories/location_repo.py`
- Modify: `tests/test_version_repo.py` (add location tests, or create separate)

- [ ] **Step 1: Create empty locations data file**

```json
[]
```

Write to `data/locations.json`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_location_repo.py`:

```python
import json
import os
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00', 'work_end': '17:00',
            'actual_work_start': '08:30', 'actual_work_end': '16:30',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [], 'grid_interval_minutes': 15,
            'max_schedule_days': 14, 'block_color_by': 'assignee',
        }, f)
    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


def test_create_location(app):
    with app.app_context():
        from app.repositories import location_repo
        loc = location_repo.create(name='A', color='#28a745', description='1층 시험실')
        assert loc['id'].startswith('loc_')
        assert loc['name'] == 'A'
        assert loc['description'] == '1층 시험실'


def test_get_all_locations(app):
    with app.app_context():
        from app.repositories import location_repo
        location_repo.create(name='A', color='#28a745')
        location_repo.create(name='B', color='#6f42c1')
        assert len(location_repo.get_all()) == 2


def test_update_location(app):
    with app.app_context():
        from app.repositories import location_repo
        loc = location_repo.create(name='A', color='#28a745')
        updated = location_repo.update(loc['id'], name='A-1', color='#ff0000', description='updated')
        assert updated['name'] == 'A-1'
        assert updated['description'] == 'updated'


def test_delete_location(app):
    with app.app_context():
        from app.repositories import location_repo
        loc = location_repo.create(name='A', color='#28a745')
        location_repo.delete(loc['id'])
        assert len(location_repo.get_all()) == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_location_repo.py -v`
Expected: FAIL

- [ ] **Step 4: Write location_repo implementation**

Create `app/repositories/location_repo.py`:

```python
from app.json_store import read_json, write_json, generate_id

FILENAME = 'locations.json'


def get_all():
    return read_json(FILENAME)


def get_by_id(loc_id):
    for loc in read_json(FILENAME):
        if loc['id'] == loc_id:
            return loc
    return None


def create(name, color, description=''):
    locations = read_json(FILENAME)
    loc = {
        'id': generate_id('loc_'),
        'name': name,
        'color': color,
        'description': description,
    }
    locations.append(loc)
    write_json(FILENAME, locations)
    return loc


def update(loc_id, name, color, description=''):
    locations = read_json(FILENAME)
    for loc in locations:
        if loc['id'] == loc_id:
            loc['name'] = name
            loc['color'] = color
            loc['description'] = description
            write_json(FILENAME, locations)
            return loc
    return None


def delete(loc_id):
    locations = read_json(FILENAME)
    locations = [loc for loc in locations if loc['id'] != loc_id]
    write_json(FILENAME, locations)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_location_repo.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add data/locations.json app/repositories/location_repo.py tests/test_location_repo.py
git commit -m "feat: add location repository replacing category"
```

---

### Task 3: Update Task Repository (New Fields)

**Files:**
- Modify: `app/repositories/task_repo.py`
- Create: `tests/test_task_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_task_repo.py`:

```python
import json
import os
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00', 'work_end': '17:00',
            'actual_work_start': '08:30', 'actual_work_end': '16:30',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [], 'grid_interval_minutes': 15,
            'max_schedule_days': 14, 'block_color_by': 'assignee',
        }, f)
    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


def test_create_task_new_fields(app):
    with app.app_context():
        from app.repositories import task_repo
        task = task_repo.create(
            procedure_id='ABC-001',
            version_id='v_test1234',
            assignee_ids=['u_aaa', 'u_bbb'],
            location_id='loc_test1234',
            section_name='3.2 통신 기능',
            procedure_owner='홍길동',
            test_list=['TC-001', 'TC-002'],
            estimated_hours=4.0,
            deadline='2026-04-15',
            memo='테스트 메모',
        )
        assert task['id'].startswith('t_')
        assert task['procedure_id'] == 'ABC-001'
        assert task['assignee_ids'] == ['u_aaa', 'u_bbb']
        assert task['location_id'] == 'loc_test1234'
        assert task['version_id'] == 'v_test1234'
        assert task['section_name'] == '3.2 통신 기능'
        assert task['procedure_owner'] == '홍길동'
        assert task['test_list'] == ['TC-001', 'TC-002']
        assert task['remaining_hours'] == 4.0
        assert task['status'] == 'waiting'
        assert task['memo'] == '테스트 메모'


def test_update_task_new_fields(app):
    with app.app_context():
        from app.repositories import task_repo
        task = task_repo.create(
            procedure_id='ABC-001', version_id='v_1',
            assignee_ids=['u_aaa'], location_id='loc_1',
            section_name='sec', procedure_owner='owner',
            test_list=['TC-001'], estimated_hours=4.0,
            deadline='2026-04-15', memo='',
        )
        updated = task_repo.update(
            task['id'],
            procedure_id='ABC-002', version_id='v_2',
            assignee_ids=['u_bbb', 'u_ccc'], location_id='loc_2',
            section_name='new sec', procedure_owner='new owner',
            test_list=['TC-003'], estimated_hours=6.0,
            remaining_hours=3.0, deadline='2026-05-01',
            status='in_progress', memo='updated',
        )
        assert updated['procedure_id'] == 'ABC-002'
        assert updated['assignee_ids'] == ['u_bbb', 'u_ccc']
        assert updated['remaining_hours'] == 3.0


def test_patch_task(app):
    with app.app_context():
        from app.repositories import task_repo
        task = task_repo.create(
            procedure_id='ABC-001', version_id='v_1',
            assignee_ids=['u_aaa'], location_id='loc_1',
            section_name='sec', procedure_owner='owner',
            test_list=[], estimated_hours=4.0,
            deadline='2026-04-15', memo='',
        )
        patched = task_repo.patch(task['id'], memo='patched memo')
        assert patched['memo'] == 'patched memo'
        assert patched['procedure_id'] == 'ABC-001'  # unchanged


def test_get_by_version(app):
    with app.app_context():
        from app.repositories import task_repo
        task_repo.create(
            procedure_id='ABC-001', version_id='v_1',
            assignee_ids=[], location_id='',
            section_name='', procedure_owner='',
            test_list=[], estimated_hours=2.0,
            deadline='', memo='',
        )
        task_repo.create(
            procedure_id='ABC-002', version_id='v_2',
            assignee_ids=[], location_id='',
            section_name='', procedure_owner='',
            test_list=[], estimated_hours=3.0,
            deadline='', memo='',
        )
        v1_tasks = task_repo.get_by_version('v_1')
        assert len(v1_tasks) == 1
        assert v1_tasks[0]['procedure_id'] == 'ABC-001'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_task_repo.py -v`
Expected: FAIL (signature mismatch)

- [ ] **Step 3: Rewrite task_repo with new fields**

Replace `app/repositories/task_repo.py`:

```python
from datetime import datetime

from app.json_store import read_json, write_json, generate_id

FILENAME = 'tasks.json'


def get_all():
    return read_json(FILENAME)


def get_by_id(task_id):
    for t in read_json(FILENAME):
        if t['id'] == task_id:
            return t
    return None


def get_by_version(version_id):
    return [t for t in read_json(FILENAME) if t.get('version_id') == version_id]


def create(procedure_id, version_id, assignee_ids, location_id,
           section_name, procedure_owner, test_list,
           estimated_hours, deadline, memo=''):
    tasks = read_json(FILENAME)
    task = {
        'id': generate_id('t_'),
        'procedure_id': procedure_id,
        'version_id': version_id,
        'assignee_ids': assignee_ids or [],
        'location_id': location_id,
        'section_name': section_name,
        'procedure_owner': procedure_owner,
        'test_list': test_list or [],
        'estimated_hours': estimated_hours,
        'remaining_hours': estimated_hours,
        'deadline': deadline,
        'status': 'waiting',
        'memo': memo,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    tasks.append(task)
    write_json(FILENAME, tasks)
    return task


def update(task_id, procedure_id, version_id, assignee_ids, location_id,
           section_name, procedure_owner, test_list,
           estimated_hours, remaining_hours, deadline, status, memo=''):
    tasks = read_json(FILENAME)
    for t in tasks:
        if t['id'] == task_id:
            t['procedure_id'] = procedure_id
            t['version_id'] = version_id
            t['assignee_ids'] = assignee_ids or []
            t['location_id'] = location_id
            t['section_name'] = section_name
            t['procedure_owner'] = procedure_owner
            t['test_list'] = test_list or []
            t['estimated_hours'] = estimated_hours
            t['remaining_hours'] = remaining_hours
            t['deadline'] = deadline
            t['status'] = status
            t['memo'] = memo
            write_json(FILENAME, tasks)
            return t
    return None


def patch(task_id, **kwargs):
    tasks = read_json(FILENAME)
    for t in tasks:
        if t['id'] == task_id:
            for k, v in kwargs.items():
                t[k] = v
            write_json(FILENAME, tasks)
            return t
    return None


def delete(task_id):
    tasks = read_json(FILENAME)
    tasks = [t for t in tasks if t['id'] != task_id]
    write_json(FILENAME, tasks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_task_repo.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/repositories/task_repo.py tests/test_task_repo.py
git commit -m "feat: update task repository with procedure/version/multi-assignee fields"
```

---

### Task 4: Update Schedule Repository (New Fields)

**Files:**
- Modify: `app/repositories/schedule_repo.py`
- Create: `tests/test_schedule_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_schedule_repo.py`:

```python
import json
import os
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00', 'work_end': '17:00',
            'actual_work_start': '08:30', 'actual_work_end': '16:30',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [], 'grid_interval_minutes': 15,
            'max_schedule_days': 14, 'block_color_by': 'assignee',
        }, f)
    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


def test_create_block_new_fields(app):
    with app.app_context():
        from app.repositories import schedule_repo
        block = schedule_repo.create(
            task_id='t_test',
            assignee_ids=['u_aaa', 'u_bbb'],
            location_id='loc_test',
            version_id='v_test',
            date='2026-04-01',
            start_time='08:30',
            end_time='12:00',
        )
        assert block['id'].startswith('sb_')
        assert block['assignee_ids'] == ['u_aaa', 'u_bbb']
        assert block['location_id'] == 'loc_test'
        assert block['version_id'] == 'v_test'


def test_get_by_version(app):
    with app.app_context():
        from app.repositories import schedule_repo
        schedule_repo.create(
            task_id='t_1', assignee_ids=['u_a'], location_id='loc_1',
            version_id='v_1', date='2026-04-01',
            start_time='08:30', end_time='10:00',
        )
        schedule_repo.create(
            task_id='t_2', assignee_ids=['u_b'], location_id='loc_2',
            version_id='v_2', date='2026-04-01',
            start_time='10:00', end_time='12:00',
        )
        v1_blocks = schedule_repo.get_by_version('v_1')
        assert len(v1_blocks) == 1


def test_get_by_location_and_date(app):
    with app.app_context():
        from app.repositories import schedule_repo
        schedule_repo.create(
            task_id='t_1', assignee_ids=['u_a'], location_id='loc_1',
            version_id='v_1', date='2026-04-01',
            start_time='08:30', end_time='10:00',
        )
        schedule_repo.create(
            task_id='t_2', assignee_ids=['u_b'], location_id='loc_2',
            version_id='v_1', date='2026-04-01',
            start_time='08:30', end_time='10:00',
        )
        loc1 = schedule_repo.get_by_location_and_date('loc_1', '2026-04-01')
        assert len(loc1) == 1


def test_update_block_allowed_fields(app):
    with app.app_context():
        from app.repositories import schedule_repo
        block = schedule_repo.create(
            task_id='t_1', assignee_ids=['u_a'], location_id='loc_1',
            version_id='v_1', date='2026-04-01',
            start_time='08:30', end_time='10:00',
        )
        updated = schedule_repo.update(block['id'], location_id='loc_2', start_time='09:00')
        assert updated['location_id'] == 'loc_2'
        assert updated['start_time'] == '09:00'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schedule_repo.py -v`
Expected: FAIL

- [ ] **Step 3: Rewrite schedule_repo with new fields**

Replace `app/repositories/schedule_repo.py`:

```python
from app.json_store import read_json, write_json, generate_id

FILENAME = 'schedule_blocks.json'


def get_all():
    return read_json(FILENAME)


def get_by_id(block_id):
    for b in read_json(FILENAME):
        if b['id'] == block_id:
            return b
    return None


def get_by_date(date_str):
    return [b for b in read_json(FILENAME) if b['date'] == date_str]


def get_by_date_range(start_date, end_date):
    return [
        b for b in read_json(FILENAME)
        if start_date <= b['date'] <= end_date
    ]


def get_by_version(version_id):
    return [b for b in read_json(FILENAME) if b.get('version_id') == version_id]


def get_by_assignee(assignee_id):
    return [b for b in read_json(FILENAME) if assignee_id in b.get('assignee_ids', [])]


def get_by_location_and_date(location_id, date_str):
    return [
        b for b in read_json(FILENAME)
        if b.get('location_id') == location_id and b['date'] == date_str
    ]


def create(task_id, assignee_ids, location_id, version_id,
           date, start_time, end_time,
           is_draft=False, is_locked=False, origin='manual',
           block_status='pending'):
    blocks = read_json(FILENAME)
    block = {
        'id': generate_id('sb_'),
        'task_id': task_id,
        'assignee_ids': assignee_ids or [],
        'location_id': location_id,
        'version_id': version_id,
        'date': date,
        'start_time': start_time,
        'end_time': end_time,
        'is_draft': is_draft,
        'is_locked': is_locked,
        'origin': origin,
        'block_status': block_status,
        'memo': '',
    }
    blocks.append(block)
    write_json(FILENAME, blocks)
    return block


ALLOWED_FIELDS = {
    'date', 'start_time', 'end_time', 'is_draft', 'is_locked',
    'block_status', 'task_id', 'assignee_ids', 'location_id',
    'version_id', 'origin', 'memo',
}


def update(block_id, **kwargs):
    blocks = read_json(FILENAME)
    for b in blocks:
        if b['id'] == block_id:
            for key, value in kwargs.items():
                if key in ALLOWED_FIELDS:
                    b[key] = value
            write_json(FILENAME, blocks)
            return b
    return None


def delete(block_id):
    blocks = read_json(FILENAME)
    blocks = [b for b in blocks if b['id'] != block_id]
    write_json(FILENAME, blocks)


def delete_drafts():
    blocks = read_json(FILENAME)
    blocks = [b for b in blocks if not b.get('is_draft')]
    write_json(FILENAME, blocks)


def approve_drafts():
    blocks = read_json(FILENAME)
    for b in blocks:
        if b.get('is_draft'):
            b['is_draft'] = False
    write_json(FILENAME, blocks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schedule_repo.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/repositories/schedule_repo.py tests/test_schedule_repo.py
git commit -m "feat: update schedule repository with location/version/multi-assignee"
```

---

### Task 5: Update Settings Repository

**Files:**
- Modify: `app/repositories/settings_repo.py`
- Modify: `data/settings.json`

- [ ] **Step 1: Update settings_repo defaults**

Replace `app/repositories/settings_repo.py`:

```python
from app.json_store import read_json, write_json

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
```

- [ ] **Step 2: Update settings.json data file**

```json
{
  "work_start": "08:00",
  "work_end": "17:00",
  "actual_work_start": "08:30",
  "actual_work_end": "16:30",
  "lunch_start": "12:00",
  "lunch_end": "13:00",
  "breaks": [
    {"start": "09:45", "end": "10:00"},
    {"start": "14:45", "end": "15:00"}
  ],
  "grid_interval_minutes": 15,
  "max_schedule_days": 14,
  "block_color_by": "assignee"
}
```

- [ ] **Step 3: Commit**

```bash
git add app/repositories/settings_repo.py data/settings.json
git commit -m "feat: add actual_work_start/end to settings"
```

---

### Task 6: Update Scheduler Service (Same-Day + Location + Version)

**Files:**
- Modify: `app/services/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scheduler.py`:

```python
import json
import os
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00', 'work_end': '17:00',
            'actual_work_start': '08:30', 'actual_work_end': '16:30',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
            'grid_interval_minutes': 15,
            'max_schedule_days': 14,
            'block_color_by': 'assignee',
        }, f)
    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


def _make_task(app, procedure_id='ABC-001', version_id='v_1',
               assignee_ids=None, location_id='loc_1',
               hours=3.0, deadline='2026-04-15'):
    with app.app_context():
        from app.repositories import task_repo
        return task_repo.create(
            procedure_id=procedure_id, version_id=version_id,
            assignee_ids=assignee_ids or ['u_a'],
            location_id=location_id,
            section_name='test', procedure_owner='owner',
            test_list=[], estimated_hours=hours,
            deadline=deadline, memo='',
        )


def test_same_day_completion(app):
    """Task must be placed entirely within one day."""
    task = _make_task(app, hours=3.0)
    with app.app_context():
        from app.services.scheduler import generate_draft_schedule
        result = generate_draft_schedule(version_id='v_1')
        # Should be placed in exactly 1 block (same-day)
        assert len(result['placed']) >= 1
        # All blocks for same task should be on the same date
        dates = set(b['date'] for b in result['placed'] if b['task_id'] == task['id'])
        assert len(dates) == 1


def test_task_exceeding_daily_hours_unplaced(app):
    """Task that exceeds daily work hours should be unplaced."""
    _make_task(app, hours=20.0)  # Way more than a day
    with app.app_context():
        from app.services.scheduler import generate_draft_schedule
        result = generate_draft_schedule(version_id='v_1')
        assert len(result['unplaced']) == 1


def test_version_filter(app):
    """Only tasks matching version_id should be scheduled."""
    _make_task(app, procedure_id='ABC-001', version_id='v_1', hours=2.0)
    _make_task(app, procedure_id='DEF-001', version_id='v_2', hours=2.0)
    with app.app_context():
        from app.services.scheduler import generate_draft_schedule
        result = generate_draft_schedule(version_id='v_1')
        task_ids_placed = set(b['task_id'] for b in result['placed'])
        # Only v_1 tasks should be placed
        from app.repositories import task_repo
        for tid in task_ids_placed:
            t = task_repo.get_by_id(tid)
            assert t['version_id'] == 'v_1'


def test_location_conflict_prevention(app):
    """Two tasks at same location/time should not overlap."""
    _make_task(app, procedure_id='ABC-001', version_id='v_1',
               assignee_ids=['u_a'], location_id='loc_1', hours=3.0)
    _make_task(app, procedure_id='ABC-002', version_id='v_1',
               assignee_ids=['u_b'], location_id='loc_1', hours=3.0)
    with app.app_context():
        from app.services.scheduler import generate_draft_schedule
        from app.utils.time_utils import time_to_minutes
        result = generate_draft_schedule(version_id='v_1')
        # Check no location overlap on same date
        blocks_by_date_loc = {}
        for b in result['placed']:
            key = (b['date'], b['location_id'])
            blocks_by_date_loc.setdefault(key, []).append(b)
        for key, blist in blocks_by_date_loc.items():
            for i, b1 in enumerate(blist):
                for b2 in blist[i+1:]:
                    s1, e1 = time_to_minutes(b1['start_time']), time_to_minutes(b1['end_time'])
                    s2, e2 = time_to_minutes(b2['start_time']), time_to_minutes(b2['end_time'])
                    assert not (s1 < e2 and s2 < e1), f"Location overlap: {b1} vs {b2}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL

- [ ] **Step 3: Rewrite scheduler.py**

Replace `app/services/scheduler.py`:

```python
from datetime import datetime, timedelta

from app.repositories import task_repo, schedule_repo, settings_repo

PRIORITY_ORDER = {'high': 0, 'medium': 1, 'low': 2}


def generate_draft_schedule(version_id):
    """Generate a draft schedule for tasks in the given version.

    Same-day completion: each task is placed entirely within one day.
    Prevents: assignee time overlap, location time overlap.
    """
    settings = settings_repo.get()
    max_days = settings.get('max_schedule_days', 14)

    # 1. Get schedulable tasks for this version
    tasks = [
        t for t in task_repo.get_all()
        if t.get('version_id') == version_id
        and t['status'] != 'completed'
        and t.get('remaining_hours', 0) > 0
    ]

    # 2. Sort: deadline ascending, then procedure_id
    tasks.sort(key=lambda t: (
        t.get('deadline') or '9999-12-31',
        t.get('procedure_id', ''),
    ))

    # 3. Delete existing drafts
    schedule_repo.delete_drafts()

    # 4. Get confirmed blocks
    confirmed_blocks = [b for b in schedule_repo.get_all() if not b.get('is_draft')]

    # Track all blocks (confirmed + newly placed)
    all_blocks = list(confirmed_blocks)

    placed = []
    unplaced = []

    # Calculate daily available work hours
    daily_work_hours = _daily_available_hours(settings)

    for task in tasks:
        hours_needed = task['remaining_hours']

        # Same-day constraint: if exceeds daily hours, cannot place
        if hours_needed > daily_work_hours:
            unplaced.append({
                'task': task,
                'remaining_unscheduled_hours': hours_needed,
                'reason': f'소요시간({hours_needed}h)이 일일 가용시간({daily_work_hours}h)을 초과합니다.',
            })
            continue

        # Already fully scheduled by confirmed blocks?
        confirmed_for_task = [b for b in confirmed_blocks if b['task_id'] == task['id']]
        already_scheduled = _calculate_work_hours(confirmed_for_task, settings)
        if already_scheduled >= hours_needed:
            continue

        task_placed = False

        for day_offset in range(max_days):
            date_str = (datetime.now() + timedelta(days=day_offset)).strftime('%Y-%m-%d')

            # Find a slot that fits the entire task (same-day)
            slot = _find_slot_for_task(
                date_str, task, hours_needed, all_blocks, settings,
            )
            if slot:
                start_time, end_time = slot
                block = schedule_repo.create(
                    task_id=task['id'],
                    assignee_ids=task['assignee_ids'],
                    location_id=task['location_id'],
                    version_id=version_id,
                    date=date_str,
                    start_time=start_time,
                    end_time=end_time,
                    is_draft=True,
                    is_locked=False,
                    origin='auto',
                )
                placed.append(block)
                all_blocks.append(block)
                task_placed = True
                break

        if not task_placed:
            unplaced.append({
                'task': task,
                'remaining_unscheduled_hours': hours_needed,
            })

    return {'placed': placed, 'unplaced': unplaced}


def _find_slot_for_task(date_str, task, hours_needed, all_blocks, settings):
    """Find a contiguous slot on date_str that fits hours_needed.

    Must not overlap with any assignee's blocks or the location's blocks.
    """
    actual_start = settings.get('actual_work_start', '08:30')
    actual_end = settings.get('actual_work_end', '16:30')

    # Collect occupied ranges for ALL assignees of this task
    assignee_occupied = []
    for b in all_blocks:
        if b['date'] != date_str:
            continue
        block_assignees = b.get('assignee_ids', [])
        if any(a in block_assignees for a in task['assignee_ids']):
            assignee_occupied.append((_parse_time(b['start_time']), _parse_time(b['end_time'])))

    # Collect occupied ranges for the location
    location_occupied = []
    for b in all_blocks:
        if b['date'] != date_str:
            continue
        if b.get('location_id') == task['location_id'] and task['location_id']:
            location_occupied.append((_parse_time(b['start_time']), _parse_time(b['end_time'])))

    # Merge all occupied ranges
    all_occupied = assignee_occupied + location_occupied
    all_occupied.sort()

    # Build free ranges within actual work time
    free = _get_free_ranges(actual_start, actual_end, all_occupied)

    # Find first free range that can fit the task (accounting for breaks)
    for free_start_str, free_end_str in free:
        available_hours = _work_hours_in_range(free_start_str, free_end_str, settings)
        if available_hours >= hours_needed:
            end_time = _compute_end_for_work_hours(free_start_str, hours_needed, settings)
            return (free_start_str, end_time)

    return None


def _get_free_ranges(work_start, work_end, occupied):
    """Return list of (start_str, end_str) free ranges."""
    current = _parse_time(work_start)
    end = _parse_time(work_end)
    free = []

    # Deduplicate and merge occupied
    merged = _merge_ranges(occupied)

    for occ_start, occ_end in merged:
        if current < occ_start:
            free.append((_format_time(current), _format_time(occ_start)))
        current = max(current, occ_end)

    if current < end:
        free.append((_format_time(current), _format_time(end)))

    return free


def _merge_ranges(ranges):
    """Merge overlapping time ranges."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges)
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _daily_available_hours(settings):
    """Calculate total available work hours in a day."""
    actual_start = settings.get('actual_work_start', '08:30')
    actual_end = settings.get('actual_work_end', '16:30')
    return _work_hours_in_range(actual_start, actual_end, settings)


def approve_drafts():
    """Approve all draft blocks and update task remaining hours."""
    settings = settings_repo.get()
    draft_blocks = [b for b in schedule_repo.get_all() if b.get('is_draft')]

    schedule_repo.approve_drafts()

    hours_by_task = {}
    for block in draft_blocks:
        work_hours = _work_hours_in_range(block['start_time'], block['end_time'], settings)
        hours_by_task.setdefault(block['task_id'], 0)
        hours_by_task[block['task_id']] += work_hours

    for task_id, hours in hours_by_task.items():
        task = task_repo.get_by_id(task_id)
        if not task:
            continue
        new_remaining = max(0, task['remaining_hours'] - hours)
        new_status = 'completed' if new_remaining <= 0 else task['status']
        task_repo.patch(
            task_id,
            remaining_hours=round(new_remaining, 2),
            status=new_status,
        )


def discard_drafts():
    schedule_repo.delete_drafts()


def _get_break_periods(settings):
    periods = [(settings['lunch_start'], settings['lunch_end'])]
    for brk in settings.get('breaks', []):
        periods.append((brk['start'], brk['end']))
    periods.sort()
    return periods


def _work_hours_in_range(start_str, end_str, settings):
    start = _parse_time(start_str)
    end = _parse_time(end_str)
    total_min = (end - start).total_seconds() / 60.0
    for bs, be in _get_break_periods(settings):
        b_start = _parse_time(bs)
        b_end = _parse_time(be)
        ov_start = max(start, b_start)
        ov_end = min(end, b_end)
        if ov_start < ov_end:
            total_min -= (ov_end - ov_start).total_seconds() / 60.0
    return max(0.0, total_min / 60.0)


def _compute_end_for_work_hours(start_str, work_hours, settings):
    breaks = _get_break_periods(settings)
    work_end = settings.get('actual_work_end', '16:30')
    current = _parse_time(start_str)
    remaining_min = work_hours * 60.0
    end_limit = _parse_time(work_end)
    interval = settings.get('grid_interval_minutes', 15)

    while remaining_min > 0 and current < end_limit:
        in_break = False
        for bs, be in breaks:
            b_start = _parse_time(bs)
            b_end = _parse_time(be)
            if b_start <= current < b_end:
                current = b_end
                in_break = True
                break
        if in_break:
            continue

        next_break_start = end_limit
        for bs, be in breaks:
            b_start = _parse_time(bs)
            if b_start > current and b_start < next_break_start:
                next_break_start = b_start

        available_min = (next_break_start - current).total_seconds() / 60.0
        if available_min >= remaining_min:
            current += timedelta(minutes=remaining_min)
            remaining_min = 0
        else:
            remaining_min -= available_min
            for bs, be in breaks:
                if _parse_time(bs) == next_break_start:
                    current = _parse_time(be)
                    break

    result_min = int((current - datetime(1900, 1, 1)).total_seconds() / 60)
    snapped = ((result_min + interval - 1) // interval) * interval
    result = datetime(1900, 1, 1) + timedelta(minutes=snapped)
    if result > end_limit:
        result = end_limit
    return _format_time(result)


def _calculate_work_hours(blocks, settings):
    total = 0.0
    for b in blocks:
        total += _work_hours_in_range(b['start_time'], b['end_time'], settings)
    return total


def _parse_time(time_str):
    return datetime.strptime(time_str, '%H:%M')


def _format_time(dt):
    return dt.strftime('%H:%M')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler with same-day completion, location conflict, version filter"
```

---

### Task 7: Procedure Service (Mock/External Lookup)

**Files:**
- Create: `app/services/procedure_service.py`
- Create: `data/procedures.json`

- [ ] **Step 1: Create mock procedures data**

Write `data/procedures.json`:

```json
[
  {
    "procedure_id": "SYS-001",
    "section_name": "3.1 시스템 초기화",
    "procedure_owner": "김민수",
    "test_list": ["TC-001", "TC-002", "TC-003"]
  },
  {
    "procedure_id": "SYS-002",
    "section_name": "3.2 통신 기능",
    "procedure_owner": "이지은",
    "test_list": ["TC-004", "TC-005"]
  },
  {
    "procedure_id": "NAV-001",
    "section_name": "4.1 항법 연산",
    "procedure_owner": "박준혁",
    "test_list": ["TC-010", "TC-011", "TC-012"]
  }
]
```

- [ ] **Step 2: Write procedure_service**

Create `app/services/procedure_service.py`:

```python
from app.json_store import read_json

FILENAME = 'procedures.json'


def lookup(procedure_id):
    """Look up procedure info by ID.

    Currently reads from mock data file.
    In production, replace with external API call.
    """
    procedures = read_json(FILENAME)
    for p in procedures:
        if p['procedure_id'] == procedure_id:
            return {
                'section_name': p['section_name'],
                'procedure_owner': p['procedure_owner'],
                'test_list': p['test_list'],
            }
    return None
```

- [ ] **Step 3: Commit**

```bash
git add data/procedures.json app/services/procedure_service.py
git commit -m "feat: add procedure lookup service with mock data"
```

---

### Task 8: Update Admin Routes (Locations + Versions)

**Files:**
- Modify: `app/blueprints/admin/routes.py`

- [ ] **Step 1: Rewrite admin routes**

Replace `app/blueprints/admin/routes.py` — change all `category_repo` references to `location_repo`, add version CRUD routes:

```python
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash

from app.repositories import user_repo, location_repo, version_repo, settings_repo

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _snap_time(time_str, interval=15):
    if not time_str or ':' not in time_str:
        return time_str
    parts = time_str.split(':')
    h, m = int(parts[0]), int(parts[1])
    m = round(m / interval) * interval
    if m >= 60:
        h += 1
        m = 0
    return f'{h:02d}:{m:02d}'


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        grid = int(request.form.get('grid_interval_minutes', 15))
        data = {
            'work_start': _snap_time(request.form['work_start'], grid),
            'work_end': _snap_time(request.form['work_end'], grid),
            'actual_work_start': _snap_time(request.form.get('actual_work_start', '08:30'), grid),
            'actual_work_end': _snap_time(request.form.get('actual_work_end', '16:30'), grid),
            'lunch_start': _snap_time(request.form['lunch_start'], grid),
            'lunch_end': _snap_time(request.form['lunch_end'], grid),
            'grid_interval_minutes': grid,
            'max_schedule_days': int(request.form.get('max_schedule_days', 14)),
            'block_color_by': request.form.get('block_color_by', 'assignee'),
        }
        break_starts = request.form.getlist('break_start')
        break_ends = request.form.getlist('break_end')
        data['breaks'] = [
            {'start': _snap_time(s, grid), 'end': _snap_time(e, grid)}
            for s, e in zip(break_starts, break_ends)
            if s and e
        ]
        settings_repo.update(data)
        flash('설정이 저장되었습니다.', 'success')
        return redirect(url_for('admin.settings'))
    return render_template('admin/settings.html', settings=settings_repo.get())


# ---------------------------------------------------------------------------
# Users (unchanged pattern)
# ---------------------------------------------------------------------------

@admin_bp.route('/users')
def users():
    return render_template('admin/users.html', users=user_repo.get_all())


@admin_bp.route('/users/new', methods=['GET', 'POST'])
def user_new():
    if request.method == 'POST':
        user_repo.create(
            name=request.form['name'],
            role=request.form['role'],
            color=request.form['color'],
        )
        flash('팀원이 추가되었습니다.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=None)


@admin_bp.route('/users/<user_id>/edit', methods=['GET', 'POST'])
def user_edit(user_id):
    user = user_repo.get_by_id(user_id)
    if not user:
        flash('팀원을 찾을 수 없습니다.', 'danger')
        return redirect(url_for('admin.users'))
    if request.method == 'POST':
        user_repo.update(
            user_id,
            name=request.form['name'],
            role=request.form['role'],
            color=request.form['color'],
        )
        flash('팀원 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=user)


@admin_bp.route('/users/<user_id>/delete', methods=['POST'])
def user_delete(user_id):
    user_repo.delete(user_id)
    flash('팀원이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.users'))


# ---------------------------------------------------------------------------
# Locations (replaces categories)
# ---------------------------------------------------------------------------

@admin_bp.route('/locations')
def locations():
    return render_template('admin/locations.html', locations=location_repo.get_all())


@admin_bp.route('/locations/new', methods=['GET', 'POST'])
def location_new():
    if request.method == 'POST':
        location_repo.create(
            name=request.form['name'],
            color=request.form['color'],
            description=request.form.get('description', ''),
        )
        flash('시험장소가 추가되었습니다.', 'success')
        return redirect(url_for('admin.locations'))
    return render_template('admin/location_form.html', location=None)


@admin_bp.route('/locations/<loc_id>/edit', methods=['GET', 'POST'])
def location_edit(loc_id):
    loc = location_repo.get_by_id(loc_id)
    if not loc:
        flash('시험장소를 찾을 수 없습니다.', 'danger')
        return redirect(url_for('admin.locations'))
    if request.method == 'POST':
        location_repo.update(
            loc_id,
            name=request.form['name'],
            color=request.form['color'],
            description=request.form.get('description', ''),
        )
        flash('시험장소가 수정되었습니다.', 'success')
        return redirect(url_for('admin.locations'))
    return render_template('admin/location_form.html', location=loc)


@admin_bp.route('/locations/<loc_id>/delete', methods=['POST'])
def location_delete(loc_id):
    location_repo.delete(loc_id)
    flash('시험장소가 삭제되었습니다.', 'success')
    return redirect(url_for('admin.locations'))


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

@admin_bp.route('/versions')
def versions():
    return render_template('admin/versions.html', versions=version_repo.get_all())


@admin_bp.route('/versions/new', methods=['GET', 'POST'])
def version_new():
    if request.method == 'POST':
        version_repo.create(
            name=request.form['name'],
            description=request.form.get('description', ''),
        )
        flash('버전이 추가되었습니다.', 'success')
        return redirect(url_for('admin.versions'))
    return render_template('admin/version_form.html', version=None)


@admin_bp.route('/versions/<version_id>/edit', methods=['GET', 'POST'])
def version_edit(version_id):
    v = version_repo.get_by_id(version_id)
    if not v:
        flash('버전을 찾을 수 없습니다.', 'danger')
        return redirect(url_for('admin.versions'))
    if request.method == 'POST':
        version_repo.update(
            version_id,
            name=request.form['name'],
            description=request.form.get('description', ''),
            is_active='is_active' in request.form,
        )
        flash('버전 정보가 수정되었습니다.', 'success')
        return redirect(url_for('admin.versions'))
    return render_template('admin/version_form.html', version=v)


@admin_bp.route('/versions/<version_id>/delete', methods=['POST'])
def version_delete(version_id):
    version_repo.delete(version_id)
    flash('버전이 삭제되었습니다.', 'success')
    return redirect(url_for('admin.versions'))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@admin_bp.route('/api/settings')
def api_get_settings():
    return jsonify(settings_repo.get())


@admin_bp.route('/api/settings', methods=['PUT'])
def api_update_settings():
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    updated = settings_repo.update(data)
    return jsonify(updated)


@admin_bp.route('/api/users')
def api_get_users():
    return jsonify(user_repo.get_all())


@admin_bp.route('/api/users', methods=['POST'])
def api_create_user():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': '이름을 입력해주세요.'}), 400
    user = user_repo.create(
        name=data['name'],
        role=data.get('role', ''),
        color=data.get('color', '#4A90D9'),
    )
    return jsonify(user), 201


@admin_bp.route('/api/users/<user_id>', methods=['PUT'])
def api_update_user(user_id):
    user = user_repo.get_by_id(user_id)
    if not user:
        return jsonify({'error': '팀원을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    updated = user_repo.update(
        user_id,
        name=data.get('name', user['name']),
        role=data.get('role', user['role']),
        color=data.get('color', user['color']),
    )
    return jsonify(updated)


@admin_bp.route('/api/users/<user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    user_repo.delete(user_id)
    return jsonify({'success': True})


@admin_bp.route('/api/locations')
def api_get_locations():
    return jsonify(location_repo.get_all())


@admin_bp.route('/api/locations', methods=['POST'])
def api_create_location():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': '이름을 입력해주세요.'}), 400
    loc = location_repo.create(
        name=data['name'],
        color=data.get('color', '#28a745'),
        description=data.get('description', ''),
    )
    return jsonify(loc), 201


@admin_bp.route('/api/locations/<loc_id>', methods=['PUT'])
def api_update_location(loc_id):
    loc = location_repo.get_by_id(loc_id)
    if not loc:
        return jsonify({'error': '시험장소를 찾을 수 없습니다.'}), 404
    data = request.get_json()
    updated = location_repo.update(
        loc_id,
        name=data.get('name', loc['name']),
        color=data.get('color', loc['color']),
        description=data.get('description', loc.get('description', '')),
    )
    return jsonify(updated)


@admin_bp.route('/api/locations/<loc_id>', methods=['DELETE'])
def api_delete_location(loc_id):
    location_repo.delete(loc_id)
    return jsonify({'success': True})


@admin_bp.route('/api/versions')
def api_get_versions():
    return jsonify(version_repo.get_all())


@admin_bp.route('/api/versions', methods=['POST'])
def api_create_version():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': '버전명을 입력해주세요.'}), 400
    v = version_repo.create(
        name=data['name'],
        description=data.get('description', ''),
    )
    return jsonify(v), 201


@admin_bp.route('/api/versions/<version_id>', methods=['PUT'])
def api_update_version(version_id):
    v = version_repo.get_by_id(version_id)
    if not v:
        return jsonify({'error': '버전을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    updated = version_repo.update(
        version_id,
        name=data.get('name', v['name']),
        description=data.get('description', v.get('description', '')),
        is_active=data.get('is_active', v.get('is_active', True)),
    )
    return jsonify(updated)


@admin_bp.route('/api/versions/<version_id>', methods=['DELETE'])
def api_delete_version(version_id):
    version_repo.delete(version_id)
    return jsonify({'success': True})
```

- [ ] **Step 2: Commit**

```bash
git add app/blueprints/admin/routes.py
git commit -m "feat: update admin routes with locations and versions management"
```

---

### Task 9: Update Tasks Routes (New Fields + Procedure Lookup)

**Files:**
- Modify: `app/blueprints/tasks/routes.py`

- [ ] **Step 1: Rewrite tasks routes**

Replace `app/blueprints/tasks/routes.py`:

```python
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, abort

from app.repositories import task_repo, user_repo, location_repo, version_repo

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


# ---------------------------------------------------------------------------
# Template rendering routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/')
def task_list():
    tasks = task_repo.get_all()
    version = request.args.get('version')
    status = request.args.get('status')
    assignees = request.args.getlist('assignee')
    location = request.args.get('location')
    procedure = request.args.get('procedure', '').strip()

    if version:
        tasks = [t for t in tasks if t.get('version_id') == version]
    if status:
        tasks = [t for t in tasks if t['status'] == status]
    if assignees:
        tasks = [t for t in tasks if any(a in t.get('assignee_ids', []) for a in assignees)]
    if location:
        tasks = [t for t in tasks if t.get('location_id') == location]
    if procedure:
        tasks = [t for t in tasks if procedure.lower() in t.get('procedure_id', '').lower()]

    users = user_repo.get_all()
    locations = location_repo.get_all()
    versions = version_repo.get_all()
    user_map = {u['id']: u['name'] for u in users}
    location_map = {loc['id']: loc['name'] for loc in locations}

    return render_template('tasks/list.html',
                           tasks=tasks, users=users,
                           locations=locations, versions=versions,
                           user_map=user_map, location_map=location_map,
                           filters={
                               'version': version or '',
                               'status': status or '',
                               'assignees': assignees,
                               'location': location or '',
                               'procedure': procedure,
                           })


@tasks_bp.route('/new', methods=['GET', 'POST'])
def task_new():
    if request.method == 'POST':
        procedure_id = request.form.get('procedure_id', '').strip()
        if not procedure_id:
            flash('절차서 식별자를 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_new'))
        assignee_ids = request.form.getlist('assignee_ids')
        test_list_raw = request.form.get('test_list', '')
        test_list = [t.strip() for t in test_list_raw.split(',') if t.strip()]
        task_repo.create(
            procedure_id=procedure_id,
            version_id=request.form.get('version_id', ''),
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_hours=float(request.form.get('estimated_hours', 0) or 0),
            deadline=request.form.get('deadline', ''),
            memo=request.form.get('memo', '').strip(),
        )
        flash('시험 항목이 생성되었습니다.', 'success')
        return redirect(url_for('tasks.task_list'))
    users = user_repo.get_all()
    locations = location_repo.get_all()
    versions = version_repo.get_all()
    return render_template('tasks/form.html', task=None,
                           users=users, locations=locations, versions=versions)


@tasks_bp.route('/<task_id>')
def task_detail(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    users = user_repo.get_all()
    user_map = {u['id']: u['name'] for u in users}
    assignee_names = [user_map.get(uid, uid) for uid in task.get('assignee_ids', [])]
    location = location_repo.get_by_id(task.get('location_id')) if task.get('location_id') else None
    version = version_repo.get_by_id(task.get('version_id')) if task.get('version_id') else None
    return render_template('tasks/detail.html', task=task,
                           assignee_names=assignee_names,
                           location=location, version=version)


@tasks_bp.route('/<task_id>/edit', methods=['GET', 'POST'])
def task_edit(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    if request.method == 'POST':
        procedure_id = request.form.get('procedure_id', '').strip()
        if not procedure_id:
            flash('절차서 식별자를 입력해주세요.', 'danger')
            return redirect(url_for('tasks.task_edit', task_id=task_id))
        assignee_ids = request.form.getlist('assignee_ids')
        test_list_raw = request.form.get('test_list', '')
        test_list = [t.strip() for t in test_list_raw.split(',') if t.strip()]
        task_repo.update(
            task_id=task_id,
            procedure_id=procedure_id,
            version_id=request.form.get('version_id', ''),
            assignee_ids=assignee_ids,
            location_id=request.form.get('location_id', ''),
            section_name=request.form.get('section_name', '').strip(),
            procedure_owner=request.form.get('procedure_owner', '').strip(),
            test_list=test_list,
            estimated_hours=float(request.form.get('estimated_hours', 0) or 0),
            remaining_hours=float(request.form.get('remaining_hours', 0) or 0),
            deadline=request.form.get('deadline', ''),
            status=request.form.get('status', 'waiting'),
            memo=request.form.get('memo', '').strip(),
        )
        flash('시험 항목이 수정되었습니다.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    users = user_repo.get_all()
    locations = location_repo.get_all()
    versions = version_repo.get_all()
    return render_template('tasks/form.html', task=task,
                           users=users, locations=locations, versions=versions)


@tasks_bp.route('/<task_id>/delete', methods=['POST'])
def task_delete(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        abort(404)
    task_repo.delete(task_id)
    flash('시험 항목이 삭제되었습니다.', 'success')
    return redirect(url_for('tasks.task_list'))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@tasks_bp.route('/api/list')
def api_task_list():
    tasks = task_repo.get_all()
    version = request.args.get('version')
    if version:
        tasks = [t for t in tasks if t.get('version_id') == version]
    return jsonify({'tasks': tasks})


@tasks_bp.route('/api/<task_id>')
def api_task_detail(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    return jsonify({'task': task})


@tasks_bp.route('/api/create', methods=['POST'])
def api_task_create():
    data = request.get_json()
    if not data or not data.get('procedure_id', '').strip():
        return jsonify({'error': '절차서 식별자를 입력해주세요.'}), 400
    task = task_repo.create(
        procedure_id=data['procedure_id'].strip(),
        version_id=data.get('version_id', ''),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=data.get('test_list', []),
        estimated_hours=float(data.get('estimated_hours', 0) or 0),
        deadline=data.get('deadline', ''),
        memo=data.get('memo', ''),
    )
    return jsonify(task), 201


@tasks_bp.route('/api/<task_id>/update', methods=['PUT'])
def api_task_update(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if not data or not data.get('procedure_id', '').strip():
        return jsonify({'error': '절차서 식별자를 입력해주세요.'}), 400
    updated = task_repo.update(
        task_id=task_id,
        procedure_id=data['procedure_id'].strip(),
        version_id=data.get('version_id', ''),
        assignee_ids=data.get('assignee_ids', []),
        location_id=data.get('location_id', ''),
        section_name=data.get('section_name', ''),
        procedure_owner=data.get('procedure_owner', ''),
        test_list=data.get('test_list', []),
        estimated_hours=float(data.get('estimated_hours', 0) or 0),
        remaining_hours=float(data.get('remaining_hours', 0) or 0),
        deadline=data.get('deadline', ''),
        status=data.get('status', 'waiting'),
        memo=data.get('memo', ''),
    )
    return jsonify(updated)


@tasks_bp.route('/api/<task_id>/delete', methods=['DELETE'])
def api_task_delete(task_id):
    task = task_repo.get_by_id(task_id)
    if not task:
        return jsonify({'error': '시험 항목을 찾을 수 없습니다.'}), 404
    task_repo.delete(task_id)
    return jsonify({'success': True})


@tasks_bp.route('/api/procedure/<procedure_id>')
def api_procedure_lookup(procedure_id):
    from app.services.procedure_service import lookup
    result = lookup(procedure_id)
    if not result:
        return jsonify({'error': '절차서를 찾을 수 없습니다.'}), 404
    return jsonify(result)
```

- [ ] **Step 2: Commit**

```bash
git add app/blueprints/tasks/routes.py
git commit -m "feat: update tasks routes with new fields and procedure lookup"
```

---

### Task 10: Update Schedule Routes (Version Filter + New Fields)

**Files:**
- Modify: `app/blueprints/schedule/routes.py`

- [ ] **Step 1: Rewrite schedule routes**

This is the largest file. Key changes:
- Replace `category_repo` with `location_repo`, add `version_repo`
- `_build_maps()` returns location_map instead of category_map
- `_enrich_blocks()` uses `assignee_ids` (array), `location_id`
- `_get_queue_tasks()` works with new task fields
- `_check_overlap()` checks both assignee and location conflicts
- All views accept `version` query param
- Draft generate passes `version_id`

Replace `app/blueprints/schedule/routes.py`:

```python
import calendar
from datetime import date, datetime, timedelta

from flask import Blueprint, request, jsonify, render_template, Response

from app.repositories import (
    location_repo,
    schedule_repo,
    settings_repo,
    task_repo,
    user_repo,
    version_repo,
)
from app.utils.time_utils import (
    adjust_end_for_breaks,
    generate_time_slots,
    is_break_slot,
    minutes_to_time,
    time_to_minutes,
    work_minutes_in_range,
)

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')

DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str):
    if date_str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    return date.today()


def _get_current_version_id():
    """Get version_id from query param, or first active version."""
    vid = request.args.get('version')
    if vid:
        return vid
    active = version_repo.get_active()
    return active[0]['id'] if active else None


def _build_maps():
    users = user_repo.get_all()
    tasks = task_repo.get_all()
    locations = location_repo.get_all()
    return (
        {u['id']: u for u in users},
        {t['id']: t for t in tasks},
        {loc['id']: loc for loc in locations},
    )


def _enrich_blocks(blocks, users_map, tasks_map, locations_map, color_by):
    enriched = []
    for b in blocks:
        block = dict(b)
        task = tasks_map.get(b.get('task_id'))
        location = locations_map.get(b.get('location_id'))

        # Assignee names from assignee_ids
        assignee_ids = b.get('assignee_ids', [])
        assignee_names = []
        assignee_colors = []
        for uid in assignee_ids:
            u = users_map.get(uid)
            if u:
                assignee_names.append(u['name'])
                assignee_colors.append(u['color'])

        block['procedure_id'] = task.get('procedure_id', '') if task else ''
        block['section_name'] = task.get('section_name', '') if task else ''
        block['task_title'] = task.get('procedure_id', '(삭제됨)') if task else '(삭제됨)'
        block['assignee_names'] = assignee_names
        block['assignee_name'] = ', '.join(assignee_names) if assignee_names else '(미배정)'
        block['assignee_color'] = assignee_colors[0] if assignee_colors else '#6c757d'
        block['location_name'] = location['name'] if location else ''
        block['location_color'] = location['color'] if location else '#6c757d'
        block['color'] = block['location_color'] if color_by == 'location' else block['assignee_color']
        block['block_status'] = b.get('block_status', 'pending')
        block['memo'] = b.get('memo', '')

        enriched.append(block)
    return enriched


def _get_queue_tasks(users_map, locations_map, version_id):
    tasks = task_repo.get_all()
    if version_id:
        tasks = [t for t in tasks if t.get('version_id') == version_id]
    all_blocks = schedule_repo.get_all()

    scheduled_hours = {}
    for b in all_blocks:
        tid = b['task_id']
        duration = time_to_minutes(b['end_time']) - time_to_minutes(b['start_time'])
        scheduled_hours[tid] = scheduled_hours.get(tid, 0) + duration / 60.0

    queue = []
    for t in tasks:
        if t['status'] == 'completed':
            continue
        est = t.get('estimated_hours', 0)
        if est <= 0:
            continue
        remaining = est - scheduled_hours.get(t['id'], 0)
        if remaining <= 0:
            continue

        task = dict(t)
        task['remaining_unscheduled_hours'] = round(remaining, 2)

        assignee_ids = t.get('assignee_ids', [])
        assignee_names = [users_map[uid]['name'] for uid in assignee_ids if uid in users_map]
        assignee_colors = [users_map[uid]['color'] for uid in assignee_ids if uid in users_map]

        task['assignee_name'] = ', '.join(assignee_names) if assignee_names else '(미배정)'
        task['assignee_color'] = assignee_colors[0] if assignee_colors else '#6c757d'

        location = locations_map.get(t.get('location_id'))
        task['location_name'] = location['name'] if location else ''
        task['location_color'] = location['color'] if location else '#6c757d'

        queue.append(task)

    queue.sort(key=lambda t: (
        t.get('deadline') or '9999-12-31',
        t.get('procedure_id', ''),
    ))
    return queue


def _check_overlap(assignee_ids, location_id, date_str, start_time, end_time, exclude_block_id=None):
    """Check overlap for any assignee or for location."""
    s1 = time_to_minutes(start_time)
    e1 = time_to_minutes(end_time)
    for b in schedule_repo.get_by_date(date_str):
        if exclude_block_id and b['id'] == exclude_block_id:
            continue
        s2 = time_to_minutes(b['start_time'])
        e2 = time_to_minutes(b['end_time'])
        if s1 < e2 and s2 < e1:
            # Check assignee overlap
            block_assignees = b.get('assignee_ids', [])
            if any(a in block_assignees for a in assignee_ids):
                return b
            # Check location overlap
            if location_id and b.get('location_id') == location_id:
                return b
    return None


def _compute_overlap_layout(blocks):
    if not blocks:
        return blocks
    sorted_blocks = sorted(
        blocks,
        key=lambda b: (time_to_minutes(b['start_time']),
                       -time_to_minutes(b['end_time'])),
    )
    columns = []
    block_col = {}
    for i, b in enumerate(sorted_blocks):
        s = time_to_minutes(b['start_time'])
        placed = False
        for ci, (col_end, indices) in enumerate(columns):
            if col_end <= s:
                columns[ci] = (time_to_minutes(b['end_time']), indices + [i])
                block_col[i] = ci
                placed = True
                break
        if not placed:
            block_col[i] = len(columns)
            columns.append((time_to_minutes(b['end_time']), [i]))
    for i, b in enumerate(sorted_blocks):
        s = time_to_minutes(b['start_time'])
        e = time_to_minutes(b['end_time'])
        max_col = block_col[i] + 1
        for j, b2 in enumerate(sorted_blocks):
            if i == j:
                continue
            s2 = time_to_minutes(b2['start_time'])
            e2 = time_to_minutes(b2['end_time'])
            if s < e2 and s2 < e:
                max_col = max(max_col, block_col[j] + 1)
        b['col_index'] = block_col[i]
        b['col_total'] = max_col
    return sorted_blocks


def _get_break_slots(settings):
    slots = generate_time_slots(settings)
    return {s for s in slots if is_break_slot(s, settings)}


def _build_month_nav(year, month):
    if month == 1:
        prev_date = date(year - 1, 12, 1)
    else:
        prev_date = date(year, month - 1, 1)
    if month == 12:
        next_date = date(year + 1, 1, 1)
    else:
        next_date = date(year, month + 1, 1)
    return prev_date, next_date


def _group_blocks_by_date(enriched):
    result = {}
    for b in enriched:
        result.setdefault(b['date'], []).append(b)
    return result


def _build_month_weeks(year, month, blocks_by_date):
    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append(None)
            else:
                d = date(year, month, day_num)
                week_data.append({
                    'date': d,
                    'day': day_num,
                    'blocks': blocks_by_date.get(d.isoformat(), []),
                })
        weeks.append(week_data)
    return weeks


def _version_url_param():
    """Return version query string for navigation links."""
    vid = request.args.get('version')
    return vid or ''


# ---------------------------------------------------------------------------
# Template rendering routes
# ---------------------------------------------------------------------------

@schedule_bp.route('/')
def day_view():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = _build_maps()

    blocks = schedule_repo.get_by_date(current_date.isoformat())
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        settings.get('block_color_by', 'assignee'),
    )
    enriched = _compute_overlap_layout(enriched)

    return render_template(
        'schedule/day.html',
        current_date=current_date,
        prev_date=current_date - timedelta(days=1),
        next_date=current_date + timedelta(days=1),
        blocks=enriched,
        time_slots=generate_time_slots(settings),
        break_slots=_get_break_slots(settings),
        settings=settings,
        queue_tasks=_get_queue_tasks(users_map, locations_map, version_id),
        versions=version_repo.get_all(),
        current_version_id=version_id or '',
    )


@schedule_bp.route('/week')
def week_view():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = _build_maps()

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_repo.get_by_date_range(
        week_start.isoformat(), week_end.isoformat(),
    )
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        settings.get('block_color_by', 'assignee'),
    )

    blocks_by_date = _group_blocks_by_date(enriched)
    for day_key in blocks_by_date:
        blocks_by_date[day_key] = _compute_overlap_layout(blocks_by_date[day_key])

    return render_template(
        'schedule/week.html',
        current_date=current_date,
        week_start=week_start,
        week_end=week_end,
        week_days=[week_start + timedelta(days=i) for i in range(7)],
        day_names=DAY_NAMES,
        prev_date=current_date - timedelta(weeks=1),
        next_date=current_date + timedelta(weeks=1),
        blocks_by_date=blocks_by_date,
        time_slots=generate_time_slots(settings),
        break_slots=_get_break_slots(settings),
        settings=settings,
        today=date.today(),
        queue_tasks=_get_queue_tasks(users_map, locations_map, version_id),
        versions=version_repo.get_all(),
        current_version_id=version_id or '',
    )


@schedule_bp.route('/month')
def month_view():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = _build_maps()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_repo.get_by_date_range(
        first_day.isoformat(), last_day.isoformat(),
    )
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        settings.get('block_color_by', 'assignee'),
    )

    blocks_by_date = _group_blocks_by_date(enriched)
    prev_date, next_date = _build_month_nav(year, month)

    return render_template(
        'schedule/month.html',
        current_date=current_date,
        year=year,
        month=month,
        weeks=_build_month_weeks(year, month, blocks_by_date),
        day_names=DAY_NAMES,
        prev_date=prev_date,
        next_date=next_date,
        today=date.today(),
        settings=settings,
        queue_tasks=_get_queue_tasks(users_map, locations_map, version_id),
        versions=version_repo.get_all(),
        current_version_id=version_id or '',
    )


# ---------------------------------------------------------------------------
# View data API endpoints
# ---------------------------------------------------------------------------

@schedule_bp.route('/api/day')
def api_day_data():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = _build_maps()

    blocks = schedule_repo.get_by_date(current_date.isoformat())
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        settings.get('block_color_by', 'assignee'),
    )

    time_slots = generate_time_slots(settings)
    return jsonify({
        'current_date': current_date.isoformat(),
        'prev_date': (current_date - timedelta(days=1)).isoformat(),
        'next_date': (current_date + timedelta(days=1)).isoformat(),
        'blocks': enriched,
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, settings)],
        'settings': settings,
        'queue_tasks': _get_queue_tasks(users_map, locations_map, version_id),
    })


@schedule_bp.route('/api/week')
def api_week_data():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = _build_maps()

    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)

    blocks = schedule_repo.get_by_date_range(week_start.isoformat(), week_end.isoformat())
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        settings.get('block_color_by', 'assignee'),
    )

    time_slots = generate_time_slots(settings)
    return jsonify({
        'current_date': current_date.isoformat(),
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'week_days': [(week_start + timedelta(days=i)).isoformat() for i in range(7)],
        'day_names': DAY_NAMES,
        'prev_date': (current_date - timedelta(weeks=1)).isoformat(),
        'next_date': (current_date + timedelta(weeks=1)).isoformat(),
        'blocks_by_date': _group_blocks_by_date(enriched),
        'time_slots': time_slots,
        'break_slots': [s for s in time_slots if is_break_slot(s, settings)],
        'settings': settings,
        'today': date.today().isoformat(),
        'queue_tasks': _get_queue_tasks(users_map, locations_map, version_id),
    })


@schedule_bp.route('/api/month')
def api_month_data():
    current_date = _parse_date(request.args.get('date'))
    settings = settings_repo.get()
    version_id = _get_current_version_id()
    users_map, tasks_map, locations_map = _build_maps()

    year, month = current_date.year, current_date.month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    blocks = schedule_repo.get_by_date_range(first_day.isoformat(), last_day.isoformat())
    if version_id:
        blocks = [b for b in blocks if b.get('version_id') == version_id]
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        settings.get('block_color_by', 'assignee'),
    )

    blocks_by_date = _group_blocks_by_date(enriched)
    prev_date, next_date = _build_month_nav(year, month)

    weeks = []
    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdayscalendar(year, month):
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append(None)
            else:
                d = date(year, month, day_num)
                week_data.append({
                    'date': d.isoformat(),
                    'day': day_num,
                    'blocks': blocks_by_date.get(d.isoformat(), []),
                })
        weeks.append(week_data)

    return jsonify({
        'current_date': current_date.isoformat(),
        'year': year,
        'month': month,
        'weeks': weeks,
        'day_names': DAY_NAMES,
        'prev_date': prev_date.isoformat(),
        'next_date': next_date.isoformat(),
        'today': date.today().isoformat(),
        'settings': settings,
        'queue_tasks': _get_queue_tasks(users_map, locations_map, version_id),
    })


# ---------------------------------------------------------------------------
# Block CRUD API
# ---------------------------------------------------------------------------

@schedule_bp.route('/api/blocks', methods=['POST'])
def api_create_block():
    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    for field in ('task_id', 'date', 'start_time', 'end_time'):
        if not data.get(field):
            return jsonify({'error': f'{field}은(는) 필수 항목입니다.'}), 400

    task = task_repo.get_by_id(data['task_id'])
    assignee_ids = data.get('assignee_ids', [])
    location_id = data.get('location_id', '')
    version_id = data.get('version_id', '')

    if not assignee_ids and task:
        assignee_ids = task.get('assignee_ids', [])
    if not location_id and task:
        location_id = task.get('location_id', '')
    if not version_id and task:
        version_id = task.get('version_id', '')

    settings = settings_repo.get()
    adjusted_end = adjust_end_for_breaks(data['start_time'], data['end_time'], settings)

    overlap = _check_overlap(assignee_ids, location_id, data['date'], data['start_time'], adjusted_end)
    if overlap:
        return jsonify({'error': '해당 시간에 이미 다른 시험이 배치되어 있습니다.'}), 409

    block = schedule_repo.create(
        task_id=data['task_id'],
        assignee_ids=assignee_ids,
        location_id=location_id,
        version_id=version_id,
        date=data['date'],
        start_time=data['start_time'],
        end_time=adjusted_end,
        is_draft=data.get('is_draft', False),
        is_locked=data.get('is_locked', False),
        origin=data.get('origin', 'manual'),
    )
    _sync_task_remaining_hours(data['task_id'])
    return jsonify(block), 201


@schedule_bp.route('/api/blocks/<block_id>', methods=['PUT'])
def api_update_block(block_id):
    block = schedule_repo.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400

    allowed = {'date', 'start_time', 'end_time', 'is_draft', 'is_locked', 'block_status', 'location_id'}
    updates = {k: v for k, v in data.items() if k in allowed}
    is_resize = data.get('resize', False)

    if 'start_time' in updates and 'end_time' in updates and not is_resize:
        settings = settings_repo.get()
        work_mins = work_minutes_in_range(block['start_time'], block['end_time'], settings)
        raw_end = minutes_to_time(time_to_minutes(updates['start_time']) + work_mins)
        updates['end_time'] = adjust_end_for_breaks(updates['start_time'], raw_end, settings)

    check_date = updates.get('date', block['date'])
    check_start = updates.get('start_time', block['start_time'])
    check_end = updates.get('end_time', block['end_time'])
    assignee_ids = block.get('assignee_ids', [])
    location_id = updates.get('location_id', block.get('location_id', ''))

    overlap = _check_overlap(
        assignee_ids, location_id, check_date, check_start, check_end,
        exclude_block_id=block_id,
    )
    if overlap:
        return jsonify({'error': '해당 시간에 이미 다른 시험이 배치되어 있습니다.'}), 409

    updated = schedule_repo.update(block_id, **updates)

    if is_resize and block.get('task_id'):
        _sync_task_remaining_hours(block['task_id'])

    return jsonify(updated)


@schedule_bp.route('/api/blocks/<block_id>', methods=['DELETE'])
def api_delete_block(block_id):
    block = schedule_repo.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    task_id = block.get('task_id')
    schedule_repo.delete(block_id)
    if task_id:
        _sync_task_remaining_hours(task_id)
    return jsonify({'success': True})


@schedule_bp.route('/api/blocks/<block_id>/lock', methods=['PUT'])
def api_toggle_lock(block_id):
    block = schedule_repo.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    updated = schedule_repo.update(block_id, is_locked=not block.get('is_locked', False))
    return jsonify(updated)


VALID_BLOCK_STATUSES = {'pending', 'in_progress', 'completed', 'cancelled'}


@schedule_bp.route('/api/blocks/<block_id>/status', methods=['PUT'])
def api_update_block_status(block_id):
    block = schedule_repo.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if not data or 'block_status' not in data:
        return jsonify({'error': '상태 값이 필요합니다.'}), 400
    status = data['block_status']
    if status not in VALID_BLOCK_STATUSES:
        return jsonify({'error': '유효하지 않은 상태입니다.'}), 400
    updated = schedule_repo.update(block_id, block_status=status)
    return jsonify(updated)


@schedule_bp.route('/api/blocks/<block_id>/memo', methods=['PUT'])
def api_update_block_memo(block_id):
    block = schedule_repo.get_by_id(block_id)
    if not block:
        return jsonify({'error': '블록을 찾을 수 없습니다.'}), 404
    data = request.get_json()
    if data is None:
        return jsonify({'error': '요청 데이터가 없습니다.'}), 400
    memo = data.get('memo', '')
    updated = schedule_repo.update(block_id, memo=memo)
    return jsonify(updated)


def _sync_task_remaining_hours(task_id):
    total_min = sum(
        time_to_minutes(b['end_time']) - time_to_minutes(b['start_time'])
        for b in schedule_repo.get_all()
        if b['task_id'] == task_id
    )
    scheduled_hours = round(total_min / 60.0, 2)
    task = task_repo.get_by_id(task_id)
    if task:
        est = task.get('estimated_hours', 0)
        new_remaining = round(max(est - scheduled_hours, 0), 2)
        if task.get('remaining_hours', 0) != new_remaining:
            task_repo.patch(task_id, remaining_hours=new_remaining)


# ---------------------------------------------------------------------------
# Export API
# ---------------------------------------------------------------------------

@schedule_bp.route('/api/export')
def api_export():
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    fmt = request.args.get('format', 'csv')

    if not start_date or not end_date:
        return jsonify({'error': 'start_date와 end_date는 필수입니다.'}), 400

    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': '날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)'}), 400

    users_map, tasks_map, locations_map = _build_maps()
    settings = settings_repo.get()
    blocks = schedule_repo.get_by_date_range(start_date, end_date)
    enriched = _enrich_blocks(
        blocks, users_map, tasks_map, locations_map,
        settings.get('block_color_by', 'assignee'),
    )
    enriched.sort(key=lambda b: (b.get('date', ''), b.get('start_time', '')))

    from app.services.export import export_xlsx, export_csv

    if fmt == 'xlsx':
        try:
            data = export_xlsx(enriched, start_date, end_date)
            return Response(
                data,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': f'attachment; filename="schedule_{start_date}_{end_date}.xlsx"'},
            )
        except ImportError:
            fmt = 'csv'

    return Response(
        export_csv(enriched),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="schedule_{start_date}_{end_date}.csv"'},
    )


# ---------------------------------------------------------------------------
# Draft scheduling API
# ---------------------------------------------------------------------------

@schedule_bp.route('/api/draft/generate', methods=['POST'])
def api_draft_generate():
    from app.services.scheduler import generate_draft_schedule
    version_id = _get_current_version_id()
    if not version_id:
        return jsonify({'error': '버전을 선택해주세요.'}), 400
    result = generate_draft_schedule(version_id=version_id)
    return jsonify({
        'placed_count': len(result['placed']),
        'unplaced': [
            {
                'task_id': u['task']['id'],
                'procedure_id': u['task'].get('procedure_id', ''),
                'remaining_hours': u['remaining_unscheduled_hours'],
                'reason': u.get('reason', ''),
            }
            for u in result['unplaced']
        ],
    })


@schedule_bp.route('/api/draft/approve', methods=['POST'])
def api_draft_approve():
    from app.services.scheduler import approve_drafts
    approve_drafts()
    return jsonify({'success': True})


@schedule_bp.route('/api/draft/discard', methods=['POST'])
def api_draft_discard():
    from app.services.scheduler import discard_drafts
    discard_drafts()
    return jsonify({'success': True})
```

- [ ] **Step 2: Commit**

```bash
git add app/blueprints/schedule/routes.py
git commit -m "feat: update schedule routes with version filter, location, multi-assignee"
```

---

### Task 11: Update Templates — Base + Admin

**Files:**
- Modify: `app/templates/base.html`
- Create: `app/templates/admin/locations.html`
- Create: `app/templates/admin/location_form.html`
- Create: `app/templates/admin/versions.html`
- Create: `app/templates/admin/version_form.html`
- Modify: `app/templates/admin/settings.html`

- [ ] **Step 1: Update base.html**

Update the navbar in `app/templates/base.html`:
- Change brand to "시험 스케줄러"
- Replace "업무" with "시험 항목"
- Replace "카테고리 관리" with "시험장소 관리" and add "버전 관리"
- Add version selector dropdown in the navbar right area

Replace the `<nav>` section:

```html
<nav class="navbar navbar-expand-lg navbar-dark bg-primary">
    <div class="container-fluid">
      <a class="navbar-brand" href="{{ url_for('schedule.day_view') }}">시험 스케줄러</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav">
          <li class="nav-item">
            <a class="nav-link" href="{{ url_for('schedule.day_view') }}">일간</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" href="{{ url_for('schedule.week_view') }}">주간</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" href="{{ url_for('schedule.month_view') }}">월간</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" href="{{ url_for('tasks.task_list') }}">시험 항목</a>
          </li>
          <li class="nav-item dropdown">
            <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">관리</a>
            <ul class="dropdown-menu">
              <li><a class="dropdown-item" href="{{ url_for('admin.users') }}">팀원 관리</a></li>
              <li><a class="dropdown-item" href="{{ url_for('admin.locations') }}">시험장소 관리</a></li>
              <li><a class="dropdown-item" href="{{ url_for('admin.versions') }}">버전 관리</a></li>
              <li><a class="dropdown-item" href="{{ url_for('admin.settings') }}">설정</a></li>
            </ul>
          </li>
        </ul>
```

- [ ] **Step 2: Create admin location templates**

Create `app/templates/admin/locations.html`:

```html
{% extends "base.html" %}
{% block title %}시험장소 관리 - 스케줄링{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>시험장소 관리</h4>
  <a href="{{ url_for('admin.location_new') }}" class="btn btn-primary btn-sm">
    <i class="bi bi-plus-lg"></i> 장소 추가
  </a>
</div>
<table class="table">
  <thead>
    <tr><th>이름</th><th>설명</th><th>색상</th><th></th></tr>
  </thead>
  <tbody>
    {% for loc in locations %}
    <tr>
      <td>{{ loc.name }}</td>
      <td>{{ loc.description or '-' }}</td>
      <td><span class="badge" style="background-color:{{ loc.color }}">{{ loc.color }}</span></td>
      <td>
        <a href="{{ url_for('admin.location_edit', loc_id=loc.id) }}" class="btn btn-sm btn-outline-primary">수정</a>
        <form method="POST" action="{{ url_for('admin.location_delete', loc_id=loc.id) }}" class="d-inline" onsubmit="return confirm('삭제하시겠습니까?')">
          <button class="btn btn-sm btn-outline-danger">삭제</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Create `app/templates/admin/location_form.html`:

```html
{% extends "base.html" %}
{% block title %}{{ '장소 수정' if location else '장소 추가' }} - 스케줄링{% endblock %}
{% block content %}
<h2>{{ '장소 수정' if location else '장소 추가' }}</h2>
<form method="POST" class="mt-3" style="max-width: 400px;">
  <div class="mb-3">
    <label class="form-label">이름</label>
    <input type="text" class="form-control" name="name" value="{{ location.name if location else '' }}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">설명</label>
    <input type="text" class="form-control" name="description" value="{{ location.description if location else '' }}">
  </div>
  <div class="mb-3">
    <label class="form-label">색상</label>
    <input type="color" class="form-control form-control-color" name="color" value="{{ location.color if location else '#28a745' }}">
  </div>
  <button type="submit" class="btn btn-primary">저장</button>
  <a href="{{ url_for('admin.locations') }}" class="btn btn-secondary">취소</a>
</form>
{% endblock %}
```

- [ ] **Step 3: Create admin version templates**

Create `app/templates/admin/versions.html`:

```html
{% extends "base.html" %}
{% block title %}버전 관리 - 스케줄링{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>버전 관리</h4>
  <a href="{{ url_for('admin.version_new') }}" class="btn btn-primary btn-sm">
    <i class="bi bi-plus-lg"></i> 버전 추가
  </a>
</div>
<table class="table">
  <thead>
    <tr><th>버전명</th><th>설명</th><th>상태</th><th></th></tr>
  </thead>
  <tbody>
    {% for v in versions %}
    <tr>
      <td>{{ v.name }}</td>
      <td>{{ v.description or '-' }}</td>
      <td>
        {% if v.is_active %}
        <span class="badge bg-success">활성</span>
        {% else %}
        <span class="badge bg-secondary">비활성</span>
        {% endif %}
      </td>
      <td>
        <a href="{{ url_for('admin.version_edit', version_id=v.id) }}" class="btn btn-sm btn-outline-primary">수정</a>
        <form method="POST" action="{{ url_for('admin.version_delete', version_id=v.id) }}" class="d-inline" onsubmit="return confirm('삭제하시겠습니까?')">
          <button class="btn btn-sm btn-outline-danger">삭제</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Create `app/templates/admin/version_form.html`:

```html
{% extends "base.html" %}
{% block title %}{{ '버전 수정' if version else '버전 추가' }} - 스케줄링{% endblock %}
{% block content %}
<h2>{{ '버전 수정' if version else '버전 추가' }}</h2>
<form method="POST" class="mt-3" style="max-width: 400px;">
  <div class="mb-3">
    <label class="form-label">버전명</label>
    <input type="text" class="form-control" name="name" value="{{ version.name if version else '' }}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">설명</label>
    <textarea class="form-control" name="description" rows="2">{{ version.description if version else '' }}</textarea>
  </div>
  {% if version %}
  <div class="mb-3 form-check">
    <input type="checkbox" class="form-check-input" name="is_active" id="is_active" {{ 'checked' if version.is_active }}>
    <label class="form-check-label" for="is_active">활성 버전</label>
  </div>
  {% endif %}
  <button type="submit" class="btn btn-primary">저장</button>
  <a href="{{ url_for('admin.versions') }}" class="btn btn-secondary">취소</a>
</form>
{% endblock %}
```

- [ ] **Step 4: Update settings.html to include actual_work_start/end**

Add two fields after work_start/work_end in `app/templates/admin/settings.html`:

```html
<div class="mb-3">
  <label class="form-label">실제 업무 시작</label>
  <input type="time" class="form-control" name="actual_work_start" value="{{ settings.actual_work_start|default('08:30') }}">
</div>
<div class="mb-3">
  <label class="form-label">실제 업무 종료</label>
  <input type="time" class="form-control" name="actual_work_end" value="{{ settings.actual_work_end|default('16:30') }}">
</div>
```

- [ ] **Step 5: Commit**

```bash
git add app/templates/base.html app/templates/admin/locations.html app/templates/admin/location_form.html app/templates/admin/versions.html app/templates/admin/version_form.html app/templates/admin/settings.html
git commit -m "feat: update templates for locations, versions, and new settings"
```

---

### Task 12: Update Templates — Tasks (Form + List + Detail)

**Files:**
- Modify: `app/templates/tasks/form.html`
- Modify: `app/templates/tasks/list.html`
- Modify: `app/templates/tasks/detail.html`

- [ ] **Step 1: Rewrite tasks/form.html**

Replace `app/templates/tasks/form.html` with new fields:

```html
{% extends "base.html" %}
{% block title %}{{ '시험 항목 수정' if task else '시험 항목 추가' }} - 스케줄링{% endblock %}

{% block content %}
<h2>{{ '시험 항목 수정' if task else '시험 항목 추가' }}</h2>
<form method="POST" class="mt-3" style="max-width: 600px;">
  <div class="mb-3">
    <label class="form-label">절차서 식별자</label>
    <input type="text" class="form-control" name="procedure_id" id="procedure_id"
           value="{{ task.procedure_id if task else '' }}"
           placeholder="예: ABC-001" pattern="[A-Za-z]{3}-\d+"
           required>
    <div class="form-text">영문 3자리-숫자 형식 (예: SYS-001, NAV-042)</div>
  </div>
  <div id="procedure-info" style="display:none" class="alert alert-info mb-3">
    <div><strong>장절명:</strong> <span id="pi-section"></span></div>
    <div><strong>절차서 담당자:</strong> <span id="pi-owner"></span></div>
    <div><strong>시험목록:</strong> <span id="pi-tests"></span></div>
  </div>
  <div class="mb-3">
    <label class="form-label">소프트웨어 버전</label>
    <select name="version_id" class="form-select" required>
      <option value="">선택</option>
      {% for v in versions %}
      <option value="{{ v.id }}" {{ 'selected' if task and task.version_id == v.id }}>{{ v.name }}{% if not v.is_active %} (비활성){% endif %}</option>
      {% endfor %}
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">시험 담당자 (복수 선택 가능)</label>
    <select name="assignee_ids" class="form-select" id="assignee-select" multiple size="4">
      {% for u in users %}
      <option value="{{ u.id }}" {{ 'selected' if task and u.id in task.assignee_ids }}>{{ u.name }}</option>
      {% endfor %}
    </select>
    <div id="assignee-chips" class="mt-1"></div>
  </div>
  <div class="mb-3">
    <label class="form-label">시험장소</label>
    <select name="location_id" class="form-select">
      <option value="">선택 안 함</option>
      {% for loc in locations %}
      <option value="{{ loc.id }}" {{ 'selected' if task and task.location_id == loc.id }}>{{ loc.name }}{% if loc.description %} ({{ loc.description }}){% endif %}</option>
      {% endfor %}
    </select>
  </div>
  <div class="mb-3">
    <label class="form-label">장절명</label>
    <input type="text" class="form-control" name="section_name" id="section_name"
           value="{{ task.section_name if task else '' }}">
  </div>
  <div class="mb-3">
    <label class="form-label">절차서 담당자</label>
    <input type="text" class="form-control" name="procedure_owner" id="procedure_owner"
           value="{{ task.procedure_owner if task else '' }}">
  </div>
  <div class="mb-3">
    <label class="form-label">시험목록</label>
    <input type="text" class="form-control" name="test_list" id="test_list"
           value="{{ task.test_list|join(', ') if task and task.test_list else '' }}"
           placeholder="TC-001, TC-002, TC-003">
    <div class="form-text">쉼표로 구분</div>
  </div>
  <div class="mb-3">
    <label class="form-label">예상 시간</label>
    <input type="number" class="form-control" name="estimated_hours" min="0" step="0.5"
           value="{{ task.estimated_hours if task else '' }}">
  </div>
  {% if task %}
  <div class="mb-3">
    <label class="form-label">잔여 시간</label>
    <input type="number" class="form-control" name="remaining_hours" min="0" step="0.5"
           value="{{ task.remaining_hours }}">
  </div>
  <div class="mb-3">
    <label class="form-label">상태</label>
    <select name="status" class="form-select">
      <option value="waiting" {{ 'selected' if task.status == 'waiting' }}>대기</option>
      <option value="in_progress" {{ 'selected' if task.status == 'in_progress' }}>진행 중</option>
      <option value="completed" {{ 'selected' if task.status == 'completed' }}>완료</option>
    </select>
  </div>
  {% endif %}
  <div class="mb-3">
    <label class="form-label">마감일</label>
    <input type="date" class="form-control" name="deadline"
           value="{{ task.deadline if task else '' }}">
  </div>
  <div class="mb-3">
    <label class="form-label">메모</label>
    <textarea class="form-control" name="memo" rows="3">{{ task.memo if task else '' }}</textarea>
  </div>
  <button type="submit" class="btn btn-primary">저장</button>
  {% if task %}
  <a href="{{ url_for('tasks.task_detail', task_id=task.id) }}" class="btn btn-secondary">취소</a>
  {% else %}
  <a href="{{ url_for('tasks.task_list') }}" class="btn btn-secondary">취소</a>
  {% endif %}
</form>
{% endblock %}

{% block scripts %}
<script>
// Procedure ID auto-lookup
document.getElementById('procedure_id').addEventListener('blur', function() {
  var pid = this.value.trim();
  if (!pid) return;
  fetch('/tasks/api/procedure/' + encodeURIComponent(pid))
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      if (!data) { document.getElementById('procedure-info').style.display = 'none'; return; }
      document.getElementById('pi-section').textContent = data.section_name || '';
      document.getElementById('pi-owner').textContent = data.procedure_owner || '';
      document.getElementById('pi-tests').textContent = (data.test_list || []).join(', ');
      document.getElementById('procedure-info').style.display = 'block';
      // Auto-fill if empty
      if (!document.getElementById('section_name').value) document.getElementById('section_name').value = data.section_name || '';
      if (!document.getElementById('procedure_owner').value) document.getElementById('procedure_owner').value = data.procedure_owner || '';
      if (!document.getElementById('test_list').value) document.getElementById('test_list').value = (data.test_list || []).join(', ');
    });
});

// Multi-select chip display
(function() {
  var sel = document.getElementById('assignee-select');
  var chips = document.getElementById('assignee-chips');
  function render() {
    chips.innerHTML = '';
    Array.from(sel.selectedOptions).forEach(function(opt) {
      var chip = document.createElement('span');
      chip.className = 'badge bg-primary me-1 mb-1';
      chip.style.cursor = 'pointer';
      chip.textContent = opt.text + ' ×';
      chip.addEventListener('click', function() { opt.selected = false; render(); });
      chips.appendChild(chip);
    });
  }
  sel.addEventListener('change', render);
  render();
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Rewrite tasks/list.html with chip filters**

Replace `app/templates/tasks/list.html`:

```html
{% extends "base.html" %}
{% block title %}시험 항목 목록 - 스케줄링{% endblock %}

{% block content %}
<div class="task-list-page">
  <div class="task-list-header">
    <h4 class="mb-0">시험 항목 목록</h4>
    <a href="{{ url_for('tasks.task_new') }}" class="btn btn-primary btn-sm">
      <i class="bi bi-plus-lg"></i> 새 항목
    </a>
  </div>

  {# Filters #}
  <form method="GET" id="filter-form" class="task-filter-bar flex-wrap gap-2">
    <select name="version" class="form-select form-select-sm" style="max-width:150px" onchange="this.form.submit()">
      <option value="">전체 버전</option>
      {% for v in versions %}
      <option value="{{ v.id }}" {{ 'selected' if filters.version == v.id }}>{{ v.name }}</option>
      {% endfor %}
    </select>
    <select name="status" class="form-select form-select-sm" style="max-width:120px" onchange="this.form.submit()">
      <option value="">전체 상태</option>
      <option value="waiting" {{ 'selected' if filters.status == 'waiting' }}>대기</option>
      <option value="in_progress" {{ 'selected' if filters.status == 'in_progress' }}>진행 중</option>
      <option value="completed" {{ 'selected' if filters.status == 'completed' }}>완료</option>
    </select>
    <select name="location" class="form-select form-select-sm" style="max-width:130px" onchange="this.form.submit()">
      <option value="">전체 장소</option>
      {% for loc in locations %}
      <option value="{{ loc.id }}" {{ 'selected' if filters.location == loc.id }}>{{ loc.name }}</option>
      {% endfor %}
    </select>
    <input type="text" name="procedure" class="form-control form-control-sm" style="max-width:150px"
           placeholder="절차서 검색" value="{{ filters.procedure }}"
           onchange="this.form.submit()">

    {# Multi-assignee filter with chips #}
    <div class="dropdown" id="assignee-filter-dropdown">
      <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
        담당자
      </button>
      <ul class="dropdown-menu p-2" style="min-width: 200px;">
        {% for u in users %}
        <li>
          <label class="dropdown-item py-1">
            <input type="checkbox" name="assignee" value="{{ u.id }}"
                   {{ 'checked' if u.id in filters.assignees }}
                   onchange="document.getElementById('filter-form').submit()">
            {{ u.name }}
          </label>
        </li>
        {% endfor %}
      </ul>
    </div>

    {# Active filter chips #}
    <div class="d-flex flex-wrap gap-1 align-items-center">
      {% for uid in filters.assignees %}
      <span class="badge bg-primary">
        {{ user_map.get(uid, uid) }}
        <a href="?{{ 'version=' ~ filters.version ~ '&' if filters.version }}{{ 'status=' ~ filters.status ~ '&' if filters.status }}{{ 'location=' ~ filters.location ~ '&' if filters.location }}{% for a in filters.assignees if a != uid %}assignee={{ a }}&{% endfor %}" class="text-white text-decoration-none ms-1">×</a>
      </span>
      {% endfor %}
    </div>

    {% if filters.status or filters.assignees or filters.location or filters.procedure or filters.version %}
    <a href="{{ url_for('tasks.task_list') }}" class="btn btn-sm btn-outline-secondary">
      <i class="bi bi-x-lg"></i> 초기화
    </a>
    {% endif %}
  </form>

  {# Table #}
  <div class="task-table-wrap">
    <table class="task-table">
      <thead>
        <tr>
          <th>절차서 ID</th>
          <th>장절명</th>
          <th>담당자</th>
          <th>장소</th>
          <th>시간</th>
          <th>마감일</th>
          <th>상태</th>
        </tr>
      </thead>
      <tbody>
        {% for task in tasks %}
        <tr class="task-row" onclick="location.href='{{ url_for('tasks.task_detail', task_id=task.id) }}'">
          <td class="text-nowrap fw-bold">{{ task.procedure_id }}</td>
          <td class="task-cell-title">{{ task.section_name or '-' }}</td>
          <td>
            {% for uid in task.assignee_ids %}
              {{ user_map.get(uid, uid) }}{% if not loop.last %}, {% endif %}
            {% endfor %}
            {% if not task.assignee_ids %}-{% endif %}
          </td>
          <td>{{ location_map.get(task.location_id, '-') }}</td>
          <td class="text-nowrap">{{ task.remaining_hours }}h / {{ task.estimated_hours }}h</td>
          <td class="text-nowrap">{{ task.deadline or '-' }}</td>
          <td>
            {% if task.status == 'waiting' %}
            <span class="task-status-chip status-waiting">대기</span>
            {% elif task.status == 'in_progress' %}
            <span class="task-status-chip status-progress">진행 중</span>
            {% else %}
            <span class="task-status-chip status-done">완료</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
        {% if not tasks %}
        <tr>
          <td colspan="7" class="task-empty-cell">등록된 시험 항목이 없습니다.</td>
        </tr>
        {% endif %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Rewrite tasks/detail.html**

Replace `app/templates/tasks/detail.html`:

```html
{% extends "base.html" %}
{% block title %}{{ task.procedure_id }} - 스케줄링{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2>{{ task.procedure_id }} — {{ task.section_name or '' }}</h2>
  <div>
    <a href="{{ url_for('tasks.task_edit', task_id=task.id) }}" class="btn btn-outline-primary">수정</a>
    <form method="POST" action="{{ url_for('tasks.task_delete', task_id=task.id) }}" class="d-inline"
          onsubmit="return confirm('정말 삭제하시겠습니까?')">
      <button type="submit" class="btn btn-outline-danger">삭제</button>
    </form>
  </div>
</div>

<div class="card" style="max-width: 700px;">
  <div class="card-body">
    <table class="table table-borderless mb-0">
      <tr><th style="width:140px">절차서 식별자</th><td>{{ task.procedure_id }}</td></tr>
      <tr><th>장절명</th><td>{{ task.section_name or '-' }}</td></tr>
      <tr><th>절차서 담당자</th><td>{{ task.procedure_owner or '-' }}</td></tr>
      <tr><th>시험목록</th><td>{{ task.test_list|join(', ') if task.test_list else '-' }}</td></tr>
      <tr><th>소프트웨어 버전</th><td>{{ version.name if version else '-' }}</td></tr>
      <tr><th>시험 담당자</th><td>{{ assignee_names|join(', ') if assignee_names else '-' }}</td></tr>
      <tr><th>시험장소</th><td>{{ location.name if location else '-' }}</td></tr>
      <tr>
        <th>상태</th>
        <td>
          {% if task.status == 'waiting' %}<span class="badge bg-secondary">대기</span>
          {% elif task.status == 'in_progress' %}<span class="badge bg-primary">진행 중</span>
          {% else %}<span class="badge bg-success">완료</span>{% endif %}
        </td>
      </tr>
      <tr><th>예상 시간</th><td>{{ task.estimated_hours }}시간</td></tr>
      <tr><th>잔여 시간</th><td>{{ task.remaining_hours }}시간</td></tr>
      <tr><th>마감일</th><td>{{ task.deadline or '-' }}</td></tr>
      <tr><th>메모</th><td>{{ task.memo or '-' }}</td></tr>
      <tr><th>생성일</th><td>{{ task.created_at or '-' }}</td></tr>
    </table>
  </div>
</div>

<a href="{{ url_for('tasks.task_list') }}" class="btn btn-secondary mt-3">목록으로</a>
{% endblock %}
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/tasks/form.html app/templates/tasks/list.html app/templates/tasks/detail.html
git commit -m "feat: update task templates with new fields and chip filters"
```

---

### Task 13: Update Schedule Templates (Day View + Task Queue)

**Files:**
- Modify: `app/templates/schedule/day.html`
- Modify: `app/templates/schedule/_task_queue.html`

- [ ] **Step 1: Update day.html block display**

In `app/templates/schedule/day.html`, update the block content section to show `procedure_id` + `section_name` instead of `task_title`, and show `assignee_name` (comma-joined) and `location_name` instead of `category_name`:

Replace the block title/meta/info section inside each block `<div>`:

```html
<div class="block-title">
  {{ block.procedure_id }}
  {% if block.section_name %}<span class="block-section">{{ block.section_name }}</span>{% endif %}
  <span class="block-status-badge badge-status-{{ block.block_status }}">
    {% if block.block_status == 'in_progress' %}진행
    {% elif block.block_status == 'completed' %}완료
    {% elif block.block_status == 'cancelled' %}불가
    {% endif %}
  </span>
</div>
<div class="block-meta">
  <span class="block-assignee">{{ block.assignee_name }}</span>
  {% if block.location_name %}
  <span class="block-category">{{ block.location_name }}</span>
  {% endif %}
</div>
<div class="block-info">
  <span class="block-time">{{ block.start_time }}–{{ block.end_time }}</span>
</div>
```

- [ ] **Step 2: Update _task_queue.html**

Replace `app/templates/schedule/_task_queue.html`:

```html
<div class="task-queue" id="task-queue">
  <div class="task-queue-header">
    <h6 class="mb-0">시험 큐</h6>
    <button class="btn btn-sm btn-link p-0" id="toggle-queue" title="접기/펼치기">
      <i class="bi bi-chevron-left"></i>
    </button>
  </div>
  <div class="queue-sort-bar">
    <button class="queue-sort-btn active" data-sort="deadline" title="마감일 순">
      <i class="bi bi-calendar-event"></i>
    </button>
    <button class="queue-sort-btn" data-sort="name" title="절차서ID 순">
      <i class="bi bi-sort-alpha-down"></i>
    </button>
    <button class="queue-sort-btn" data-sort="hours" title="남은시간 순">
      <i class="bi bi-clock"></i>
    </button>
  </div>
  <div class="task-queue-body" id="task-queue-body">
    {% if queue_tasks %}
    {% for task in queue_tasks %}
    {% set queue_color = task.location_color if settings.block_color_by == 'location' else task.assignee_color %}
    <div class="queue-task-item"
         data-task-id="{{ task.id }}"
         data-assignee-ids="{{ task.assignee_ids|join(',') }}"
         data-location-id="{{ task.location_id }}"
         data-version-id="{{ task.version_id }}"
         data-remaining-hours="{{ task.remaining_unscheduled_hours }}"
         data-title="{{ task.procedure_id }}"
         data-deadline="{{ task.deadline or '9999-12-31' }}"
         style="border-left: 4px solid {{ queue_color }};">
      <div class="queue-task-title">{{ task.procedure_id }}</div>
      <div class="queue-task-meta">
        {% if task.location_name %}
        <span class="queue-task-category" style="color: {{ task.location_color }};">{{ task.location_name }}</span>
        {% endif %}
        <span class="text-muted">{{ task.remaining_unscheduled_hours }}h</span>
      </div>
      <div class="queue-task-assignee">{{ task.assignee_name }}</div>
      {% if task.deadline %}
      <div class="queue-task-deadline text-muted">~{{ task.deadline }}</div>
      {% endif %}
    </div>
    {% endfor %}
    {% else %}
    <div class="text-muted small p-2 text-center">배치 가능한 시험이 없습니다.</div>
    {% endif %}
  </div>
</div>
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/schedule/day.html app/templates/schedule/_task_queue.html
git commit -m "feat: update schedule day view and task queue for new fields"
```

---

### Task 14: Update drag_drop.js for New Data Structure

**Files:**
- Modify: `app/static/js/drag_drop.js`

- [ ] **Step 1: Update JS to use new fields**

Key changes needed in `drag_drop.js`:
- Queue task items now use `data-assignee-ids` (comma-separated) instead of `data-assignee-id`
- Block creation POST needs `assignee_ids` array, `location_id`, `version_id`
- Change `data-priority` references to `data-title` (procedure_id)
- Queue sort by `name` sorts by procedure_id
- Remove priority-based sorting

Search and replace in `drag_drop.js`:
- `data.assignee_id = item.dataset.assigneeId` → `data.assignee_ids = item.dataset.assigneeIds ? item.dataset.assigneeIds.split(',') : []`
- Add `data.location_id = item.dataset.locationId || ''`
- Add `data.version_id = item.dataset.versionId || ''`
- In queue sorting, update `name` sort to use `data-title` which now holds procedure_id
- Remove priority sort option

This file is 667 lines so the exact changes depend on the current code. The implementer should search for `assigneeId`, `assignee_id`, `priority` and update accordingly.

- [ ] **Step 2: Commit**

```bash
git add app/static/js/drag_drop.js
git commit -m "feat: update drag_drop.js for new data structure"
```

---

### Task 15: Clean Up Old Category Files + Reset Data

**Files:**
- Delete: `app/repositories/category_repo.py`
- Delete: `data/categories.json`
- Delete: `app/templates/admin/categories.html`
- Delete: `app/templates/admin/category_form.html`
- Modify: `data/tasks.json` (reset to empty)
- Modify: `data/schedule_blocks.json` (reset to empty)

- [ ] **Step 1: Delete old category files**

```bash
git rm app/repositories/category_repo.py
git rm data/categories.json
git rm app/templates/admin/categories.html
git rm app/templates/admin/category_form.html
```

- [ ] **Step 2: Reset data files**

Write empty arrays to `data/tasks.json` and `data/schedule_blocks.json`.

- [ ] **Step 3: Commit**

```bash
git add data/tasks.json data/schedule_blocks.json
git commit -m "chore: remove old category files and reset data for new schema"
```

---

### Task 16: Update Tests

**Files:**
- Modify: `tests/test_app.py`

- [ ] **Step 1: Rewrite test fixtures and helpers**

Update the test fixture to create `locations.json` and `versions.json` instead of `categories.json`. Update helpers to use new field names.

The fixture should initialize:
```python
for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions'):
    ...
```

Update `_create_category` → `_create_location`, `_create_task` to use new parameters.

- [ ] **Step 2: Update all tests to use new field names**

Replace `category` references with `location`, `assignee_id` with `assignee_ids`, `title` with `procedure_id`, etc.

- [ ] **Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: update all tests for new data model"
```

---

### Task 17: Integration Smoke Test

- [ ] **Step 1: Start the server and verify manually**

```bash
cd /Users/yangseungmin/Projects/scheduling
source venv/bin/activate
python3 run.py
```

- [ ] **Step 2: Check key pages load without errors**

- `/` → should redirect to `/schedule/`
- `/schedule/` → day view loads
- `/tasks/` → task list loads
- `/admin/locations` → location management
- `/admin/versions` → version management
- `/admin/settings` → settings with new fields

- [ ] **Step 3: Create test data and verify flow**

1. Create a version (e.g., "v1.0.0")
2. Create a location (e.g., "A")
3. Create a test item with procedure_id, assignees, location
4. Verify it appears in the task list
5. Verify calendar shows the version selector
6. Test auto-scheduling

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes from smoke testing"
```
