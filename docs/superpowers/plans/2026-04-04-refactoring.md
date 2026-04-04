# Scheduling App Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코드 중복 제거, 파일 분리, 테스트 보강으로 가독성과 유지보수성을 개선한다.

**Architecture:** BaseRepository로 모델 CRUD 통합, calendar.py를 views/api/helpers로 분리, drag_drop.js를 10개 모듈로 분할. 테스트를 먼저 작성하여 리팩토링 안전망을 확보한다.

**Tech Stack:** Flask, Jinja2, Vanilla JS (IIFE + namespace), pytest

---

## File Structure

### New Files
- `schedule/models/base.py` — BaseRepository 클래스
- `schedule/routes/calendar_views.py` — day/week/month 뷰 렌더링
- `schedule/routes/calendar_api.py` — 블록 CRUD/shift/split API
- `schedule/routes/calendar_helpers.py` — 공통 함수
- `schedule/static/js/utils.js` — api(), time helpers, showToast
- `schedule/static/js/modals.js` — confirm/alert/memo modals
- `schedule/static/js/drag-core.js` — startDrag, findTarget, ghost, highlight
- `schedule/static/js/block-move.js` — initBlockMove, initMonthBlockMove
- `schedule/static/js/block-resize.js` — initResize
- `schedule/static/js/queue-drag.js` — initQueueDrag, identifier picker
- `schedule/static/js/context-menu.js` — initContextMenu, split picker
- `schedule/static/js/block-detail.js` — showTaskDetailPopup, initBlockDetail
- `schedule/static/js/schedule-features.js` — weekend toggle, shift, add buttons, queue search
- `schedule/static/js/schedule-app.js` — DOMContentLoaded init
- `tests/test_calendar_api.py` — calendar API 전용 테스트
- `tests/test_enrichment.py` — enrichment 로직 테스트
- `tests/test_integration.py` — 통합 시나리오 테스트

### Modified Files
- `schedule/models/user.py`, `location.py`, `version.py`, `task.py`, `schedule_block.py` — BaseRepository 상속
- `schedule/routes/__init__.py` — 새 모듈 등록
- `schedule/static/css/style.css` — CSS 변수화, 중복 제거
- `schedule/templates/schedule/day.html`, `week.html`, `month.html` — JS 로드 변경
- `schedule/templates/base.html` — 공통 JS 로드

### Deleted Files
- `schedule/static/js/drag_drop.js` — 10개 모듈로 대체
- `schedule/routes/calendar.py` — 3개 파일로 대체

---

### Task 1: 테스트 보강 — calendar API

**Files:**
- Create: `tests/test_calendar_api.py`

- [ ] **Step 1: calendar API 테스트 작성**

