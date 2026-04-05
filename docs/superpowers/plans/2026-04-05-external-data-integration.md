# External Data Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provider 추상화로 외부 데이터(버전, 시험식별자, 작성자)를 연동 가능하게 하고, 동기화 서비스로 내부 데이터와 병합한다.

**Architecture:** BaseProvider ABC → JsonFileProvider 기본 구현 → SyncService가 Provider로부터 데이터를 가져와 version/task 모델에 병합. 외부 원본 데이터는 UI에서 읽기 전용.

**Tech Stack:** Flask, pytest, ABC (abc 모듈)

---

## File Structure

### New Files
- `schedule/providers/__init__.py` — get_provider() 팩토���
- `schedule/providers/base.py` — BaseProvider ABC
- `schedule/providers/json_file.py` — JsonFileProvider (procedures.json + versions.json 읽기)
- `schedule/services/sync.py` — SyncService
- `schedule/routes/sync.py` — 동기화 API 라우트
- `tests/test_providers.py` — Provider 테스트
- `tests/test_sync.py` — 동기화 서비스 + API 테스트

### Modified Files
- `schedule/models/base.py` — create()에 외부 ID 허용
- `schedule/models/version.py` — create()에 id 파라미터 추가
- `schedule/models/task.py` — source, external_key 필드
- `schedule/routes/__init__.py` — sync 블루프린트 등록
- `schedule/__init__.py` — PROVIDER_TYPE 설정
- `schedule/templates/tasks/form.html` — 외부 데이터 읽기 전용
- `schedule/templates/tasks/list.html` — "외부" 뱃지
- `schedule/templates/admin/versions.html` — 동기화 버튼
- `data/tasks.json` — 마이그레이션 (source, external_key 추가)

### NOT Modified (사이드이펙트 방지)
- `schedule/models/schedule_block.py`, `user.py`, `location.py`, `settings.py`
- `schedule/routes/calendar_views.py`, `calendar_api.py`, `calendar_helpers.py`
- `schedule/helpers/enrichment.py`, `overlap.py`, `time_utils.py`
- `schedule/static/js/*.js` (10개 모듈 전부)
- `schedule/static/css/style.css`

---

### Task 1: BaseProvider + JsonFileProvider

**Files:**
- Create: `schedule/providers/__init__.py`
- Create: `schedule/providers/base.py`
- Create: `schedule/providers/json_file.py`
- Create: `tests/test_providers.py`

- [ ] **Step 1: Provider 테스트 작성**

Create `tests/test_providers.py`:

```python
"""Tests for data providers."""
import json
import os
import pytest
from schedule import create_app


@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    # Versions
    with open(os.path.join(data_dir, 'versions.json'), 'w') as f:
        json.dump([
            {'id': 'VER-001', 'name': 'v1.0.0', 'description': '1차', 'is_active': True, 'created_at': ''},
            {'id': 'VER-002', 'name': 'v2.0.0', 'description': '2차', 'is_active': True, 'created_at': ''},
        ], f)
    # Procedures (external test data source)
    with open(os.path.join(data_dir, 'procedures.json'), 'w') as f:
        json.dump([
            {
                'section_name': '3.1 시스템',
                'version_id': 'VER-001',
                'identifiers': [
                    {'id': 'TC-001', 'estimated_hours': 0.5, 'owners': ['김���수']},
                    {'id': 'TC-002', 'estimated_hours': 0.75, 'owners': ['이지은']},
                ],
            },
            {
                'section_name': '4.1 항법',
                'version_id': 'VER-002',
                'identifiers': [
                    {'id': 'TC-010', 'estimated_hours': 1.0, 'owners': ['박준혁']},
                ],
            },
        ], f)
    # Empty files for other models
    for name in ('users', 'locations', 'tasks', 'schedule_blocks'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00', 'work_end': '17:00',
            'actual_work_start': '08:30', 'actual_work_end': '16:30',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [], 'grid_interval_minutes': 10,
            'max_schedule_days': 14, 'block_color_by': 'location',
        }, f)

    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


class TestJsonFileProvider:
    def test_get_versions(self, app):
        with app.app_context():
            from schedule.providers import get_provider
            provider = get_provider()
            versions = provider.get_versions()
            assert len(versions) == 2
            assert versions[0]['id'] == 'VER-001'
            assert versions[0]['name'] == 'v1.0.0'

    def test_get_test_data_by_version(self, app):
        with app.app_context():
            from schedule.providers import get_provider
            provider = get_provider()
            data = provider.get_test_data('VER-001')
            assert len(data) == 1
            assert data[0]['section_name'] == '3.1 시스템'
            assert len(data[0]['identifiers']) == 2

    def test_get_test_data_all(self, app):
        with app.app_context():
            from schedule.providers import get_provider
            provider = get_provider()
            data = provider.get_test_data_all()
            assert len(data) == 2

    def test_get_test_data_nonexistent_version(self, app):
        with app.app_context():
            from schedule.providers import get_provider
            provider = get_provider()
            data = provider.get_test_data('NOPE')
            assert data == []
```

