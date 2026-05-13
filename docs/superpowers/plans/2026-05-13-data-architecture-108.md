# Data Architecture Improvement Implementation Plan (#108)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** execution 데이터가 schedule 데이터에 쓰여지는 순환 흐름(write-back)을 제거하고, 상태 정보를 한 곳(executions.json)에서만 관리한다.

**Architecture:** 현재 `execution.complete()` → `_sync_block_status()` → `sync_task_status()` → `task.status` 기록이라는 순환 경로를 끊는다. `task.status` 필드를 삭제하고, block_status 자동 동기화를 제거한다. 상태는 필요할 때 executions 데이터에서 동적으로 계산한다.

**Tech Stack:** Python/Flask, Jinja2, JSON file storage, pytest

---

## 현재 순환 경로 (제거 대상)

```
execution.complete/start/cancel
    → _sync_block_status()       # execution_api.py — 실제로는 dead code (라우터 미등록)
    → schedule_blocks.block_status 갱신

POST /api/blocks/<id>/status
    → sync_task_status(task_id)   # calendar_helpers.py — ACTIVE 순환
    → tasks.task.status 갱신     ← 이것이 진짜 문제
```

## 남길 것

- `block.block_status` — 사용자가 수동으로 설정 가능 (자동 동기화만 제거)
- `task.status = 'cancelled'` — sync 서비스가 외부 API에서 사라진 태스크 표시 (정당한 단방향 흐름)
- enrichment.py의 `block_status` 시각적 표시

## 제거할 것

- `task.status` 필드 ('waiting'/'in_progress'/'completed' 값만 해당, 'cancelled' 유지)
- `sync_task_status()` 함수 전체 — calendar_helpers.py
- `sync_task_status()` 호출부 — calendar_api.py:420
- `_sync_block_status()` 함수 — execution_api.py (이미 dead code, 삭제만)
- `task.status` 쓰기: task.py create/update, tasks.py form/api

---

## 핵심 파일 경로

```
app/features/schedule/routes/calendar_helpers.py   # sync_task_status 삭제 (130–160줄)
app/features/schedule/routes/calendar_api.py       # import + 호출 제거 (25줄, 420줄)
app/features/schedule/helpers/enrichment.py        # queue filter 교체 (206줄)
app/features/schedule/models/task.py               # status 필드 제거 (110줄, 119줄, 149줄)
app/features/schedule/routes/tasks.py              # status 쓰기 제거 (334줄, 484줄)
app/features/execution/routes/execution_api.py     # dead code 파일 삭제
tests/test_enrichment.py                           # test_queue_excludes_completed 수정
migrate_data.py                                    # 기존 JSON 마이그레이션
```

---

## Task 1: 실패 테스트 작성 — 새 동작 기록

**Files:**
- Modify: `tests/test_enrichment.py`

- [ ] **Step 1: test_queue_uses_execution_status_not_task_status 추가**

`tests/test_enrichment.py` 의 `TestQueueTasks` 클래스 안에 추가:

```python
def test_queue_uses_execution_status_not_task_status(self, app, client):
    """Queue 필터는 task.status 필드가 아닌 execution 상태 기반이어야 한다 (#108)."""
    uid = _create_user(client)
    vid = _create_version(client)
    tid = _create_task(client, uid, version_id=vid)

    # task.status = 'waiting' 인 상태에서 모든 식별자 execution 을 completed 로 만든다
    from app.features.execution.models.execution import ExecutionRepository
    with app.app_context():
        ex1 = ExecutionRepository.start('TC-001', tid)
        ExecutionRepository.complete(ex1['id'], fail_count=0)
        ex2 = ExecutionRepository.start('TC-002', tid)
        ExecutionRepository.complete(ex2['id'], fail_count=0)

    r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
    queue = r.get_json()['queue_tasks']
    queue_ids = [q['id'] for q in queue]
    # task.status 가 'waiting' 이어도 execution 기준으로 완료 → queue 에 없어야 함
    assert tid not in queue_ids
```

- [ ] **Step 2: sync_task_status 미호출 확인 테스트 추가**

`tests/test_calendar_api.py` 에서 `TestBlockStatus` 클래스 또는 파일 하단에 추가:

```python
def test_manual_block_status_does_not_write_task_status(app, client):
    """block_status 변경이 task.status 를 갱신하지 않아야 한다 (#108)."""
    uid = _create_user(client)
    tid = _create_task(client, uid)
    block_r = client.post('/schedule/api/blocks', json={
        'task_id': tid,
        'assignee_names': [uid],
        'date': '2026-03-10',
        'start_time': '09:00',
        'end_time': '10:00',
    })
    assert block_r.status_code == 201
    block_id = block_r.get_json()['id']

    from app.features.schedule.models import task as task_model
    with app.app_context():
        before_status = task_model.get_by_id(tid).get('status')

    r = client.put(f'/schedule/api/blocks/{block_id}/status',
                   json={'block_status': 'completed'})
    assert r.status_code == 200

    with app.app_context():
        after_status = task_model.get_by_id(tid).get('status')

    # task.status 가 변경되지 않아야 함
    assert after_status == before_status
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

```bash
source venv/bin/activate && pytest tests/test_enrichment.py::TestQueueTasks::test_queue_uses_execution_status_not_task_status tests/test_calendar_api.py::test_manual_block_status_does_not_write_task_status -v
```

Expected: FAIL (`test_queue_uses_execution_status_not_task_status`는 queue에서 제외되지 않음, `test_manual_block_status`는 task.status가 변경됨)

- [ ] **Step 4: Commit**

```bash
git add tests/test_enrichment.py tests/test_calendar_api.py
git commit -m "test(#108): 순환 write-back 제거 검증용 실패 테스트 추가"
```

---

## Task 2: sync_task_status 순환 경로 제거

**Files:**
- Modify: `app/features/schedule/routes/calendar_helpers.py:130-160`
- Modify: `app/features/schedule/routes/calendar_api.py:25,420`

- [ ] **Step 1: calendar_helpers.py 에서 sync_task_status 삭제**

`app/features/schedule/routes/calendar_helpers.py` 의 130~160줄 (`sync_task_status` 함수 전체) 삭제:

```python
# 이 함수 전체 삭제:
def sync_task_status(task_id):
    """블록 상태를 기반으로 태스크의 전체 상태를 자동 갱신한다. ..."""
    from app.features.schedule.models import task as task_model
    t = task_model.get_by_id(task_id)
    if not t:
        return
    blocks = [b for b in schedule_block.get_all()
              if b.get('task_id') == task_id]
    if not blocks:
        return
    statuses = [b.get('block_status', 'pending') for b in blocks]
    if all(s == 'completed' for s in statuses):
        new_status = 'completed'
    elif any(s == 'in_progress' for s in statuses):
        new_status = 'in_progress'
    elif any(s == 'completed' for s in statuses):
        new_status = 'in_progress'
    else:
        new_status = t['status']
    if new_status != t['status']:
        task_model.patch(task_id, status=new_status)
```

- [ ] **Step 2: calendar_api.py import 제거**

`app/features/schedule/routes/calendar_api.py` 25줄에서 `sync_task_status,` 제거:

```python
# BEFORE:
from app.features.schedule.routes.calendar_helpers import (
    VALID_BLOCK_STATUSES,
    remove_identifiers_from_other_blocks,
    sync_task_remaining_minutes,
    sync_task_status,
)

# AFTER:
from app.features.schedule.routes.calendar_helpers import (
    VALID_BLOCK_STATUSES,
    remove_identifiers_from_other_blocks,
    sync_task_remaining_minutes,
)
```

- [ ] **Step 3: calendar_api.py 호출부 제거**

`api_update_block_status` 함수(420줄 근처)에서 `sync_task_status` 호출 삭제:

현재 코드:
```python
    updated = schedule_block.update(block_id, block_status=status)
    # 블록 상태 변경에 따라 태스크 전체 상태를 자동 갱신
    task_id = block.get('task_id')
    if task_id:
        sync_task_status(task_id)
    return jsonify(updated)
```

변경 후:
```python
    updated = schedule_block.update(block_id, block_status=status)
    return jsonify(updated)
```

- [ ] **Step 4: 테스트 실행**

```bash
source venv/bin/activate && pytest tests/test_calendar_api.py::test_manual_block_status_does_not_write_task_status tests/test_calendar_api.py -v
```

Expected: `test_manual_block_status_does_not_write_task_status` PASS, 기존 calendar_api 테스트도 모두 통과

- [ ] **Step 5: Commit**

```bash
git add app/features/schedule/routes/calendar_helpers.py app/features/schedule/routes/calendar_api.py
git commit -m "fix(#108): sync_task_status 제거 — block→task 순환 write-back 삭제"
```

---

## Task 3: enrichment.py queue 필터를 execution 기반으로 교체

**Files:**
- Modify: `app/features/schedule/helpers/enrichment.py:206`
- Modify: `tests/test_enrichment.py:55-68` (기존 테스트 수정)

- [ ] **Step 1: enrichment.py get_queue_tasks() 수정**

`app/features/schedule/helpers/enrichment.py` 의 `get_queue_tasks()` 함수 내부, `for t in tasks:` 루프 시작 부분(206줄 전후):

현재:
```python
    for t in tasks:
        # 완료된 태스크는 큐에서 제외
        if t['status'] == 'completed':
            continue
