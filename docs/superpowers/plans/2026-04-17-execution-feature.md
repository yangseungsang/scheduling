# 시험실행 페이지 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/execution/` 페이지에서 시험자가 식별자 단위로 시험을 수행하고 서버사이드 타이머로 시간을 기록할 수 있는 기능 구현

**Architecture:** `app/features/execution/` 독립 feature로 분리. schedule feature의 모델을 읽기 전용으로 참조. 자체 `store.py`로 별도 데이터 디렉토리 사용. `EXECUTION_DATA_DIR` Flask config 키로 테스트 격리.

**Tech Stack:** Flask Blueprint, JSON 파일 저장소, Bootstrap 5 모달, Vanilla JS (fetch API, setInterval)

---

## 파일 맵

| 파일 | 역할 |
|------|------|
| `app/features/execution/__init__.py` | register_blueprints 진입점 |
| `app/features/execution/store.py` | EXECUTION_DATA_DIR 기반 read/write JSON |
| `app/features/execution/data/executions.json` | 실행 기록 초기 빈 파일 |
| `app/features/execution/models/execution.py` | ExecutionRepository (start/pause/resume/complete/reset) |
| `app/features/execution/routes/__init__.py` | execution_bp, api_bp 등록 |
| `app/features/execution/routes/views.py` | GET /execution/ HTML 라우트 |
| `app/features/execution/routes/api.py` | REST API (list, start, pause, resume, complete, reset, total-count) |
| `app/templates/execution/index.html` | 시험실행 메인 페이지 |
| `app/static/execution/js/execution-app.js` | 타이머, 모달, 리스트 렌더링 |
| `app/__init__.py` | EXECUTION_DATA_DIR config + blueprint 등록 수정 |
| `app/templates/schedule/base.html` | 시험실행 nav 탭 추가 |
| `tests/conftest.py` | EXECUTION_DATA_DIR tmp 설정 |
| `tests/test_execution.py` | 신규 테스트 파일 |

---

## Task 1: store.py + 데이터 디렉토리 + 앱 설정

**Files:**
- Create: `app/features/execution/store.py`
- Create: `app/features/execution/data/executions.json`
- Modify: `app/__init__.py`

- [ ] **Step 1: executions.json 초기 파일 생성**

```bash
mkdir -p /home/yangsm/Projects/scheduling/app/features/execution/data
echo '[]' > /home/yangsm/Projects/scheduling/app/features/execution/data/executions.json
```

- [ ] **Step 2: store.py 작성**

`app/features/execution/store.py`:

```python
import json
import os
import shutil
import uuid

import portalocker


def generate_id(prefix):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _get_path(filename):
    from flask import current_app
    return os.path.join(current_app.config['EXECUTION_DATA_DIR'], filename)


def read_json(filename):
    path = _get_path(filename)
    if not os.path.exists(path):
        return []
    with portalocker.Lock(path, 'r', timeout=5) as f:
        content = f.read()
        if not content.strip():
            return []
        return json.loads(content)


def write_json(filename, data):
    path = _get_path(filename)
    if os.path.exists(path):
        shutil.copy2(path, path + '.bak')
    with portalocker.Lock(path, 'w', timeout=5) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 3: app/__init__.py에 EXECUTION_DATA_DIR 추가**

현재 `app/__init__.py`의 `DATA_DIR` 정의 아래에 추가:

```python
EXECUTION_DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'features', 'execution', 'data'
)
```

`create_app()` 함수 안, `app.config['DATA_DIR'] = DATA_DIR` 아래에 추가:

```python
app.config['EXECUTION_DATA_DIR'] = EXECUTION_DATA_DIR
os.makedirs(app.config['EXECUTION_DATA_DIR'], exist_ok=True)
```

- [ ] **Step 4: 커밋**

```bash
git add app/features/execution/data/executions.json app/features/execution/store.py app/__init__.py
git commit -m "feat(execution): store.py + EXECUTION_DATA_DIR config"
```

---

## Task 2: ExecutionRepository 모델

**Files:**
- Create: `app/features/execution/models/__init__.py`
- Create: `app/features/execution/models/execution.py`
- Create: `tests/test_execution.py`

- [ ] **Step 1: 테스트 파일 작성 (failing)**

`tests/test_execution.py`:

```python
import json
import os
import pytest
from app import create_app