- [ ] **Step 2: BaseProvider + JsonFileProvider 구현**

Create `schedule/providers/base.py`:
```python
from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Abstract base for external data providers."""

    @abstractmethod
    def get_versions(self):
        """Return list of version dicts: [{id, name, description}]"""

    @abstractmethod
    def get_test_data(self, version_id):
        """Return test data for a version: [{section_name, version_id, identifiers: [{id, estimated_hours, owners}]}]"""

    @abstractmethod
    def get_test_data_all(self):
        """Return all test data across all versions."""
```

Create `schedule/providers/json_file.py`:
```python
from schedule.providers.base import BaseProvider
from schedule.store import read_json


class JsonFileProvider(BaseProvider):
    """Provider that reads from local JSON files (default, backward-compatible)."""

    def get_versions(self):
        return [
            {'id': v['id'], 'name': v['name'], 'description': v.get('description', '')}
            for v in read_json('versions.json')
        ]

    def get_test_data(self, version_id):
        return [
            item for item in self._read_procedures()
            if item['version_id'] == version_id
        ]

    def get_test_data_all(self):
        return self._read_procedures()

    def _read_procedures(self):
        raw = read_json('procedures.json')
        result = []
        for p in raw:
            result.append({
                'section_name': p.get('section_name', ''),
                'version_id': p.get('version_id', ''),
                'identifiers': p.get('identifiers', p.get('test_list', [])),
            })
        return result
```

Create `schedule/providers/__init__.py`:
```python
import os

from schedule.providers.json_file import JsonFileProvider


def get_provider():
    """Factory: return the configured data provider."""
    provider_type = os.environ.get('PROVIDER_TYPE', 'json_file')
    if provider_type == 'json_file':
        return JsonFileProvider()
    raise ValueError(f'Unknown provider type: {provider_type}')
```

- [ ] **Step 3: 테스트 실행**

Run: `source venv/bin/activate && pytest tests/test_providers.py -v`
Expected: ALL PASS

Run: `pytest tests/ -q`
Expected: 149+ passed

- [ ] **Step 4: 커밋**

```bash
git add schedule/providers/ tests/test_providers.py
git commit -m "feat: BaseProvider + JsonFileProvider — 외부 데이터 소스 추상화"
```

---

### Task 2: 모델 변경 — 외부 ID 허용 + source 필드

**Files:**
- Modify: `schedule/models/base.py`
- Modify: `schedule/models/version.py`
- Modify: `schedule/models/task.py`
- Modify: `data/tasks.json` (마이그레이션)
- Modify: `migrate_data.py`

- [ ] **Step 1: base.py — create()에 외부 ID 허용**

`schedule/models/base.py`의 `create` 메서드를 수정 — `data`에 이미 `id`가 있으면 자동 생성하지 않음:

```python
@classmethod
def create(cls, data):
    """Create a new item. If 'id' not in data, auto-generate it."""
    items = read_json(cls.FILENAME)
    if 'id' not in data or not data['id']:
        data['id'] = generate_id(cls.ID_PREFIX)
    items.append(data)
    write_json(cls.FILENAME, items)
    return data
```

- [ ] **Step 2: version.py — create()에 id 파라미터 추가**

```python
@classmethod
def create(cls, name, description='', id=None):
    data = {
        'name': name,
        'description': description,
        'is_active': True,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    if id:
        data['id'] = id
    return super().create(data)
```

Alias 추가 없음 (기존 `create` alias가 이미 있음).

- [ ] **Step 3: task.py — source, external_key 필드 추가**

`TaskRepository.create()`에 `source='local'`, `external_key=''` 추가:

```python
@classmethod
def create(cls, procedure_id, version_id, assignee_ids, location_id,
           section_name, procedure_owner, test_list,
           estimated_hours, memo='', source='local', external_key=''):
    data = {
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
        'source': source,
        'external_key': external_key,
    }
    return super().create(data)
```