```python
"""Tests for calendar block API endpoints."""
import json
from tests.conftest import (
    _create_user, _create_location, _create_task, _create_version, _create_block,
)


class TestBlockCreate:
    def test_create_normal_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        block, status = _create_block(client, tid, uid)
        assert status == 201
        assert block['task_id'] == tid

    def test_create_simple_block(self, client):
        r = client.post('/schedule/api/simple-blocks', json={
            'title': '장비 점검', 'estimated_minutes': 60,
        })
        assert r.status_code == 201

    def test_create_block_overlap_rejected(self, client):
        uid = _create_user(client)
        lid = _create_location(client)
        tid = _create_task(client, uid, loc_id=lid, hours='4')
        _create_block(client, tid, uid, start='09:00', end='10:00')
        tid2 = _create_task(client, uid, loc_id=lid, hours='4')
        _, status = _create_block(client, tid2, uid, start='09:00', end='10:00')
        assert status == 409

    def test_create_block_with_identifier_ids(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid, 'assignee_ids': [uid],
            'date': '2026-05-01', 'start_time': '09:00', 'end_time': '10:00',
            'identifier_ids': ['TC-001'],
        })
        assert r.status_code == 201
        assert r.get_json()['identifier_ids'] == ['TC-001']


class TestBlockUpdate:
    def test_move_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        block, _ = _create_block(client, tid, uid, date_str='2026-05-01')
        r = client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'date': '2026-05-02', 'start_time': '10:00', 'end_time': '11:00',
        })
        assert r.status_code == 200
        assert r.get_json()['date'] == '2026-05-02'

    def test_resize_no_remaining_change(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        t_before = client.get(f'/tasks/api/{tid}').get_json()['task']
        client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '09:00', 'end_time': '10:00', 'resize': True,
        })
        t_after = client.get(f'/tasks/api/{tid}').get_json()['task']
        assert t_after['remaining_hours'] == t_before['remaining_hours']
        assert t_after['estimated_hours'] == 4.0


class TestBlockDelete:
    def test_delete_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        block, _ = _create_block(client, tid, uid)
        r = client.delete(f'/schedule/api/blocks/{block["id"]}')
        assert r.status_code == 200

    def test_restore_to_queue_clears_location(self, client):
        uid = _create_user(client)
        lid = _create_location(client)
        tid = _create_task(client, uid, loc_id=lid, hours='2')
        block, _ = _create_block(client, tid, uid)
        client.delete(f'/schedule/api/blocks/{block["id"]}?restore=1')
        t = client.get(f'/tasks/api/{tid}').get_json()['task']
        assert t['location_id'] == ''


class TestBlockSplit:
    def test_split_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid, start='09:00', end='11:00')
        r = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={
            'keep_identifier_ids': ['TC-001'],
        })
        assert r.status_code == 200

    def test_split_requires_identifiers(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        block, _ = _create_block(client, tid, uid)
        r = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={
            'keep_identifier_ids': [],
        })
        assert r.status_code == 400


class TestBlockShift:
    def test_shift_forward(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        _create_block(client, tid, uid, date_str='2026-05-04')  # Monday
        r = client.post('/schedule/api/blocks/shift', json={
            'from_date': '2026-05-04', 'direction': 1,
        })
        assert r.status_code == 200
        assert r.get_json()['shifted_count'] >= 1

    def test_shift_skips_weekend(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        _create_block(client, tid, uid, date_str='2026-05-08')  # Friday
        r = client.post('/schedule/api/blocks/shift', json={
            'from_date': '2026-05-08', 'direction': 1,
        })
        data = r.get_json()
        assert data['shifted_count'] == 1
        # Verify block moved to Monday (skipped Sat/Sun)
        blocks = client.get(f'/schedule/api/blocks/by-task/{tid}').get_json()['blocks']
        assert blocks[0]['date'] == '2026-05-11'


class TestBlocksByTask:
    def test_get_blocks_by_task(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        _create_block(client, tid, uid, date_str='2026-05-01')
        _create_block(client, tid, uid, date_str='2026-05-02')
        r = client.get(f'/schedule/api/blocks/by-task/{tid}')
        assert r.status_code == 200
        assert len(r.get_json()['blocks']) == 2
```

- [ ] **Step 2: 테스트 실행하여 모두 통과 확인**

Run: `pytest tests/test_calendar_api.py -v`
Expected: ALL PASS

- [ ] **Step 3: 커밋**

```bash
git add tests/test_calendar_api.py
git commit -m "test: calendar API 테스트 추가 (블록 CRUD, 분리, 이동)"
```

---

### Task 2: 테스트 보강 — enrichment + 통합

**Files:**
- Create: `tests/test_enrichment.py`
- Create: `tests/test_integration.py`

- [ ] **Step 1: enrichment 테스트 작성**

```python
"""Tests for enrichment helpers."""
import json
import os
from tests.conftest import (
    _create_user, _create_location, _create_task, _create_version, _create_block,
)


class TestEnrichBlocks:
    def test_enrich_normal_block(self, client):
        uid = _create_user(client)
        lid = _create_location(client, name='STE1')
        tid = _create_task(client, uid, loc_id=lid, hours='2')
        _create_block(client, tid, uid, date_str='2026-05-01')
        r = client.get('/schedule/api/day?date=2026-05-01')
        blocks = r.get_json()['blocks']
        assert len(blocks) >= 1
        b = blocks[0]
        assert b['section_name'] == '3.1 시스템'
        assert b['location_name'] == 'STE1'
        assert 'color' in b

    def test_enrich_split_block(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid, 'assignee_ids': [uid],
            'date': '2026-05-01', 'start_time': '09:00', 'end_time': '10:00',
            'identifier_ids': ['TC-001'],
        })
        data = client.get('/schedule/api/day?date=2026-05-01').get_json()
        blocks = data['blocks']
        b = [x for x in blocks if x.get('identifier_ids')]
        assert len(b) >= 1
        assert b[0]['is_split'] is True
        assert b[0]['block_identifier_count'] == 1


class TestQueueTasks:
    def test_queue_excludes_completed(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='2')
        client.put(f'/tasks/api/{tid}/update', json={
            'procedure_id': 'X', 'status': 'completed',
            'estimated_hours': 2, 'remaining_hours': 0,
        })
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_tasks']
        assert all(q['id'] != tid for q in queue)

    def test_queue_remaining_calculation(self, client):
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')
        _create_block(client, tid, uid, start='10:00', end='11:00')
        r = client.get('/schedule/api/day')
        queue = r.get_json()['queue_tasks']
        match = [q for q in queue if q['id'] == tid]
        assert len(match) == 1
        assert match[0]['remaining_unscheduled_hours'] < 4.0
```