```

변경 후:
```python
    from app.features.execution.models.execution import ExecutionRepository
    all_executions = ExecutionRepository.get_all()
    exec_by_identifier = {ex['identifier_id']: ex for ex in all_executions}

    for t in tasks:
        # execution 기준으로 모든 식별자가 완료된 태스크는 큐에서 제외 (#108)
        identifiers = t.get('identifiers', [])
        if identifiers:
            exec_statuses = [
                exec_by_identifier.get(
                    idf['id'] if isinstance(idf, dict) else idf, {}
                ).get('status', 'pending')
                for idf in identifiers
            ]
            if all(s == 'completed' for s in exec_statuses):
                continue
        elif t.get('status') == 'cancelled':
            # sync 서비스가 외부에서 삭제된 태스크에 설정하는 cancelled 는 유지
            continue
```

- [ ] **Step 2: test_queue_excludes_completed 수정**

`tests/test_enrichment.py` 의 `test_queue_excludes_completed`(55~68줄)를 다음으로 교체:

```python
def test_queue_excludes_completed(self, app, client):
    """모든 식별자가 execution 완료된 태스크는 queue 에서 제외된다 (#108)."""
    uid = _create_user(client)
    vid = _create_version(client)
    tid = _create_task(client, uid, version_id=vid)

    from app.features.execution.models.execution import ExecutionRepository
    with app.app_context():
        ex1 = ExecutionRepository.start('TC-001', tid)
        ExecutionRepository.complete(ex1['id'], fail_count=0)
        ex2 = ExecutionRepository.start('TC-002', tid)
        ExecutionRepository.complete(ex2['id'], fail_count=0)

    r = client.get(f'/schedule/api/day?date=2026-03-10&version={vid}')
    queue = r.get_json()['queue_tasks']
    queue_ids = [q['id'] for q in queue]
    assert tid not in queue_ids
```

- [ ] **Step 3: 테스트 실행**

```bash
source venv/bin/activate && pytest tests/test_enrichment.py -v
```

Expected: 모든 enrichment 테스트 PASS (포함: `test_queue_uses_execution_status_not_task_status`, `test_queue_excludes_completed`)

- [ ] **Step 4: Commit**

```bash
git add app/features/schedule/helpers/enrichment.py tests/test_enrichment.py
git commit -m "fix(#108): queue 필터를 execution 기반으로 교체, task.status 의존 제거"
```

---

## Task 4: task.status 필드 쓰기 제거 + dead code 정리

**Files:**
- Modify: `app/features/schedule/models/task.py:110,119,149`
- Modify: `app/features/schedule/routes/tasks.py:334,484`
- Delete: `app/features/execution/routes/execution_api.py` (dead code)

- [ ] **Step 1: task.py — create() 에서 status 제거**

`app/features/schedule/models/task.py` create() 메서드(110줄):

```python
# BEFORE: data dict 안에 있는 'status': 'waiting' 줄 삭제
data = {
    'doc_id': doc_id,
    'version_id': version_id,
    'assignee_names': assignee_names or [],
    'location_id': location_id,
    'doc_name': doc_name,
    'identifiers': identifiers or [],
    'estimated_minutes': estimated_minutes,
    'remaining_minutes': estimated_minutes,
    'status': 'waiting',          # ← 이 줄 삭제
    'memo': memo,
    'created_at': datetime.now().isoformat(timespec='seconds'),
}
```

- [ ] **Step 2: task.py — update() 에서 status 파라미터 제거**

`app/features/schedule/models/task.py` update() 시그니처(119줄)에서 `status` 파라미터 제거:

```python
# BEFORE:
    def update(cls, task_id, doc_id, assignee_names, location_id,
               doc_name, identifiers,
               estimated_minutes, remaining_minutes, status, memo='',
               version_id=''):

# AFTER:
    def update(cls, task_id, doc_id, assignee_names, location_id,
               doc_name, identifiers,
               estimated_minutes, remaining_minutes, memo='',
               version_id=''):
```

patch() 호출부(149줄)에서도 `status=status,` 줄 삭제:

```python
# BEFORE:
        return cls.patch(
            task_id,
            ...
            status=status,
            memo=memo,
        )

# AFTER:
        return cls.patch(
            task_id,
            ...
            memo=memo,
        )
```

- [ ] **Step 3: tasks.py — form + API 에서 status 쓰기 제거**

`app/features/schedule/routes/tasks.py` 334줄 (task_edit form 핸들러):

```python
# BEFORE:
        task.update(
            task_id=task_id,
            ...
            status=request.form.get('status', 'waiting'),
            memo=request.form.get('memo', '').strip(),
        )