`get_by_external_key` 추가:

```python
@classmethod
def get_by_external_key(cls, key):
    for t in cls.get_all():
        if t.get('external_key') == key:
            return t
    return None
```

Module alias 추가: `get_by_external_key = TaskRepository.get_by_external_key`

- [ ] **Step 4: 마이그레이션 — 기존 task에 source/external_key 추가**

`migrate_data.py`에 추가:

```python
def add_source_fields():
    tasks = read('tasks.json')
    changed = 0
    for t in tasks:
        if 'source' not in t:
            t['source'] = 'local'
            t['external_key'] = ''
            changed += 1
    write('tasks.json', tasks)
    print(f'  Added source field to {changed} tasks')
```

실행: `python3 -c "exec(open('migrate_data.py').read()); add_source_fields()"`

- [ ] **Step 5: 전체 테스트**

Run: `pytest tests/ -q`
Expected: 149+ passed (기존 테스트 전부 통과)

- [ ] **Step 6: 커밋**

```bash
git add schedule/models/ data/tasks.json migrate_data.py
git commit -m "feat: 모델 변경 — 외부 ID 허용, source/external_key 필드 추가"
```

---

### Task 3: SyncService 구현

**Files:**
- Create: `schedule/services/sync.py`
- Create: `tests/test_sync.py`

- [ ] **Step 1: 동기화 테스트 작성**

Create `tests/test_sync.py`:

```python
"""Tests for sync service."""
import json
import os
import pytest
from schedule import create_app


@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    os.makedirs(data_dir)
    for name in ('users', 'locations', 'tasks', 'schedule_blocks'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(data_dir, 'versions.json'), 'w') as f:
        json.dump([], f)
    with open(os.path.join(data_dir, 'procedures.json'), 'w') as f:
        json.dump([
            {
                'section_name': '3.1 시스템',
                'version_id': 'VER-001',
                'identifiers': [
                    {'id': 'TC-001', 'estimated_hours': 0.5, 'owners': ['김민수']},
                    {'id': 'TC-002', 'estimated_hours': 0.75, 'owners': ['이���은']},
                ],
            },
        ], f)
    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
            'work_start': '08:00', 'work_end': '17:00',
            'actual_work_start': '08:30', 'actual_work_end': '16:30',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [], 'grid_interval_minutes': 10,
            'max_schedule_days': 14, 'block_color_by': 'location',
        }, f)
    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['TESTING'] = True
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


class TestSyncVersions:
    def test_sync_adds_new_versions(self, app):
        with app.app_context():
            from schedule.services.sync import SyncService
            from schedule.providers import get_provider
            from schedule.providers.base import BaseProvider

            class MockProvider(BaseProvider):
                def get_versions(self):
                    return [
                        {'id': 'VER-001', 'name': 'v1.0.0', 'description': '1차'},
                        {'id': 'VER-002', 'name': 'v2.0.0', 'description': '2차'},
                    ]
                def get_test_data(self, v): return []
                def get_test_data_all(self): return []

            result = SyncService.sync_versions(MockProvider())
            assert result['added'] == 2

            from schedule.models import version
            assert len(version.get_all()) == 2
            assert version.get_by_id('VER-001')['name'] == 'v1.0.0'

    def test_sync_updates_existing_version(self, app):
        with app.app_context():
            from schedule.models import version
            from schedule.services.sync import SyncService
            from schedule.providers.base import BaseProvider

            version.create(name='old', description='old desc', id='VER-001')

            class MockProvider(BaseProvider):
                def get_versions(self):
                    return [{'id': 'VER-001', 'name': 'v1.0.0', 'description': 'updated'}]
                def get_test_data(self, v): return []
                def get_test_data_all(self): return []

            result = SyncService.sync_versions(MockProvider())
            assert result['updated'] == 1
            assert version.get_by_id('VER-001')['name'] == 'v1.0.0'

    def test_sync_deactivates_removed_version(self, app):
        with app.app_context():
            from schedule.models import version
            from schedule.services.sync import SyncService
            from schedule.providers.base import BaseProvider

            version.create(name='removed', description='', id='VER-OLD')

            class MockProvider(BaseProvider):
                def get_versions(self):
                    return [{'id': 'VER-NEW', 'name': 'new', 'description': ''}]
                def get_test_data(self, v): return []
                def get_test_data_all(self): return []

            result = SyncService.sync_versions(MockProvider())
            old = version.get_by_id('VER-OLD')
            assert old['is_active'] is False
            assert result['deactivated'] == 1


class TestSyncTestData:
    def test_sync_creates_new_tasks(self, app):
        with app.app_context():
            from schedule.services.sync import SyncService
            from schedule.providers.base import BaseProvider

            class MockProvider(BaseProvider):
                def get_versions(self): return []
                def get_test_data(self, v): return []
                def get_test_data_all(self):
                    return [{
                        'section_name': '3.1 시스템',
                        'version_id': 'VER-001',
                        'identifiers': [
                            {'id': 'TC-001', 'estimated_hours': 0.5, 'owners': ['김민수']},
                        ],
                    }]

            result = SyncService.sync_test_data(MockProvider())
            assert result['added'] == 1

            from schedule.models import task
            tasks = task.get_all()
            assert len(tasks) == 1
            assert tasks[0]['source'] == 'external'
            assert tasks[0]['section_name'] == '3.1 시스템'
            assert tasks[0]['test_list'][0]['id'] == 'TC-001'

    def test_sync_updates_existing_task_identifiers(self, app):
        with app.app_context():
            from schedule.models import task
            from schedule.services.sync import SyncService
            from schedule.providers.base import BaseProvider

            task.create(
                procedure_id='X', version_id='VER-001',
                assignee_ids=['u_001'], location_id='loc_001',
                section_name='3.1 시스템', procedure_owner='',
                test_list=[{'id': 'TC-OLD', 'estimated_hours': 1.0, 'owners': []}],
                estimated_hours=1.0,
                source='external', external_key='3.1 시스템::VER-001',
            )

            class MockProvider(BaseProvider):
                def get_versions(self): return []
                def get_test_data(self, v): return []
                def get_test_data_all(self):
                    return [{
                        'section_name': '3.1 시스템',
                        'version_id': 'VER-001',
                        'identifiers': [
                            {'id': 'TC-NEW', 'estimated_hours': 2.0, 'owners': ['박준혁']},
                        ],
                    }]

            result = SyncService.sync_test_data(MockProvider())
            assert result['updated'] == 1

            t = task.get_all()[0]
            assert t['test_list'][0]['id'] == 'TC-NEW'
            assert t['assignee_ids'] == ['u_001']  # preserved
            assert t['location_id'] == 'loc_001'    # preserved

    def test_sync_cancels_removed_task(self, app):
        with app.app_context():
            from schedule.models import task
            from schedule.services.sync import SyncService
            from schedule.providers.base import BaseProvider

            task.create(
                procedure_id='X', version_id='VER-001',
                assignee_ids=[], location_id='',
                section_name='삭제될 장절', procedure_owner='',
                test_list=[], estimated_hours=0,
                source='external', external_key='삭제될 장절::VER-001',
            )

            class MockProvider(BaseProvider):
                def get_versions(self): return []
                def get_test_data(self, v): return []
                def get_test_data_all(self):
                    return []  # no data → existing should be cancelled

            result = SyncService.sync_test_data(MockProvider())
            assert result['cancelled'] == 1

            t = task.get_all()[0]
            assert t['status'] == 'cancelled'
```

- [ ] **Step 2: SyncService 구현**

Create `schedule/services/sync.py`:

```python
"""Synchronization service — merges external provider data into local models."""
from schedule.models import version, task


class SyncService:

    @staticmethod
    def sync_versions(provider):
        """Sync versions from provider. Returns {added, updated, deactivated}."""
        external = provider.get_versions()
        external_ids = {v['id'] for v in external}
        existing = {v['id']: v for v in version.get_all()}
        added = updated = deactivated = 0

        for ext in external:
            if ext['id'] in existing:
                version.update(ext['id'], name=ext['name'],
                               description=ext.get('description', ''),
                               is_active=True)
                updated += 1
            else:
                version.create(name=ext['name'],
                               description=ext.get('description', ''),
                               id=ext['id'])
                added += 1

        for vid, v in existing.items():
            if vid not in external_ids and v.get('is_active', True):
                version.patch(vid, is_active=False)
                deactivated += 1

        return {'added': added, 'updated': updated, 'deactivated': deactivated}

    @staticmethod
    def sync_test_data(provider, version_id=None):
        """Sync test data from provider. Returns {added, updated, cancelled, warnings}."""
        if version_id:
            external = provider.get_test_data(version_id)
        else:
            external = provider.get_test_data_all()

        external_keys = set()
        added = updated = cancelled = 0
        warnings = []

        for item in external:
            key = item['section_name'] + '::' + item['version_id']
            external_keys.add(key)
            existing = task.get_by_external_key(key)

            identifiers = item.get('identifiers', [])
            est_hours = round(sum(i.get('estimated_hours', 0) for i in identifiers), 4)

            if existing:
                # Update identifiers/hours but preserve app-owned fields
                task.patch(existing['id'],
                           test_list=identifiers,
                           estimated_hours=est_hours,
                           section_name=item['section_name'])
                updated += 1
            else:
                task.create(
                    procedure_id='EXT-' + str(len(task.get_all()) + 1).zfill(3),
                    version_id=item['version_id'],
                    assignee_ids=[],
                    location_id='',
                    section_name=item['section_name'],
                    procedure_owner='',
                    test_list=identifiers,
                    estimated_hours=est_hours,
                    source='external',
                    external_key=key,
                )
                added += 1

        # Cancel tasks whose external_key no longer exists
        for t in task.get_all():
            if (t.get('source') == 'external'
                    and t.get('external_key')
                    and t['external_key'] not in external_keys
                    and t.get('status') != 'cancelled'):
                task.patch(t['id'], status='cancelled')
                cancelled += 1

        return {'added': added, 'updated': updated,
                'cancelled': cancelled, 'warnings': warnings}
```

- [ ] **Step 3: 테스트 실행**

Run: `pytest tests/test_sync.py -v`
Expected: ALL PASS

Run: `pytest tests/ -q`
Expected: 149+ passed

- [ ] **Step 4: 커밋**

```bash
git add schedule/services/sync.py tests/test_sync.py
git commit -m "feat: SyncService — 버전/시험 데이터 동기화 서비스"
```

---

### Task 4: 동기화 API 라우트

**Files:**
- Create: `schedule/routes/sync.py`
- Modify: `schedule/routes/__init__.py`

- [ ] **Step 1: sync.py 라우트 작성**

```python
from flask import Blueprint, jsonify, request
from schedule.providers import get_provider
from schedule.services.sync import SyncService

sync_bp = Blueprint('sync', __name__, url_prefix='/api/sync')


@sync_bp.route('/versions', methods=['POST'])
def sync_versions():
    provider = get_provider()
    result = SyncService.sync_versions(provider)
    return jsonify(result)


@sync_bp.route('/test-data', methods=['POST'])
def sync_test_data():
    provider = get_provider()
    data = request.get_json() or {}
    version_id = data.get('version_id')
    result = SyncService.sync_test_data(provider, version_id=version_id)
    return jsonify(result)


@sync_bp.route('/status', methods=['GET'])
def sync_status():
    from schedule.models import version, task
    versions = version.get_all()
    tasks = task.get_all()
    external_tasks = [t for t in tasks if t.get('source') == 'external']
    return jsonify({
        'versions': len(versions),
        'external_tasks': len(external_tasks),
        'local_tasks': len(tasks) - len(external_tasks),
    })
```

- [ ] **Step 2: __init__.py에 블루프린트 등록**

```python
from schedule.routes.calendar_views import schedule_bp
from schedule.routes.tasks import tasks_bp
from schedule.routes.admin import admin_bp
from schedule.routes.sync import sync_bp

import schedule.routes.calendar_api  # noqa: F401


def register_routes(app):
    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(sync_bp)
```

- [ ] **Step 3: API 테스트 추가**

`tests/test_sync.py`에 추가:

```python
class TestSyncAPI:
    def test_sync_versions_api(self, client):
        r = client.post('/api/sync/versions')
        assert r.status_code == 200
        data = r.get_json()
        assert 'added' in data

    def test_sync_test_data_api(self, client):
        r = client.post('/api/sync/test-data', json={})
        assert r.status_code == 200
        data = r.get_json()
        assert 'added' in data

    def test_sync_status_api(self, client):
        r = client.get('/api/sync/status')
        assert r.status_code == 200
        data = r.get_json()
        assert 'versions' in data
        assert 'external_tasks' in data
```

- [ ] **Step 4: 전체 테스트**

Run: `pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add schedule/routes/sync.py schedule/routes/__init__.py tests/test_sync.py
git commit -m "feat: 동기화 API 라우트 (/api/sync/versions, test-data, status)"
```

---

### Task 5: 데이터 마이그레이션 + procedures.json 포맷 업데이트