@pytest.fixture
def exec_app(tmp_path):
    data_dir = str(tmp_path / 'data')
    exec_dir = str(tmp_path / 'exec_data')
    os.makedirs(data_dir)
    os.makedirs(exec_dir)

    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions', 'procedures'):
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
    with open(os.path.join(exec_dir, 'executions.json'), 'w') as f:
        json.dump([], f)

    app = create_app()
    app.config['DATA_DIR'] = data_dir
    app.config['EXECUTION_DATA_DIR'] = exec_dir
    app.config['TESTING'] = True
    yield app


@pytest.fixture
def exec_client(exec_app):
    return exec_app.test_client()


class TestExecutionRepository:
    def test_start_creates_record(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-001', 't_001', total_count=5)
            assert ex['identifier_id'] == 'TC-001'
            assert ex['status'] == 'in_progress'
            assert len(ex['segments']) == 1
            assert ex['segments'][0]['end'] is None
            assert ex['total_count'] == 5

    def test_pause_closes_segment(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-002', 't_001', total_count=5)
            paused = ExecutionRepository.pause(ex['id'])
            assert paused['status'] == 'paused'
            assert paused['segments'][0]['end'] is not None

    def test_resume_adds_segment(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-003', 't_001', total_count=5)
            paused = ExecutionRepository.pause(ex['id'])
            resumed = ExecutionRepository.resume(paused['id'])
            assert resumed['status'] == 'in_progress'
            assert len(resumed['segments']) == 2
            assert resumed['segments'][1]['end'] is None

    def test_complete_saves_result(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-004', 't_001', total_count=8)
            done = ExecutionRepository.complete(ex['id'], fail_count=2)
            assert done['status'] == 'completed'
            assert done['fail_count'] == 2
            assert done['pass_count'] == 6
            assert done['completed_at'] is not None
            assert done['segments'][0]['end'] is not None

    def test_reset_clears_record(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            ex = ExecutionRepository.start('TC-005', 't_001', total_count=5)
            ExecutionRepository.complete(ex['id'], fail_count=1)
            reset = ExecutionRepository.reset(ex['id'])
            assert reset['status'] == 'pending'
            assert reset['segments'] == []
            assert reset['fail_count'] == 0
            assert reset['completed_at'] is None

    def test_compute_elapsed_seconds(self, exec_app):
        with exec_app.app_context():
            from app.features.execution.models.execution import ExecutionRepository
            segments = [
                {'start': '2026-04-17T09:00:00', 'end': '2026-04-17T09:30:00'},
                {'start': '2026-04-17T10:00:00', 'end': '2026-04-17T10:15:00'},
            ]
            assert ExecutionRepository.compute_elapsed_seconds(segments) == 2700


class TestExecutionAPI:
    def test_start(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['status'] == 'in_progress'

    def test_pause(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        ex_id = r.get_json()['id']
        r2 = exec_client.post('/execution/api/pause', json={'execution_id': ex_id})
        assert r2.status_code == 200
        assert r2.get_json()['status'] == 'paused'

    def test_resume(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        ex_id = r.get_json()['id']
        exec_client.post('/execution/api/pause', json={'execution_id': ex_id})
        r3 = exec_client.post('/execution/api/resume', json={'execution_id': ex_id})
        assert r3.status_code == 200
        assert r3.get_json()['status'] == 'in_progress'

    def test_complete(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        ex_id = r.get_json()['id']
        r2 = exec_client.post('/execution/api/complete', json={
            'execution_id': ex_id, 'fail_count': 3
        })
        assert r2.status_code == 200
        data = r2.get_json()
        assert data['status'] == 'completed'
        assert data['fail_count'] == 3

    def test_reset(self, exec_client):
        r = exec_client.post('/execution/api/start', json={
            'identifier_id': 'TC-001', 'task_id': 't_001'
        })
        ex_id = r.get_json()['id']
        exec_client.post('/execution/api/complete', json={
            'execution_id': ex_id, 'fail_count': 1
        })
        r2 = exec_client.post('/execution/api/reset', json={'execution_id': ex_id})
        assert r2.status_code == 200
        assert r2.get_json()['status'] == 'pending'

    def test_list(self, exec_client):
        r = exec_client.get('/execution/api/list')
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_total_count(self, exec_client):
        r = exec_client.get('/execution/api/total-count/TC-001')
        assert r.status_code == 200
        assert 'total_count' in r.get_json()

    def test_execution_page(self, exec_client):
        r = exec_client.get('/execution/')
        assert r.status_code == 200
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd /home/yangsm/Projects/scheduling
python -m pytest tests/test_execution.py -x -q 2>&1 | head -20
```

Expected: ImportError 또는 404 에러

- [ ] **Step 3: models/__init__.py 생성**

`app/features/execution/models/__init__.py`:

```python
```

(빈 파일)

- [ ] **Step 4: execution.py 작성**

`app/features/execution/models/execution.py`:

```python
from datetime import datetime

from app.features.execution.store import read_json, write_json, generate_id

FILENAME = 'executions.json'
ID_PREFIX = 'ex_'


class ExecutionRepository:

    @classmethod
    def get_all(cls):
        return read_json(FILENAME)

    @classmethod
    def get_by_id(cls, execution_id):
        for item in read_json(FILENAME):
            if item['id'] == execution_id:
                return item
        return None

    @classmethod
    def get_by_identifier(cls, identifier_id):
        for item in read_json(FILENAME):
            if item['identifier_id'] == identifier_id:
                return item
        return None

    @staticmethod
    def compute_elapsed_seconds(segments):
        total = 0
        now = datetime.now()
        for seg in segments:
            start = datetime.fromisoformat(seg['start'])
            end = datetime.fromisoformat(seg['end']) if seg['end'] else now
            total += int((end - start).total_seconds())
        return max(0, total)

    @classmethod
    def _patch(cls, execution_id, **kwargs):
        items = read_json(FILENAME)
        for item in items:
            if item['id'] == execution_id:
                item.update(kwargs)
                write_json(FILENAME, items)
                return item
        return None

    @classmethod
    def start(cls, identifier_id, task_id, total_count=10):
        now = datetime.now().isoformat(timespec='seconds')
        existing = cls.get_by_identifier(identifier_id)
        if existing:
            return cls._patch(
                existing['id'],
                status='in_progress',
                segments=[{'start': now, 'end': None}],
                fail_count=0,
                pass_count=0,
                total_count=total_count,
                completed_at=None,
            )
        data = {
            'id': generate_id(ID_PREFIX),
            'identifier_id': identifier_id,
            'task_id': task_id,
            'status': 'in_progress',
            'segments': [{'start': now, 'end': None}],
            'total_count': total_count,
            'fail_count': 0,
            'pass_count': 0,
            'created_at': now,
            'completed_at': None,
        }
        items = read_json(FILENAME)
        items.append(data)
        write_json(FILENAME, items)
        return data

    @classmethod
    def pause(cls, execution_id):
        ex = cls.get_by_id(execution_id)
        if not ex or ex['status'] != 'in_progress':
            return None
        now = datetime.now().isoformat(timespec='seconds')
        segments = ex['segments']
        if segments and segments[-1]['end'] is None:
            segments[-1]['end'] = now
        return cls._patch(execution_id, status='paused', segments=segments)

    @classmethod
    def resume(cls, execution_id):
        ex = cls.get_by_id(execution_id)
        if not ex or ex['status'] != 'paused':
            return None
        now = datetime.now().isoformat(timespec='seconds')
        segments = ex['segments'] + [{'start': now, 'end': None}]
        return cls._patch(execution_id, status='in_progress', segments=segments)

    @classmethod
    def complete(cls, execution_id, fail_count):
        ex = cls.get_by_id(execution_id)
        if not ex:
            return None
        now = datetime.now().isoformat(timespec='seconds')
        segments = ex['segments']
        if segments and segments[-1]['end'] is None:
            segments[-1]['end'] = now
        total_count = ex.get('total_count', 0)
        pass_count = max(0, total_count - int(fail_count))
        return cls._patch(
            execution_id,
            status='completed',
            segments=segments,
            fail_count=int(fail_count),
            pass_count=pass_count,
            completed_at=now,
        )

    @classmethod
    def reset(cls, execution_id):
        return cls._patch(
            execution_id,
            status='pending',
            segments=[],
            fail_count=0,
            pass_count=0,
            completed_at=None,
        )
```

- [ ] **Step 5: 모델 테스트만 실행 — 통과 확인**

```bash
cd /home/yangsm/Projects/scheduling
python -m pytest tests/test_execution.py::TestExecutionRepository -x -q 2>&1 | tail -10
```

Expected: 6 passed (API 테스트는 아직 실패)

- [ ] **Step 6: 커밋**

```bash
git add app/features/execution/models/ tests/test_execution.py
git commit -m "feat(execution): ExecutionRepository 모델 + 테스트"
```

---

## Task 3: API 라우트 + 뷰 라우트 + Blueprint 등록

**Files:**
- Create: `app/features/execution/routes/__init__.py`
- Create: `app/features/execution/routes/views.py`
- Create: `app/features/execution/routes/api.py`
- Create: `app/features/execution/__init__.py`
- Modify: `app/__init__.py`

- [ ] **Step 1: mock total_count 함수 — 나중에 외부 API 교체 포인트**

`app/features/execution/routes/api.py` (전체 내용):

```python
from flask import Blueprint, jsonify, request

from app.features.execution.models.execution import ExecutionRepository

api_bp = Blueprint('execution_api', __name__, url_prefix='/execution/api')


def _get_total_count(identifier_id: str) -> int:
    # TODO: 실제 외부 API 연동
    return 10


def _execution_response(ex):
    if ex is None:
        return None
    return {
        'id': ex['id'],
        'status': ex['status'],
        'elapsed_seconds': ExecutionRepository.compute_elapsed_seconds(ex['segments']),
        'total_count': ex.get('total_count', 0),
        'fail_count': ex.get('fail_count', 0),
        'pass_count': ex.get('pass_count', 0),
    }


@api_bp.route('/list')
def execution_list():
    from app.features.schedule.models import task as task_repo
    from app.features.schedule.models import schedule_block as block_repo
    from app.features.schedule.models import location as loc_repo

    date_filter = request.args.get('date', '')
    location_filter = request.args.get('location', '')

    tasks = task_repo.get_all()
    blocks = block_repo.get_all()
    locations = {loc['id']: loc for loc in loc_repo.get_all()}

    # 식별자 → 가장 이른 배치 날짜 매핑
    date_map = {}
    for block in blocks:
        block_date = block.get('date', '')
        block_task_id = block.get('task_id', '')
        block_iids = block.get('identifier_ids')
        task = next((t for t in tasks if t['id'] == block_task_id), None)
        if not task:
            continue
        for identifier in task.get('identifiers', []):
            iid = identifier['id'] if isinstance(identifier, dict) else identifier
            if block_iids is None or iid in block_iids:
                if iid not in date_map or block_date < date_map[iid]:
                    date_map[iid] = block_date

    result = []
    for task in tasks:
        loc_id = task.get('location_id', '')
        loc_name = locations.get(loc_id, {}).get('name', '') if loc_id else ''

        for identifier in task.get('identifiers', []):
            if not isinstance(identifier, dict):
                continue
            iid = identifier['id']
            scheduled_date = date_map.get(iid, '')

            if date_filter and scheduled_date != date_filter:
                continue
            if location_filter and loc_id != location_filter:
                continue

            execution = ExecutionRepository.get_by_identifier(iid)
            result.append({
                'identifier_id': iid,
                'identifier_name': identifier.get('name', ''),
                'task_id': task['id'],
                'doc_name': task.get('doc_name', ''),
                'location_id': loc_id,
                'location_name': loc_name,
                'scheduled_date': scheduled_date,
                'execution': _execution_response(execution),
            })

    return jsonify(result)


@api_bp.route('/total-count/<identifier_id>')
def total_count(identifier_id):
    return jsonify({'total_count': _get_total_count(identifier_id)})


@api_bp.route('/start', methods=['POST'])
def start():
    body = request.get_json(silent=True) or {}
    identifier_id = body.get('identifier_id', '').strip()
    task_id = body.get('task_id', '').strip()
    if not identifier_id or not task_id:
        return jsonify({'error': 'identifier_id and task_id required'}), 400
    total_count = _get_total_count(identifier_id)
    ex = ExecutionRepository.start(identifier_id, task_id, total_count=total_count)
    return jsonify(ex), 201


@api_bp.route('/pause', methods=['POST'])
def pause():
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.pause(execution_id)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404
    return jsonify(ex)


@api_bp.route('/resume', methods=['POST'])
def resume():
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.resume(execution_id)
    if ex is None:
        return jsonify({'error': 'not found or invalid state'}), 404
    return jsonify(ex)


@api_bp.route('/complete', methods=['POST'])
def complete():
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    fail_count = body.get('fail_count', 0)
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.complete(execution_id, fail_count)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(ex)


@api_bp.route('/reset', methods=['POST'])
def reset():
    body = request.get_json(silent=True) or {}
    execution_id = body.get('execution_id', '').strip()
    if not execution_id:
        return jsonify({'error': 'execution_id required'}), 400
    ex = ExecutionRepository.reset(execution_id)
    if ex is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(ex)
```

- [ ] **Step 2: views.py 작성**

`app/features/execution/routes/views.py`:

```python
from flask import Blueprint, render_template

from app.features.schedule.models import location as loc_repo
from app.features.schedule.models import schedule_block as block_repo

views_bp = Blueprint('execution', __name__, url_prefix='/execution')


@views_bp.route('/')
def index():
    locations = loc_repo.get_all()
    blocks = block_repo.get_all()
    dates = sorted({b['date'] for b in blocks if b.get('date')})
    return render_template('execution/index.html',
                           locations=locations,
                           dates=dates)
```

- [ ] **Step 3: routes/__init__.py 작성**

`app/features/execution/routes/__init__.py`:

```python
from app.features.execution.routes.views import views_bp
from app.features.execution.routes.api import api_bp


def register_execution_routes(app):
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)
```

- [ ] **Step 4: feature __init__.py 작성**

`app/features/execution/__init__.py`:

```python
from app.features.execution.routes import register_execution_routes


def register_blueprints(app):
    register_execution_routes(app)
```

- [ ] **Step 5: app/__init__.py에 execution blueprint 등록**

`create_app()` 함수 내 `register_schedule(app)` 아래에 추가:

```python
from app.features.execution import register_blueprints as register_execution
register_execution(app)
```

- [ ] **Step 6: API 테스트 실행 — 통과 확인**

```bash
cd /home/yangsm/Projects/scheduling
python -m pytest tests/test_execution.py -x -q 2>&1 | tail -15
```

Expected: execution_page 제외 모두 pass (index.html 아직 없음)

- [ ] **Step 7: 커밋**

```bash
git add app/features/execution/ app/__init__.py tests/test_execution.py
git commit -m "feat(execution): API 라우트 + Blueprint 등록"
```

---

## Task 4: 템플릿 + nav 탭

**Files:**
- Create: `app/templates/execution/index.html`
- Modify: `app/templates/schedule/base.html`

- [ ] **Step 1: execution/index.html 작성**

`app/templates/execution/index.html`:

```html
{% extends "schedule/base.html" %}
{% block title %}시험 실행{% endblock %}

{% block content %}
<div class="container-fluid py-3">
  <div class="d-flex align-items-center gap-3 mb-3">
    <h4 class="mb-0">시험 실행</h4>
  </div>

  <!-- 필터 바 -->
  <div class="d-flex gap-2 mb-3">
    <select id="filter-date" class="form-select form-select-sm" style="width:auto">
      <option value="">전체 날짜</option>
      {% for d in dates %}
      <option value="{{ d }}">{{ d }}</option>
      {% endfor %}
    </select>
    <select id="filter-location" class="form-select form-select-sm" style="width:auto">
      <option value="">전체 장소</option>
      {% for loc in locations %}
      <option value="{{ loc.id }}">{{ loc.name }}</option>
      {% endfor %}
    </select>
    <button class="btn btn-sm btn-outline-secondary" onclick="loadList()">
      <i class="bi bi-arrow-clockwise"></i> 새로고침
    </button>
  </div>

  <!-- 식별자 목록 테이블 -->
  <div class="table-responsive">
    <table class="table table-hover table-sm align-middle" id="exec-table">
      <thead class="table-light">
        <tr>
          <th style="width:100px">TC</th>
          <th>식별자명</th>
          <th style="width:140px">문서</th>
          <th style="width:90px">장소</th>
          <th style="width:90px">날짜</th>
          <th style="width:130px">상태</th>
        </tr>
      </thead>
      <tbody id="exec-tbody">
        <tr><td colspan="6" class="text-center text-muted py-4">로딩 중...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<!-- 실행 모달 -->
<div class="modal fade" id="execModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="execModalTitle">시험 실행</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body" id="execModalBody">
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block head %}
<script src="{{ url_for('static', filename='execution/js/execution-app.js') }}?v={{ cache_bust }}" defer></script>
{% endblock %}
```

- [ ] **Step 2: schedule/base.html에 시험 실행 탭 추가**

`app/templates/schedule/base.html`에서 `시험 항목` 탭 아래에 추가:

```html
        <a href="{{ url_for('execution.index') }}" class="toolbar-tab">
          <i class="bi bi-play-circle"></i> 시험 실행
        </a>
```

- [ ] **Step 3: 전체 테스트 실행 — 통과 확인**

```bash
cd /home/yangsm/Projects/scheduling
python -m pytest tests/test_execution.py -x -q 2>&1 | tail -10
```

Expected: 모두 pass (JS 없어도 HTML 페이지는 200 반환)

- [ ] **Step 4: 기존 테스트 회귀 확인**

```bash
cd /home/yangsm/Projects/scheduling
python -m pytest tests/ -q --ignore=tests/test_execution.py 2>&1 | tail -10
```

Expected: 기존 테스트 모두 pass

- [ ] **Step 5: 커밋**

```bash
git add app/templates/execution/ app/templates/schedule/base.html
git commit -m "feat(execution): index.html 템플릿 + nav 탭 추가"
```

---

## Task 5: 프론트엔드 JS (execution-app.js)

**Files:**
- Create: `app/static/execution/js/execution-app.js`

- [ ] **Step 1: 디렉토리 생성**

```bash
mkdir -p /home/yangsm/Projects/scheduling/app/static/execution/js
```

- [ ] **Step 2: execution-app.js 작성**

`app/static/execution/js/execution-app.js`:

```javascript
'use strict';

// 현재 열린 모달의 실행 데이터
let _currentItem = null;
// 타이머 인터벌 ID
let _timerInterval = null;
// 마지막 서버 elapsed_seconds + 로컬 시작 시각
let _localTimerBase = 0;
let _localTimerStart = null;

// ── 유틸 ──────────────────────────────────────────────────────────────────

function formatElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

async function apiFetch(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}

// ── 리스트 ────────────────────────────────────────────────────────────────

async function loadList() {
  const date = document.getElementById('filter-date').value;
  const loc = document.getElementById('filter-location').value;
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (loc) params.set('location', loc);

  const tbody = document.getElementById('exec-tbody');
  tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">로딩 중...</td></tr>';

  try {
    const items = await apiFetch('/execution/api/list?' + params.toString());
    renderTable(items);
  } catch {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">로드 실패</td></tr>';
  }
}

function statusBadge(item) {
  const ex = item.execution;
  if (!ex) return '<span class="badge bg-secondary">○ 대기</span>';
  switch (ex.status) {
    case 'in_progress':
      return `<span class="badge bg-primary">🔵 진행 ${formatElapsed(ex.elapsed_seconds)}</span>`;
    case 'paused':
      return `<span class="badge bg-warning text-dark">⏸ 일시정지 ${formatElapsed(ex.elapsed_seconds)}</span>`;
    case 'completed':
      return `<span class="badge bg-success">✅ 완료</span>`;
    case 'pending':
      return '<span class="badge bg-secondary">○ 대기</span>';
    default:
      return '<span class="badge bg-secondary">-</span>';
  }
}

function renderTable(items) {
  const tbody = document.getElementById('exec-tbody');
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">항목 없음</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(item => `
    <tr data-id="${item.identifier_id}" data-item='${JSON.stringify(item).replace(/'/g, "&#39;")}' style="cursor:pointer">
      <td><code>${item.identifier_id}</code></td>
      <td>${item.identifier_name}</td>
      <td class="text-muted small">${item.doc_name}</td>
      <td class="text-muted small">${item.location_name || '-'}</td>
      <td class="text-muted small">${item.scheduled_date || '-'}</td>
      <td>${statusBadge(item)}</td>
    </tr>
  `).join('');

  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('dblclick', () => {
      const item = JSON.parse(tr.dataset.item);
      openModal(item);
    });
  });
}

// ── 모달 ──────────────────────────────────────────────────────────────────

function openModal(item) {
  _currentItem = item;
  document.getElementById('execModalTitle').textContent =
    `${item.identifier_id} — ${item.identifier_name}`;
  renderModalBody(item);
  new bootstrap.Modal(document.getElementById('execModal')).show();
  startLocalTimer(item);
}

function startLocalTimer(item) {
  stopLocalTimer();
  const ex = item.execution;
  if (!ex || ex.status !== 'in_progress') return;
  _localTimerBase = ex.elapsed_seconds;
  _localTimerStart = Date.now();
  _timerInterval = setInterval(() => {
    const elapsed = _localTimerBase + Math.floor((Date.now() - _localTimerStart) / 1000);
    const el = document.getElementById('timer-display');
    if (el) el.textContent = formatElapsed(elapsed);
  }, 1000);
}

function stopLocalTimer() {
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
  _localTimerBase = 0;
  _localTimerStart = null;
}

function renderModalBody(item) {
  const ex = item.execution;
  const status = ex ? ex.status : 'pending';
  const body = document.getElementById('execModalBody');

  if (status === 'pending' || !ex) {
    body.innerHTML = `
      <div class="text-center py-3">
        <button class="btn btn-success btn-lg" onclick="doStart()">
          <i class="bi bi-play-fill"></i> 시험시작
        </button>
      </div>`;
    return;
  }

  const elapsed = ex.elapsed_seconds;
  const total = ex.total_count;
  const fail = ex.fail_count;
  const pass = ex.pass_count;

  if (status === 'completed') {
    body.innerHTML = `
      <div class="text-center mb-3">
        <span class="fs-5">✅ 완료 &nbsp; 총 ${formatElapsed(elapsed)}</span>
      </div>
      <div class="text-center mb-3">
        PASS: <strong>${pass}</strong> &nbsp;&nbsp; FAIL: <strong>${fail}</strong> &nbsp;&nbsp; (총 ${total}건)
      </div>
      <div class="d-flex justify-content-between">
        <button class="btn btn-outline-secondary btn-sm" onclick="doReset()">재시험</button>
        <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">닫기</button>
      </div>`;
    return;
  }

  // in_progress or paused
  const timerHtml = status === 'in_progress'
    ? `<span id="timer-display" class="fs-3 font-monospace">${formatElapsed(elapsed)}</span>
       <button class="btn btn-warning ms-3" onclick="doPause()"><i class="bi bi-pause-fill"></i> 일시정지</button>`
    : `<span id="timer-display" class="fs-3 font-monospace text-muted">${formatElapsed(elapsed)}</span>
       <button class="btn btn-success ms-3" onclick="doResume()"><i class="bi bi-play-fill"></i> 재시작</button>`;

  body.innerHTML = `
    <div class="d-flex align-items-center mb-3">
      ${status === 'in_progress' ? '⏱' : '⏸'} &nbsp; ${timerHtml}
    </div>
    <div class="mb-3">
      <label class="form-label">총 시험: <strong>${total}건</strong></label>
      <div class="d-flex align-items-center gap-2">
        <label class="form-label mb-0">FAIL</label>
        <input type="number" id="fail-input" class="form-control form-control-sm" style="width:80px"
               min="0" max="${total}" value="${fail}" oninput="updatePass()">
        <span class="text-muted">→ PASS:</span>
        <strong id="pass-display">${pass}</strong>
        <span class="text-muted">(자동계산)</span>
      </div>
    </div>
    <div class="d-flex justify-content-between">
      <button class="btn btn-outline-secondary btn-sm" onclick="doReset()">재시험</button>
      <button class="btn btn-primary" onclick="doComplete()">
        <i class="bi bi-check-lg"></i> 시험완료
      </button>
    </div>`;
}

function updatePass() {
  if (!_currentItem || !_currentItem.execution) return;
  const total = _currentItem.execution.total_count;
  const fail = parseInt(document.getElementById('fail-input').value) || 0;
  document.getElementById('pass-display').textContent = Math.max(0, total - fail);
}

// ── 액션 핸들러 ───────────────────────────────────────────────────────────

async function doStart() {
  try {
    const ex = await apiFetch('/execution/api/start', 'POST', {
      identifier_id: _currentItem.identifier_id,
      task_id: _currentItem.task_id,
    });
    _currentItem.execution = {
      id: ex.id,
      status: ex.status,
      elapsed_seconds: 0,
      total_count: ex.total_count,
      fail_count: 0,
      pass_count: 0,
    };
    renderModalBody(_currentItem);
    startLocalTimer(_currentItem);
    await loadList();
  } catch { alert('시험시작 실패'); }
}

async function doPause() {
  try {
    const ex = await apiFetch('/execution/api/pause', 'POST', {
      execution_id: _currentItem.execution.id,
    });
    stopLocalTimer();
    _currentItem.execution = { ..._currentItem.execution, status: 'paused',
      elapsed_seconds: ExecutionRepository_computeElapsed(ex) };
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('일시정지 실패'); }
}

async function doResume() {
  try {
    const ex = await apiFetch('/execution/api/resume', 'POST', {
      execution_id: _currentItem.execution.id,
    });
    _currentItem.execution.status = 'in_progress';
    renderModalBody(_currentItem);
    startLocalTimer(_currentItem);
    await loadList();
  } catch { alert('재시작 실패'); }
}

async function doComplete() {
  const failInput = document.getElementById('fail-input');
  const failCount = parseInt(failInput ? failInput.value : 0) || 0;
  try {
    const ex = await apiFetch('/execution/api/complete', 'POST', {
      execution_id: _currentItem.execution.id,
      fail_count: failCount,
    });
    stopLocalTimer();
    const total = _currentItem.execution.total_count;
    _currentItem.execution = {
      ..._currentItem.execution,
      status: 'completed',
      fail_count: ex.fail_count,
      pass_count: ex.pass_count,
      elapsed_seconds: ExecutionRepository_computeElapsed(ex),
    };
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('완료 처리 실패'); }
}

async function doReset() {
  if (!confirm('재시험하면 현재 기록이 초기화됩니다. 계속할까요?')) return;
  try {
    await apiFetch('/execution/api/reset', 'POST', {
      execution_id: _currentItem.execution.id,
    });
    stopLocalTimer();
    _currentItem.execution = null;
    renderModalBody(_currentItem);
    await loadList();
  } catch { alert('재시험 처리 실패'); }
}

// 서버 응답 ex에서 elapsed_seconds 계산 (segments 기반)
function ExecutionRepository_computeElapsed(ex) {
  let total = 0;
  const now = new Date();
  for (const seg of (ex.segments || [])) {
    const start = new Date(seg.start);
    const end = seg.end ? new Date(seg.end) : now;
    total += Math.floor((end - start) / 1000);
  }
  return Math.max(0, total);
}

// ── 모달 닫힐 때 타이머 정지 ──────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('execModal').addEventListener('hidden.bs.modal', stopLocalTimer);

  document.getElementById('filter-date').addEventListener('change', loadList);
  document.getElementById('filter-location').addEventListener('change', loadList);

  loadList();
});
```

- [ ] **Step 3: 서버 실행 후 브라우저 확인**

```bash
cd /home/yangsm/Projects/scheduling
FLASK_APP=run.py python -m flask run --port 5000
```

브라우저에서 `http://localhost:5000/execution/` 접속 확인:
- 리스트 테이블 표시됨
- 더블클릭 시 모달 오픈됨
- 시험시작 → 타이머 동작 확인
- 일시정지 → 재시작 → 시험완료 플로우 확인

- [ ] **Step 4: 전체 테스트 실행**

```bash
cd /home/yangsm/Projects/scheduling
python -m pytest tests/ -q 2>&1 | tail -15
```

Expected: 모든 테스트 pass

- [ ] **Step 5: conftest.py에 EXECUTION_DATA_DIR 추가**

`tests/conftest.py`의 `app` fixture에서 `executions.json` 초기화 및 `EXECUTION_DATA_DIR` 설정 추가:

```python
@pytest.fixture
def app(tmp_path):
    data_dir = str(tmp_path / 'data')
    exec_dir = str(tmp_path / 'exec_data')
    os.makedirs(data_dir)
    os.makedirs(exec_dir)

    for name in ('users', 'locations', 'tasks', 'schedule_blocks', 'versions', 'procedures'):
        with open(os.path.join(data_dir, f'{name}.json'), 'w') as f:
            json.dump([], f)
    with open(os.path.join(exec_dir, 'executions.json'), 'w') as f:
        json.dump([], f)

    with open(os.path.join(data_dir, 'settings.json'), 'w') as f:
        json.dump({
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
        }, f)

    application = create_app()
    application.config['DATA_DIR'] = data_dir
    application.config['EXECUTION_DATA_DIR'] = exec_dir
    application.config['TESTING'] = True
    yield application
```

- [ ] **Step 6: 최종 전체 테스트 실행**

```bash
cd /home/yangsm/Projects/scheduling
python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: 모든 테스트 pass

- [ ] **Step 7: 최종 커밋**

```bash
git add app/static/execution/ tests/conftest.py
git commit -m "feat(execution): 프론트엔드 JS + conftest 업데이트"
```

---

## Task 6: GitHub Issue 클로즈

- [ ] **Step 1: PR 생성 또는 이슈 클로즈**

```bash
gh issue close 35 --comment "시험실행 페이지 구현 완료 (PR: /execution/ 라우트, 서버사이드 타이머, PASS/FAIL 자동계산, 날짜/장소 필터)"
```