# AFTER: status= 줄만 삭제
        task.update(
            task_id=task_id,
            ...
            memo=request.form.get('memo', '').strip(),
        )
```

`app/features/schedule/routes/tasks.py` 484줄 (api_task_update):

```python
# BEFORE:
    updated = task.update(
        task_id=task_id,
        ...
        status=data.get('status', t.get('status', 'waiting')),
        memo=data.get('memo', t.get('memo', '')),
    )

# AFTER: status= 줄만 삭제
    updated = task.update(
        task_id=task_id,
        ...
        memo=data.get('memo', t.get('memo', '')),
    )
```

- [ ] **Step 4: execution_api.py dead code 삭제**

`app/features/execution/routes/execution_api.py` 파일 삭제 (라우터에 등록되지 않은 dead code):

```bash
git rm app/features/execution/routes/execution_api.py
```

- [ ] **Step 5: 전체 테스트 실행**

```bash
source venv/bin/activate && pytest tests/ -v
```

Expected: 173+ 통과, 2개 기존 실패 (`requests` 모듈 미설치) 외 신규 실패 없음

- [ ] **Step 6: Commit**

```bash
git add app/features/schedule/models/task.py app/features/schedule/routes/tasks.py
git commit -m "fix(#108): task.status 쓰기 제거, execution_api.py dead code 삭제"
```

---

## Task 5: 기존 데이터 마이그레이션 (tasks.json)

**Files:**
- Modify: `migrate_data.py`

- [ ] **Step 1: migrate_data.py 읽기**

현재 파일 구조 확인:
```bash
cat migrate_data.py
```

- [ ] **Step 2: remove_task_status_field 함수 추가**

`migrate_data.py` 에 함수 추가:

```python
def remove_task_status_field():
    """tasks.json 에서 status 필드 제거 (#108).

    'cancelled' 값은 sync 서비스가 외부에서 삭제된 태스크 표시에 사용하므로 유지.
    'waiting'/'in_progress'/'completed' 는 execution 기반으로 동적 계산되므로 삭제.
    """
    import os
    data_dir = os.path.join(os.path.dirname(__file__), 'app', 'features', 'schedule', 'data')
    tasks_file = os.path.join(data_dir, 'tasks.json')
    with open(tasks_file) as f:
        tasks = json.load(f)

    removed = retained = 0
    for t in tasks:
        s = t.get('status')
        if s == 'cancelled':
            retained += 1
        elif 'status' in t:
            del t['status']
            removed += 1

    with open(tasks_file, 'w') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

    print(f'  tasks.json: status 필드 {removed}개 삭제, cancelled {retained}개 유지')
```

- [ ] **Step 3: __main__ 블록에 호출 추가**

`migrate_data.py` 의 `if __name__ == '__main__':` 블록에:

```python
    print('태스크 status 필드 마이그레이션 중...')
    remove_task_status_field()
```

- [ ] **Step 4: 마이그레이션 실행**

```bash
source venv/bin/activate && python migrate_data.py
```

Expected 출력 예시:
```
태스크 status 필드 마이그레이션 중...
  tasks.json: status 필드 10개 삭제, cancelled 0개 유지
```

- [ ] **Step 5: 마이그레이션 결과 확인**

```bash
python3 -c "import json; data=json.load(open('app/features/schedule/data/tasks.json')); statuses=[t.get('status') for t in data if 'status' in t]; print('남은 status:', statuses)"
```

Expected: `남은 status: []` 또는 cancelled 만 존재

- [ ] **Step 6: 전체 테스트 재실행**

```bash
source venv/bin/activate && pytest tests/ -v
```

Expected: 173+ 통과

- [ ] **Step 7: Commit**

```bash
git add migrate_data.py app/features/schedule/data/tasks.json
git commit -m "fix(#108): tasks.json 에서 status 필드 마이그레이션, migrate_data.py 업데이트"
```

---

## 검증 체크리스트

- [ ] `pytest tests/ -v` — 173+ 통과
- [ ] 서버 실행 후 `/tasks/` — 시험항목 목록 상태 chip 정상 표시 (execution 기반)
- [ ] `/tasks/` — 동기화 업데이트 후 완료된 항목이 queue에서 제외
- [ ] `/schedule/` 캘린더 — 블록 수동 block_status 변경 후 task.status 미변경 확인
- [ ] `/execution/` — execution 완료 후 schedule 캘린더 block 시각 상태 변화 없음 (block_status는 수동만)
- [ ] `app/features/schedule/data/tasks.json` — status 필드 없음 (cancelled 제외)
- [ ] `app/features/execution/routes/execution_api.py` — 파일 삭제됨