**Files:**
- Modify: `migrate_data.py`
- Modify: `data/tasks.json`
- Modify: `data/procedures.json`

- [ ] **Step 1: migrate_data.py에 마이그레이션 함수 추가**

```python
def add_source_fields():
    """Add source and external_key to existing tasks."""
    tasks = read('tasks.json')
    changed = 0
    for t in tasks:
        if 'source' not in t:
            t['source'] = 'local'
            t['external_key'] = ''
            changed += 1
    write('tasks.json', tasks)
    print(f'  Added source field to {changed} tasks')


def update_procedures_format():
    """Update procedures.json to new provider format with version_id."""
    procedures = read('procedures.json')
    changed = 0
    for p in procedures:
        if 'identifiers' not in p:
            p['identifiers'] = p.pop('test_list', [])
            changed += 1
        if 'version_id' not in p:
            p['version_id'] = ''
            changed += 1
    write('procedures.json', procedures)
    print(f'  Updated {changed} procedures to new format')
```

- [ ] **Step 2: 마이그레이션 실행**

```bash
source venv/bin/activate
python3 -c "exec(open('migrate_data.py').read()); add_source_fields(); update_procedures_format()"
```

- [ ] **Step 3: 전체 테스트**

Run: `pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 4: ��밋**

```bash
git add data/ migrate_data.py
git commit -m "chore: 데이터 마이그레이션 — source/external_key, procedures 포맷"
```

---

### Task 6: UI 변경 — 외부 데이터 읽기 전용

**Files:**
- Modify: `schedule/templates/tasks/form.html`
- Modify: `schedule/templates/tasks/list.html`
- Modify: `schedule/templates/admin/versions.html`

- [ ] **Step 1: tasks/list.html — "외부" 뱃지 추가**

장절명 셀에서, task.source == 'external'이면 "외부" 뱃지:

```html
<td class="task-cell-title fw-bold">
  {{ task.section_name or '-' }}
  {% if task.get('source') == 'external' %}
  <span class="badge bg-info" style="font-size:0.6rem;vertical-align:middle">외부</span>
  {% endif %}
</td>
```

- [ ] **Step 2: tasks/form.html — 외부 데이터 읽기 전용**

장절명 input에 조건 추가:
```html
<input type="text" class="form-control" name="section_name" id="section_name"
       value="{{ task.section_name if task else '' }}"
       {% if task and task.get('source') == 'external' %}readonly{% endif %}
       placeholder="예: 3.1 ��스템 초기화" required>
```

식별자 테이블 JS에서, task.source == 'external'이면 추가/삭제/수정 비활성화:
```javascript
var isExternal = {{ 'true' if task and task.get('source') == 'external' else 'false' }};
```
식별자 행의 input들에 `readonly` 추가, 삭제/추가 버튼 숨김.

- [ ] **Step 3: admin/versions.html — 동기화 버튼 추가**

버전 목록 페이지 상단에 동기화 버튼:
```html
<button class="btn btn-sm btn-outline-primary" id="btn-sync-versions">
  <i class="bi bi-arrow-repeat"></i> 외부 동��화
</button>
```

JS:
```javascript
document.getElementById('btn-sync-versions').addEventListener('click', function() {
  fetch('/api/sync/versions', {method: 'POST'})
    .then(r => r.json())
    .then(data => {
      alert('동기화 완료: 추가 ' + data.added + ', 업데이트 ' + data.updated + ', 비활성화 ' + data.deactivated);
      location.reload();
    });
});
```

- [ ] **Step 4: 전체 테스트**

Run: `pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add schedule/templates/
git commit -m "feat: UI 변경 — 외부 데이터 읽기 전용, 동기화 버튼, 외부 뱃지"
```

---

### Task 7: 최종 검증

- [ ] **Step 1: 전체 테스트**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: 서버 구동 검증**

Run: `python3 run.py`
- http://localhost:5001/schedule/week 접속
- http://localhost:5001/tasks/ 접속 — 외부 뱃지 확인
- http://localhost:5001/admin/versions — 동기화 버튼 확인

- [ ] **Step 3: 동기화 API 테스트**

```bash
curl -X POST http://localhost:5001/api/sync/versions
curl -X POST http://localhost:5001/api/sync/test-data
curl http://localhost:5001/api/sync/status
```

- [ ] **Step 4: 최종 커밋**

```bash
git add -A
git commit -m "feat: 외부 데이터 통합 완료 — Provider 추상화, 동기화 서비스"
```