- [ ] **Step 2: 통합 테스트 작성**

```python
"""Integration tests — end-to-end scenarios."""
from tests.conftest import (
    _create_user, _create_location, _create_task, _create_version, _create_block,
)


class TestFullWorkflow:
    def test_create_place_resize_restore(self, client):
        """Task 생성 → 블록 배치 → 리사이즈 → 큐 복귀 시나리오."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')

        # Place block
        block, status = _create_block(client, tid, uid, start='09:00', end='11:00')
        assert status == 201

        # Resize smaller (real time change)
        client.put(f'/schedule/api/blocks/{block["id"]}', json={
            'start_time': '09:00', 'end_time': '10:00', 'resize': True,
        })

        # Task estimated_hours unchanged
        t = client.get(f'/tasks/api/{tid}').get_json()['task']
        assert t['estimated_hours'] == 4.0

        # Restore to queue
        client.delete(f'/schedule/api/blocks/{block["id"]}?restore=1')

        # Task should appear in queue again
        r = client.get('/schedule/api/day')
        queue_ids = [q['id'] for q in r.get_json()['queue_tasks']]
        assert tid in queue_ids

    def test_split_and_place_separately(self, client):
        """분할 배치 시나리오: 식별자를 나눠 다른 날에 배치."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')

        # Place with only TC-001
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid, 'assignee_ids': [uid],
            'date': '2026-05-01', 'start_time': '09:00', 'end_time': '10:00',
            'identifier_ids': ['TC-001'],
        })
        b1_id = r.get_json()['id']

        # Place with only TC-002
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid, 'assignee_ids': [uid],
            'date': '2026-05-02', 'start_time': '09:00', 'end_time': '10:00',
            'identifier_ids': ['TC-002'],
        })
        assert r.status_code == 201

        # Verify both blocks exist
        blocks = client.get(f'/schedule/api/blocks/by-task/{tid}').get_json()['blocks']
        assert len(blocks) == 2

    def test_identifier_move_between_blocks(self, client):
        """기존 블록의 식별자를 새 블록으로 이동."""
        uid = _create_user(client)
        tid = _create_task(client, uid, hours='4')

        # Place TC-001 in block 1
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid, 'assignee_ids': [uid],
            'date': '2026-05-01', 'start_time': '09:00', 'end_time': '10:00',
            'identifier_ids': ['TC-001'],
        })
        b1_id = r.get_json()['id']

        # Place TC-001 + TC-002 in block 2 (TC-001 should move from block 1)
        r = client.post('/schedule/api/blocks', json={
            'task_id': tid, 'assignee_ids': [uid],
            'date': '2026-05-02', 'start_time': '09:00', 'end_time': '11:00',
            'identifier_ids': ['TC-001', 'TC-002'],
        })
        assert r.status_code == 201

        # Block 1 should be deleted (lost all identifiers)
        blocks = client.get(f'/schedule/api/blocks/by-task/{tid}').get_json()['blocks']
        block_ids = [b['id'] for b in blocks]
        assert b1_id not in block_ids
```

- [ ] **Step 3: 테스트 실행**

Run: `pytest tests/test_enrichment.py tests/test_integration.py -v`
Expected: ALL PASS

- [ ] **Step 4: 전체 테스트 확인 후 커밋**

Run: `pytest tests/ -v`
Expected: ALL PASS

```bash
git add tests/test_enrichment.py tests/test_integration.py
git commit -m "test: enrichment + 통합 테스트 추가"
```

---

### Task 3: 모델 BaseRepository 추출

**Files:**
- Create: `schedule/models/base.py`
- Modify: `schedule/models/user.py`
- Modify: `schedule/models/location.py`
- Modify: `schedule/models/version.py`
- Modify: `schedule/models/task.py`
- Modify: `schedule/models/schedule_block.py`

- [ ] **Step 1: BaseRepository 작성**

Create `schedule/models/base.py`:

```python
from schedule.store import read_json, write_json, generate_id

ALLOWED_ALL = None  # sentinel for "update any field"


class BaseRepository:
    """Base class for JSON-file-backed repositories."""

    FILENAME = ''
    ID_PREFIX = ''
    ALLOWED_FIELDS = ALLOWED_ALL  # set of field names, or None for all

    @classmethod
    def get_all(cls):
        return read_json(cls.FILENAME)

    @classmethod
    def get_by_id(cls, item_id):
        for item in read_json(cls.FILENAME):
            if item['id'] == item_id:
                return item
        return None

    @classmethod
    def create(cls, data):
        items = read_json(cls.FILENAME)
        data['id'] = generate_id(cls.ID_PREFIX)
        items.append(data)
        write_json(cls.FILENAME, items)
        return data

    @classmethod
    def patch(cls, item_id, **kwargs):
        items = read_json(cls.FILENAME)
        for item in items:
            if item['id'] == item_id:
                for k, v in kwargs.items():
                    if cls.ALLOWED_FIELDS is None or k in cls.ALLOWED_FIELDS:
                        item[k] = v
                write_json(cls.FILENAME, items)
                return item
        return None

    @classmethod
    def delete(cls, item_id):
        items = read_json(cls.FILENAME)
        items = [i for i in items if i['id'] != item_id]
        write_json(cls.FILENAME, items)

    @classmethod
    def filter_by(cls, **kwargs):
        """Filter items by field values."""
        result = read_json(cls.FILENAME)
        for key, value in kwargs.items():
            result = [i for i in result if i.get(key) == value]
        return result
```

- [ ] **Step 2: user.py 리팩토링**

Rewrite `schedule/models/user.py`:

```python
from schedule.models.base import BaseRepository


class UserRepository(BaseRepository):
    FILENAME = 'users.json'
    ID_PREFIX = 'u_'

    @classmethod
    def create(cls, name, role, color):
        return super().create({
            'name': name, 'role': role, 'color': color,
        })

    @classmethod
    def update(cls, user_id, name, role, color):
        return cls.patch(user_id, name=name, role=role, color=color)


# Module-level aliases for backward compatibility
get_all = UserRepository.get_all
get_by_id = UserRepository.get_by_id
create = UserRepository.create
update = UserRepository.update
delete = UserRepository.delete
```

- [ ] **Step 3: location.py 리팩토링**

Rewrite `schedule/models/location.py`:

```python
from schedule.models.base import BaseRepository


class LocationRepository(BaseRepository):
    FILENAME = 'locations.json'
    ID_PREFIX = 'loc_'

    @classmethod
    def create(cls, name, color, description=''):
        return super().create({
            'name': name, 'color': color, 'description': description,
        })

    @classmethod
    def update(cls, loc_id, name, color, description=''):
        return cls.patch(loc_id, name=name, color=color, description=description)


get_all = LocationRepository.get_all
get_by_id = LocationRepository.get_by_id
create = LocationRepository.create
update = LocationRepository.update
delete = LocationRepository.delete
```

- [ ] **Step 4: version.py 리팩토링**

Rewrite `schedule/models/version.py`:

```python
from datetime import datetime
from schedule.models.base import BaseRepository


class VersionRepository(BaseRepository):
    FILENAME = 'versions.json'
    ID_PREFIX = 'v_'

    @classmethod
    def get_active(cls):
        return [v for v in cls.get_all() if v.get('is_active', True)]

    @classmethod
    def create(cls, name, description=''):
        return super().create({
            'name': name,
            'description': description,
            'is_active': True,
            'created_at': datetime.now().isoformat(timespec='seconds'),
        })

    @classmethod
    def update(cls, version_id, name, description, is_active=True):
        return cls.patch(version_id, name=name, description=description,
                         is_active=is_active)


get_all = VersionRepository.get_all
get_active = VersionRepository.get_active
get_by_id = VersionRepository.get_by_id
create = VersionRepository.create
update = VersionRepository.update
delete = VersionRepository.delete
```

- [ ] **Step 5: task.py 리팩토링**

Rewrite `schedule/models/task.py`:

```python
from datetime import datetime
from schedule.models.base import BaseRepository


class TaskRepository(BaseRepository):
    FILENAME = 'tasks.json'
    ID_PREFIX = 't_'

    @classmethod
    def get_by_version(cls, version_id):
        return cls.filter_by(version_id=version_id)

    @classmethod
    def validate_unique_identifiers(cls, test_list, exclude_task_id=None):
        new_ids = [item['id'] for item in test_list if isinstance(item, dict)]
        if not new_ids:
            return []
        existing_ids = set()
        for t in cls.get_all():
            if exclude_task_id and t['id'] == exclude_task_id:
                continue
            for item in t.get('test_list', []):
                if isinstance(item, dict):
                    existing_ids.add(item['id'])
                else:
                    existing_ids.add(item)
        return [i for i in new_ids if i in existing_ids]

    @classmethod
    def compute_estimated_hours(cls, test_list):
        return round(sum(
            item.get('estimated_hours', 0)
            for item in (test_list or [])
            if isinstance(item, dict)
        ), 2)

    @classmethod
    def create(cls, procedure_id, version_id, assignee_ids, location_id,
               section_name, procedure_owner, test_list,
               estimated_hours, memo=''):
        return super().create({
            'procedure_id': procedure_id,
            'version_id': version_id,
            'assignee_ids': assignee_ids or [],
            'location_id': location_id,
            'section_name': section_name,
            'procedure_owner': procedure_owner,
            'test_list': test_list or [],
            'estimated_hours': estimated_hours,
            'remaining_hours': estimated_hours,
            'status': 'waiting',
            'memo': memo,
            'created_at': datetime.now().isoformat(timespec='seconds'),
        })

    @classmethod
    def update(cls, task_id, procedure_id, version_id, assignee_ids,
               location_id, section_name, procedure_owner, test_list,
               estimated_hours, remaining_hours, status, memo=''):
        return cls.patch(
            task_id,
            procedure_id=procedure_id,
            version_id=version_id,
            assignee_ids=assignee_ids or [],
            location_id=location_id,
            section_name=section_name,
            procedure_owner=procedure_owner,
            test_list=test_list or [],
            estimated_hours=estimated_hours,
            remaining_hours=remaining_hours,
            status=status,
            memo=memo,
        )


get_all = TaskRepository.get_all
get_by_id = TaskRepository.get_by_id
get_by_version = TaskRepository.get_by_version
create = TaskRepository.create
update = TaskRepository.update
patch = TaskRepository.patch
delete = TaskRepository.delete
validate_unique_identifiers = TaskRepository.validate_unique_identifiers
compute_estimated_hours = TaskRepository.compute_estimated_hours
```

- [ ] **Step 6: schedule_block.py 리팩토링**

Rewrite `schedule/models/schedule_block.py`:

```python
from schedule.models.base import BaseRepository


class ScheduleBlockRepository(BaseRepository):
    FILENAME = 'schedule_blocks.json'
    ID_PREFIX = 'sb_'
    ALLOWED_FIELDS = {
        'date', 'start_time', 'end_time', 'is_draft', 'is_locked',
        'block_status', 'task_id', 'assignee_ids', 'location_id',
        'version_id', 'origin', 'memo', 'identifier_ids', 'title', 'is_simple',
    }

    @classmethod
    def get_by_date(cls, date_str):
        return [b for b in cls.get_all() if b['date'] == date_str]

    @classmethod
    def get_by_date_range(cls, start_date, end_date):
        return [b for b in cls.get_all()
                if start_date <= b['date'] <= end_date]

    @classmethod
    def get_by_version(cls, version_id):
        return cls.filter_by(version_id=version_id)

    @classmethod
    def get_by_assignee(cls, assignee_id):
        return [b for b in cls.get_all()
                if assignee_id in b.get('assignee_ids', [])]

    @classmethod
    def get_by_location_and_date(cls, location_id, date_str):
        return [b for b in cls.get_all()
                if b.get('location_id') == location_id and b['date'] == date_str]

    @classmethod
    def create(cls, task_id, assignee_ids, location_id, version_id,
               date, start_time, end_time,
               is_draft=False, is_locked=False, origin='manual',
               block_status='pending', identifier_ids=None,
               title='', is_simple=False):
        return super().create({
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
            'identifier_ids': identifier_ids,
            'title': title,
            'is_simple': is_simple,
        })

    @classmethod
    def update(cls, block_id, **kwargs):
        return cls.patch(block_id, **kwargs)

    @classmethod
    def delete_drafts(cls):
        from schedule.store import read_json, write_json
        blocks = read_json(cls.FILENAME)
        blocks = [b for b in blocks if not b.get('is_draft')]
        write_json(cls.FILENAME, blocks)

    @classmethod
    def approve_drafts(cls):
        from schedule.store import read_json, write_json
        blocks = read_json(cls.FILENAME)
        for b in blocks:
            if b.get('is_draft'):
                b['is_draft'] = False
        write_json(cls.FILENAME, blocks)


get_all = ScheduleBlockRepository.get_all
get_by_id = ScheduleBlockRepository.get_by_id
get_by_date = ScheduleBlockRepository.get_by_date
get_by_date_range = ScheduleBlockRepository.get_by_date_range
get_by_version = ScheduleBlockRepository.get_by_version
get_by_assignee = ScheduleBlockRepository.get_by_assignee
get_by_location_and_date = ScheduleBlockRepository.get_by_location_and_date
create = ScheduleBlockRepository.create
update = ScheduleBlockRepository.update
delete = ScheduleBlockRepository.delete
delete_drafts = ScheduleBlockRepository.delete_drafts
approve_drafts = ScheduleBlockRepository.approve_drafts
```

- [ ] **Step 7: 전체 테스트 실행**

Run: `pytest tests/ -v`
Expected: ALL PASS (128+ tests)

- [ ] **Step 8: 커밋**

```bash
git add schedule/models/
git commit -m "refactor: BaseRepository 추출 — 모델 CRUD 중복 제거"
```

---

### Task 4: calendar.py 분리

**Files:**
- Create: `schedule/routes/calendar_helpers.py`
- Create: `schedule/routes/calendar_views.py`
- Create: `schedule/routes/calendar_api.py`
- Modify: `schedule/routes/__init__.py`
- Delete: `schedule/routes/calendar.py`

- [ ] **Step 1: calendar_helpers.py 작성**

현재 `calendar.py`에서 `_get_current_version_id`, `_sync_task_remaining_hours`, `_remove_identifiers_from_other_blocks`, `_sync_task_status`, `VALID_BLOCK_STATUSES`, `DAY_NAMES`를 추출.

`schedule/routes/calendar_helpers.py`에 이 함수들을 복사. 코드는 현재 `calendar.py`의 해당 함수들 그대로.

- [ ] **Step 2: calendar_views.py 작성**

`day_view`, `week_view`, `month_view` + API data 엔드포인트들을 이동. `_prepare_view_context()` 공통 함수 추가.

- [ ] **Step 3: calendar_api.py 작성**

블록 CRUD, lock, status, memo, export, shift, split, blocks-by-task, simple-blocks 엔드포인트 이동.

- [ ] **Step 4: `__init__.py` 업데이트**

```python
from schedule.routes.calendar_views import schedule_bp
from schedule.routes.tasks import tasks_bp
from schedule.routes.admin import admin_bp


def register_routes(app):
    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(admin_bp)
```

- [ ] **Step 5: 기존 calendar.py 삭제**

- [ ] **Step 6: 전체 테스트 실행**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: 커밋**

```bash
git add schedule/routes/
git commit -m "refactor: calendar.py를 views/api/helpers로 분리"
```

---

### Task 5: 데이터 정리 — 미사용 필드 제거

**Files:**
- Modify: `schedule/models/schedule_block.py` — ALLOWED_FIELDS에서 `origin`, `is_draft` 제거
- Modify: `data/schedule_blocks.json` — 기존 데이터에서 필드 strip
- Modify: `migrate_data.py` — 정리 스크립트 추가

- [ ] **Step 1: migrate_data.py에 정리 함수 추가**

```python
def cleanup_schedule_blocks():
    blocks = read('schedule_blocks.json')
    for b in blocks:
        b.pop('origin', None)
        b.pop('is_draft', None)
    write('schedule_blocks.json', blocks)
    print(f'  Cleaned {len(blocks)} blocks')
```

- [ ] **Step 2: 마이그레이션 실행, schedule_block.py에서 ALLOWED_FIELDS 정리**

- [ ] **Step 3: 테스트 실행 후 커밋**

```bash
git add data/ schedule/models/ migrate_data.py
git commit -m "chore: 미사용 필드 제거 (origin, is_draft)"
```

---

### Task 6: CSS 정리

**Files:**
- Modify: `schedule/static/css/style.css`

- [ ] **Step 1: CSS 변수 추가 (`:root`)**

파일 최상단에:
```css
:root {
  --color-text: #1e293b;
  --color-text-muted: #64748b;
  --color-text-light: #94a3b8;
  --color-bg: #f5f6f8;
  --color-bg-white: #fff;
  --color-bg-light: #f8f9fa;
  --color-bg-hover: #f1f5f9;
  --color-border: #e2e8f0;
  --color-border-light: #e9ecef;
  --color-primary: #0d6efd;
  --color-success: #28a745;
  --color-danger: #dc3545;
}
```

- [ ] **Step 2: 하드코딩된 색상을 변수로 교체 (주요 부분만)**

- [ ] **Step 3: 중복 규칙 제거**

`.queue-card-hours`, `.queue-card-id` 중복 정의 제거.

- [ ] **Step 4: 테스트 + 커밋**

```bash
git add schedule/static/css/style.css
git commit -m "style: CSS 변수화, 중복 규칙 제거"
```

---

### Task 7: JS 모듈 분할 — utils + modals

**Files:**
- Create: `schedule/static/js/utils.js`
- Create: `schedule/static/js/modals.js`

- [ ] **Step 1: utils.js 작성**

`drag_drop.js`에서 `showToast`, `api`, `getTaskRemaining`, `checkRemainingAfterPlace`, `showRemainingAlert`, `pad`, `timeToMin`, `minToTime`, `snapMin`, `workMinutes`, `isReadonly`를 추출.

`window.ScheduleApp` 네임스페이스에 등록:

```javascript
window.ScheduleApp = window.ScheduleApp || {};
(function(App) {
  'use strict';
  var GRID_MINUTES = window.GRID_INTERVAL || 15;
  var SLOT_HEIGHT = 24;
  // ... 함수 정의 ...
  App.GRID_MINUTES = GRID_MINUTES;
  App.SLOT_HEIGHT = SLOT_HEIGHT;
  App.showToast = showToast;
  App.api = api;
  // ... etc
})(window.ScheduleApp);
```

- [ ] **Step 2: modals.js 작성**

`showConfirmModal`, `showRemainingAlert`, `openMemoModal` 추출.

- [ ] **Step 3: drag_drop.js에서 추출된 코드 제거, App 참조로 교체**

- [ ] **Step 4: 템플릿에서 스크립트 로드 순서 변경**

`base.html`의 scripts 블록 앞에 utils.js, modals.js를 로드.

- [ ] **Step 5: 서버 구동 후 수동 검증**

- [ ] **Step 6: 테스트 + 커밋**

```bash
git add schedule/static/js/ schedule/templates/
git commit -m "refactor: JS utils + modals 모듈 분리"
```

---

### Task 8: JS 모듈 분할 — drag-core

**Files:**
- Create: `schedule/static/js/drag-core.js`

- [ ] **Step 1: drag-core.js 작성**

`hideAllBlocks`, `showAllBlocks`, `getLocations`, `getWeekGuideLocs`, `ensureWeekGuide`, `resolveWeekLocation`, `showWeekLocationGuides`, `hideWeekLocationGuides`, `findTarget`, `createGhost`, `setHighlight`, `clearHighlight`, `startDrag` 추출.

- [ ] **Step 2: drag_drop.js에서 제거, App 참조로 교체**

- [ ] **Step 3: 수동 검증 — 드래그앤드롭 동작**

체크리스트:
- 큐→시간표 드래그
- 블록 이동
- 주간뷰 장소 가이드 표시
- 고스트 표시

- [ ] **Step 4: 테스트 + 커밋**

```bash
git add schedule/static/js/
git commit -m "refactor: JS drag-core 모듈 분리"
```

---

### Task 9: JS 모듈 분할 — block-move, block-resize, queue-drag

**Files:**
- Create: `schedule/static/js/block-move.js`
- Create: `schedule/static/js/block-resize.js`
- Create: `schedule/static/js/queue-drag.js`

- [ ] **Step 1: block-move.js — initBlockMove + initMonthBlockMove**

- [ ] **Step 2: block-resize.js — initResize**

- [ ] **Step 3: queue-drag.js — initQueueDrag + showIdentifierPicker**

- [ ] **Step 4: 수동 검증 — 드래그앤드롭 전체 동작**

체크리스트:
- 큐→시간표 드래그 (단일/분할)
- 블록→다른시간 이동
- 블록→큐 복귀
- 블록 리사이즈 (늘리기/줄이기/경고)
- 월간뷰 블록 이동

- [ ] **Step 5: 테스트 + 커밋**

```bash
git add schedule/static/js/
git commit -m "refactor: JS block-move, block-resize, queue-drag 분리"
```

---

### Task 10: JS 모듈 분할 — context-menu, block-detail, schedule-features, schedule-app

**Files:**
- Create: `schedule/static/js/context-menu.js`
- Create: `schedule/static/js/block-detail.js`
- Create: `schedule/static/js/schedule-features.js`
- Create: `schedule/static/js/schedule-app.js`
- Delete: `schedule/static/js/drag_drop.js`

- [ ] **Step 1: context-menu.js — initContextMenu + showSplitPicker**

- [ ] **Step 2: block-detail.js — showTaskDetailPopup + initBlockDetail**

- [ ] **Step 3: schedule-features.js — initWeekendToggle, initShiftSchedule, initAddButtons, initQueueSearch, initQueueToggle, initTaskHoverLink, initReturnToQueue**

- [ ] **Step 4: schedule-app.js — DOMContentLoaded 진입점**

```javascript
window.ScheduleApp = window.ScheduleApp || {};
document.addEventListener('DOMContentLoaded', function() {
  var App = window.ScheduleApp;
  if (window.GRID_INTERVAL) App.GRID_MINUTES = window.GRID_INTERVAL;
  App.initBlockMove();
  App.initMonthBlockMove();
  App.initQueueDrag();
  App.initResize();
  App.initContextMenu();
  App.initReturnToQueue();
  App.initQueueSearch();
  App.initQueueToggle();
  App.initTaskHoverLink();
  App.initBlockDetail();
  App.initWeekendToggle();
  App.initShiftSchedule();
  App.initAddButtons();
});
```

- [ ] **Step 5: 기존 drag_drop.js 삭제**

- [ ] **Step 6: 템플릿 업데이트 — 모든 JS 파일 로드**

day.html, week.html, month.html의 scripts 블록에서 `drag_drop.js` 대신 새 모듈들 로드.

- [ ] **Step 7: 전체 수동 검증**

체크리스트:
- [ ] 큐→시간표 드래그 (단일/분할)
- [ ] 블록 이동 (같은날/다른날/큐복귀)
- [ ] 블록 리사이즈 (늘리기/줄이기/경고팝업)
- [ ] 우클릭 메뉴 (상태변경/분리/삭제)
- [ ] 더블클릭 상세팝업
- [ ] 주말토글, 일정이동
- [ ] 장소 필터 복수 선택
- [ ] 간단블록/시험 추가 버튼

- [ ] **Step 8: 전체 테스트**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 9: 커밋**

```bash
git add schedule/static/js/ schedule/templates/
git rm schedule/static/js/drag_drop.js
git commit -m "refactor: JS 모듈 분할 완료 — drag_drop.js를 10개 모듈로 분리"
```

---

### Task 11: 최종 검증 + 정리 커밋

- [ ] **Step 1: 전체 테스트**

Run: `pytest tests/ -v`

- [ ] **Step 2: 서버 구동 확인**

Run: `python3 run.py`
브라우저에서 http://localhost:5001 접속

- [ ] **Step 3: 최종 커밋**

```bash
git add -A
git commit -m "refactor: 리팩토링 완료 — 코드 가독성 및 유지보수성 개선"
```
